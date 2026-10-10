"""Python-only scheduled ingestion launcher, including optional OpenSSH tunnel."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import socket
import subprocess
import time

from . import sync_flights

ROOT = Path(__file__).resolve().parents[3]
ENV_KEYS = {
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSFILE",
    "PGSSLMODE",
    "PGSSLROOTCERT",
    "QUACK_TOKEN_FILE",
    "DUCKDB_EXTENSION_DIRECTORY",
    "FLIGHT_QUACK_URL",
}
CONFIG_KEYS = ENV_KEYS | {
    "SSH_HOST",
    "SSH_LOCAL_PORT",
    "SSH_IDENTITY_FILE",
    "WINDOW_DAYS",
}


class ConfigurationError(sync_flights.SourceDataError):
    """Safe diagnostic without configuration values or credentials."""


def read_config(path):
    """Read the existing PSD1 as literal data; never run PowerShell or evaluate it.

    Only the example's flat KEY = 'string' / integer format is supported.
    Reject expressions, interpolation, duplicate/unknown keys and malformed lines.
    """
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    lines = raw.decode(encoding).splitlines()
    data, opened, closed = {}, False, False
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not opened and line == "@{":
            opened = True
            continue
        if opened and not closed and line == "}":
            closed = True
            continue
        match = re.fullmatch(
            r"([A-Z_]+)\s*=\s*('(?:[^']|'')*'|[0-9]+)\s*(?:#.*)?", line
        )
        if not opened or closed or not match:
            raise ConfigurationError(
                f"Unsupported configuration syntax at line {number}; use the example's literal values"
            )
        key, value = match.groups()
        if key not in CONFIG_KEYS or key in data:
            raise ConfigurationError(
                f"Unknown or duplicate configuration key at line {number}"
            )
        data[key] = (
            value[1:-1].replace("''", "'") if value.startswith("'") else int(value)
        )
    if not opened or not closed:
        raise ConfigurationError("Configuration must be enclosed in @{ and }")
    for key in CONFIG_KEYS - {"SSH_LOCAL_PORT", "WINDOW_DAYS"}:
        if key in data and not isinstance(data[key], str):
            raise ConfigurationError(f"{key} must be a single-quoted string")
    for key in ("SSH_LOCAL_PORT", "WINDOW_DAYS"):
        if key in data and (not isinstance(data[key], int) or data[key] < 1):
            raise ConfigurationError(f"{key} must be a positive integer")
    if data.get("SSH_LOCAL_PORT", 19494) > 65535:
        raise ConfigurationError("SSH_LOCAL_PORT must be between 1 and 65535")
    if data.get("SSH_HOST", "").startswith("-"):
        raise ConfigurationError("Invalid SSH_HOST")
    return data


@contextmanager
def ssh_tunnel(config, log_directory):
    host = config.get("SSH_HOST")
    if not host:
        yield
        return
    port = config.get("SSH_LOCAL_PORT", 19494)
    # Do not mistake an unrelated existing listener for our newly started tunnel.
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise ConfigurationError(
                "SSH_LOCAL_PORT is already in use; select another port or configure an existing tunnel"
            ) from None
    command = [
        "ssh",
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-L",
        f"127.0.0.1:{port}:127.0.0.1:9494",
    ]
    if config.get("SSH_IDENTITY_FILE"):
        command.extend(["-i", config["SSH_IDENTITY_FILE"]])
    command.append(host)
    log_directory.mkdir(parents=True, exist_ok=True)
    with (log_directory / "ssh-error.log").open("wb") as log:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError:
            raise ConfigurationError(
                "OpenSSH client (ssh.exe) was not found; install it or use an existing tunnel with SSH_HOST = ''"
            ) from None
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise ConfigurationError(
                        "SSH tunnel failed; see data/sync-logs/ssh-error.log"
                    )
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ConfigurationError(
                            "SSH tunnel startup timed out; see data/sync-logs/ssh-error.log"
                        ) from None
                    time.sleep(0.1)
            if process.poll() is not None:
                raise ConfigurationError(
                    "SSH tunnel exited during startup; see data/sync-logs/ssh-error.log"
                )
            os.environ["FLIGHT_QUACK_URL"] = f"quack:127.0.0.1:{port}"
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "deploy" / "postgres-sync.local.psd1"
    )
    args, forwarded = parser.parse_known_args(argv)
    if "--help" in forwarded or "-h" in forwarded:
        print(
            "Python launcher: --config PATH (default: deploy/postgres-sync.local.psd1)"
        )
        sync_flights.main(["--help"])
        return
    try:
        config = read_config(args.config)
        for key in ENV_KEYS:
            if key in config:
                os.environ[key] = str(config[key])
        # Match the original launcher's explicit settings rather than a stale DSN.
        os.environ.pop("SYNC_POSTGRES_DSN", None)
        log_directory = ROOT / "data" / "sync-logs"
        defaults = ["--log-file", str(log_directory / "sync.log")]
        if "WINDOW_DAYS" in config:
            defaults += ["--window-days", str(config["WINDOW_DAYS"])]
        # The existing ingestion lock is acquired before starting SSH; no second
        # launcher may replace logs or compete for the port during a long catch-up.
        sync_flights.main(
            defaults + forwarded,
            connection_context=lambda: ssh_tunnel(config, log_directory),
        )
    except (ConfigurationError, OSError, UnicodeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, ConfigurationError)
            else f"Cannot read configuration ({type(exc).__name__}); check --config and file permissions"
        )
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
