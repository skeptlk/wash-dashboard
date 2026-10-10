"""Python launcher configuration and SSH lifecycle without a Windows shell."""

from contextlib import nullcontext
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from webapp.data import sync_client as client


def test_existing_configuration_can_be_reused():
    config = client.read_config(client.ROOT / "deploy/postgres-sync.example.psd1")
    assert config["SSH_LOCAL_PORT"] == 19494
    assert config["WINDOW_DAYS"] == 7
    assert config["PGPASSFILE"] == r"C:\engine-wash-secrets\pgpass.conf"


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_windows_encoding_and_literal_paths(tmp_path, encoding):
    path = tmp_path / "config.psd1"
    path.write_text(
        "@{\n# comment\nPGUSER = 'O''Brien' # comment\nPGPASSFILE = 'C:\\a b\\пароль.conf'\n}\n",
        encoding=encoding,
    )
    assert client.read_config(path) == {
        "PGUSER": "O'Brien",
        "PGPASSFILE": "C:\\a b\\пароль.conf",
    }


@pytest.mark.parametrize(
    "body",
    [
        "PGHOST = $(Invoke-Expression 'secret')",
        "PGHOST = 'first'\nPGHOST = 'secret'",
        "UNKNOWN = 'secret'",
        "SSH_LOCAL_PORT = 65536",
        "WINDOW_DAYS = 0",
        "PGUSER = 123",
        "SSH_HOST = '-secret'",
        "PGHOST = 'secret'; Invoke-Expression 'command'",
    ],
)
def test_rejects_expressions_and_invalid_settings_without_echoing_values(
    tmp_path, body
):
    path = tmp_path / "config.psd1"
    path.write_text("@{\n" + body + "\n}\n")
    with pytest.raises(client.ConfigurationError) as error:
        client.read_config(path)
    assert "secret" not in str(error.value)


def test_launcher_sets_environment_and_passes_python_flags(tmp_path, monkeypatch):
    config = tmp_path / "existing.psd1"
    config.write_text(
        "@{\nPGHOST = 'test.internal'\nWINDOW_DAYS = 2\nSSH_HOST = ''\n}\n"
    )
    monkeypatch.setenv("SYNC_POSTGRES_DSN", "stale")
    monkeypatch.setenv("PGHOST", "original")
    monkeypatch.setattr(client, "ROOT", tmp_path)
    call = Mock()
    monkeypatch.setattr(client.sync_flights, "main", call)
    client.main(["--config", str(config), "--dry-run", "--max-windows", "1"])
    assert client.os.environ["PGHOST"] == "test.internal"
    assert "SYNC_POSTGRES_DSN" not in client.os.environ
    args, kwargs = call.call_args
    assert args[0] == [
        "--log-file",
        str(tmp_path / "data/sync-logs/sync.log"),
        "--window-days",
        "2",
        "--dry-run",
        "--max-windows",
        "1",
    ]
    with kwargs["connection_context"]():
        pass


def test_help_does_not_require_configuration(monkeypatch):
    read = Mock(side_effect=AssertionError("should not read"))
    monkeypatch.setattr(client, "read_config", read)
    with pytest.raises(SystemExit) as result:
        client.main(["--help"])
    assert result.value.code == 0


@pytest.fixture
def ssh_mocks(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr(client.subprocess, "Popen", launch)
    monkeypatch.setattr(client.socket, "socket", lambda: nullcontext(Mock()))
    monkeypatch.setattr(
        client.socket, "create_connection", lambda *a, **kw: nullcontext()
    )
    monkeypatch.setenv("FLIGHT_QUACK_URL", "original")
    return process, launch


def test_tunnel_uses_argument_array_and_closes_on_failure(tmp_path, ssh_mocks):
    process, launch = ssh_mocks
    with pytest.raises(RuntimeError, match="ingestion failed"):
        with client.ssh_tunnel(
            {"SSH_HOST": "user@host", "SSH_IDENTITY_FILE": r"C:\a b\key"}, tmp_path
        ):
            assert client.os.environ["FLIGHT_QUACK_URL"] == "quack:127.0.0.1:19494"
            raise RuntimeError("ingestion failed")
    command = launch.call_args.args[0]
    assert command[-3:] == ["-i", r"C:\a b\key", "user@host"]
    assert "StrictHostKeyChecking=yes" in command
    assert launch.call_args.kwargs.get("shell", False) is False
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)


def test_failed_ssh_does_not_yield(tmp_path, ssh_mocks):
    process, _ = ssh_mocks
    process.poll.return_value = 255
    with pytest.raises(client.ConfigurationError, match="SSH tunnel failed"):
        with client.ssh_tunnel({"SSH_HOST": "user@host"}, tmp_path):
            pytest.fail("must not start ingestion")
    process.terminate.assert_not_called()


def test_tunnel_force_stops_only_its_child_after_timeout(tmp_path, ssh_mocks):
    process, _ = ssh_mocks
    process.wait.side_effect = [subprocess.TimeoutExpired("ssh", 5), 0]
    with client.ssh_tunnel({"SSH_HOST": "user@host"}, tmp_path):
        pass
    process.kill.assert_called_once()


def test_existing_endpoint_does_not_launch_ssh(tmp_path, ssh_mocks):
    _, launch = ssh_mocks
    with client.ssh_tunnel({"SSH_HOST": ""}, tmp_path):
        pass
    launch.assert_not_called()


def test_launcher_file_runs_help_from_another_directory(tmp_path):
    import sys

    script = Path(__file__).resolve().parents[2] / "deploy/run_postgres_sync.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--config" in result.stdout and "--dry-run" in result.stdout


def test_connection_context_runs_inside_lock_and_closes(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from contextlib import contextmanager

    events = []
    lock = tmp_path / "sync.lock"

    @contextmanager
    def tunnel():
        with pytest.raises(OSError):
            with client.sync_flights.single_instance(lock):
                pytest.fail("ingestion lock must precede tunnel creation")
        events.append("tunnel open")
        try:
            yield
        finally:
            events.append("tunnel closed")

    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *a, **kw: nullcontext(object())),
    )
    monkeypatch.setattr(
        client.sync_flights, "connect_remote", lambda **kw: nullcontext(object())
    )

    def fail(*args, **kwargs):
        events.append("sync")
        raise client.sync_flights.SourceDataError("test source error")

    monkeypatch.setattr(client.sync_flights, "sync", fail)
    with pytest.raises(SystemExit) as result:
        client.sync_flights.main(
            ["--lock-file", str(lock), "--dry-run"], connection_context=tunnel
        )
    assert result.value.code == 1
    assert events == ["tunnel open", "sync", "tunnel closed"]
    with client.sync_flights.single_instance(lock):
        pass
