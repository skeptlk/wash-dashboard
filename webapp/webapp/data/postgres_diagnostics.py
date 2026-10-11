"""Password-file loading and diagnostics; never print credentials or DSNs."""

import os
from pathlib import Path
import re
from urllib.parse import quote, quote_plus


class PasswordFileError(ValueError):
    """Safe configuration diagnostic containing no password-file values."""


def password_file():
    """Return diagnostic notes and parsed entries, without changing the file."""
    filename = os.environ.get("PGPASSFILE")
    if not filename:
        return ["PGPASSFILE is not explicitly set; libpq uses its defaults."], []
    try:
        raw = Path(filename).read_bytes()
    except OSError:
        return [
            "PGPASSFILE cannot be read; check the path, .txt extension and permissions."
        ], []
    notes = ["PGPASSFILE is readable."]
    encoding = "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
        notes.append("PGPASSFILE is UTF-16; the Python reader decodes it explicitly.")
    elif raw.startswith(b"\xef\xbb\xbf"):
        notes.append(
            "PGPASSFILE starts with a UTF-8 BOM; the Python reader removes it."
        )
    try:
        content = raw.decode(encoding)
    except UnicodeError:
        return notes + ["PGPASSFILE is not valid UTF-8; verify its encoding."], []
    entries = []
    for line in content.splitlines():
        if not line or line.startswith("#"):
            continue
        fields, current, escaped = [], "", False
        for char in line:
            if escaped:
                current += char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == ":" and len(fields) < 4:
                fields.append(current)
                current = ""
            else:
                current += char
        fields.append(current)
        if len(fields) == 5 and not escaped:
            entries.append(fields)
    keys = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")
    if all(os.environ.get(k) for k in keys) and not os.environ.get("SYNC_POSTGRES_DSN"):
        target = [os.environ[k] for k in keys]
        match = next(
            (
                e
                for e in entries
                if all(v == "*" or v == t for v, t in zip(e[:4], target))
            ),
            None,
        )
        notes.append(
            "PGPASSFILE has a matching host/port/database/user entry (password not verified)."
            if match
            else "PGPASSFILE has no matching host/port/database/user entry for the configured PG* values."
        )
    if os.environ.get("PGPASSWORD"):
        notes.append(
            "PGPASSWORD is set in the environment; explicit Python password-file loading overrides it."
        )
    return notes, entries


def configured_password():
    """Load the first matching password for the launcher's explicit PG* config.

    Keep the native libpq credential resolution for direct DSN-based clients and
    clients without an explicitly configured password file. The Windows launcher
    uses PG* settings and does not use a DSN.
    """
    if not os.environ.get("PGPASSFILE") or os.environ.get("SYNC_POSTGRES_DSN"):
        return None
    keys = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")
    if not all(os.environ.get(key) for key in keys):
        raise PasswordFileError(
            "Explicit PGPASSFILE loading requires PGHOST, PGPORT, PGDATABASE and PGUSER."
        )
    notes, entries = password_file()
    if not entries:
        raise PasswordFileError("No usable PGPASSFILE entries. " + " ".join(notes))
    target = [os.environ[key] for key in keys]
    for entry in entries:
        if all(
            value == "*" or value == expected
            for value, expected in zip(entry[:4], target)
        ):
            if not entry[4]:
                raise PasswordFileError(
                    "The first matching PGPASSFILE entry has an empty password."
                )
            return entry[4]
    raise PasswordFileError(
        "No matching PGPASSFILE entry for PGHOST/PGPORT/PGDATABASE/PGUSER. "
        "Use the actual connection port (including a pooler port, e.g. 6432)."
    )


def connection_error_detail(exc, supplied_password=None):
    """Retain localized libpq diagnostics, masking known secrets and credentials.

    Only use for connection errors, never query errors which could contain SQL data.
    """
    secrets = {
        supplied_password,
        os.environ.get("PGPASSWORD"),
        os.environ.get("SYNC_POSTGRES_DSN"),
    }
    _, entries = password_file()
    secrets.update(e[4] for e in entries)
    try:
        password = exc.pgconn.password
        if password:
            secrets.add(
                password.decode("utf-8") if isinstance(password, bytes) else password
            )
    except Exception:
        # Some failed libpq connections already have a closed handle. Metadata
        # access must not hide the original error during diagnostic reporting.
        pass
    text = str(exc)
    text = re.sub(r"(?i)postgres(?:ql)?://[^\s]+", "[redacted connection URI]", text)
    text = re.sub(
        r"""(?ix)\b(?:password|sslpassword)\s*=\s*(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|[^\s;]+)""",
        "password=[redacted]",
        text,
    )
    variants = {
        v
        for secret in secrets
        if secret
        for v in (
            secret,
            quote(secret, safe=""),
            quote_plus(secret),
            secret.replace("\\", "\\\\").replace("'", "\\'"),
        )
    }
    for secret in sorted(variants, key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    return " | ".join(text.splitlines())[:4000]
