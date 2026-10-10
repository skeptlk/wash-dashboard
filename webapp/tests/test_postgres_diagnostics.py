"""Preserve connection evidence without publishing credentials."""

from contextlib import nullcontext
from types import SimpleNamespace
import sys

import pytest

from webapp.data import postgres_diagnostics as diag
from webapp.data import sync_flights


@pytest.fixture
def passfile(tmp_path, monkeypatch):
    path = tmp_path / "pgpass.conf"
    for key, value in dict(
        PGHOST="db",
        PGPORT="5432",
        PGDATABASE="ecm",
        PGUSER="reader",
        PGPASSFILE=str(path),
    ).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SYNC_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    return path


def test_pgpass_matching_and_escaped_password(passfile):
    passfile.write_text(
        "other:5432:ecm:reader:other-password\ndb:5432:ecm:reader:abc\\:def\\\\xyz\n"
    )
    notes, entries = diag.password_file()
    assert entries[1][4] == "abc:def\\xyz"
    assert any("has a matching" in n for n in notes)
    assert "abc" not in " ".join(notes)
    error = RuntimeError("ошибка подключения: abc:def\\xyz other-password")
    detail = diag.connection_error_detail(error)
    assert "ошибка подключения" in detail
    assert "abc" not in detail and "other-password" not in detail


@pytest.mark.parametrize(
    ("encoding", "expected"), [("utf-8-sig", "BOM"), ("utf-16", "UTF-16")]
)
def test_windows_password_file_encoding(passfile, encoding, expected):
    passfile.write_text("db:5432:ecm:reader:secret", encoding=encoding)
    assert expected in " ".join(diag.password_file()[0])
    assert "secret" not in diag.connection_error_detail(RuntimeError("failure: secret"))


def test_missing_and_nonmatching_password_file(passfile):
    assert "cannot be read" in " ".join(diag.password_file()[0])
    passfile.write_text("wrong:5432:ecm:reader:secret")
    assert "no matching" in " ".join(diag.password_file()[0])


def test_environment_password_precedence(passfile, monkeypatch):
    passfile.write_text("db:5432:ecm:reader:file-secret")
    monkeypatch.setenv("PGPASSWORD", "environment-secret")
    assert "takes precedence" in " ".join(diag.password_file()[0])
    detail = diag.connection_error_detail(
        RuntimeError("failure environment-secret file-secret")
    )
    assert "environment-secret" not in detail and "file-secret" not in detail


def test_detail_preserves_unknown_localized_error_and_masks_all_password_sources(
    passfile, monkeypatch
):
    passfile.write_text("db:5432:ecm:reader:file-secret")
    monkeypatch.setenv("PGPASSWORD", "env-secret")
    exc = RuntimeError(
        "ошибка сервера: env-secret file-secret native-secret typed-secret\npassword='arbitrary secret' postgresql://user:uri-secret@host/db"
    )
    exc.pgconn = SimpleNamespace(password=b"native-secret")
    result = diag.connection_error_detail(exc, "typed-secret")
    assert "ошибка сервера" in result
    assert "secret" not in result
    assert "\n" not in result


def test_interactive_check_bypasses_file_password_and_quack(
    tmp_path, monkeypatch, caplog
):
    import getpass

    calls = []
    connection = SimpleNamespace(
        execute=lambda sql: SimpleNamespace(fetchone=lambda: (1,))
    )

    def connect(*a, **kw):
        calls.append(kw)
        return nullcontext(connection)

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "typed-secret")
    monkeypatch.setattr(
        sync_flights,
        "connect_remote",
        lambda **kw: pytest.fail("Quack must not be opened"),
    )
    caplog.set_level("INFO")
    sync_flights.main(
        ["--check-postgres", "--ask-password", "--lock-file", str(tmp_path / "lock")],
        connection_context=lambda: pytest.fail("SSH must not be opened"),
    )
    assert calls[0]["password"] == "typed-secret"
    assert "typed-secret" not in caplog.text
    assert "PostgreSQL check OK" in caplog.text


def test_localized_connection_failure_is_visible_and_interactive_password_is_masked(
    tmp_path, monkeypatch, caplog
):
    import getpass

    class OperationalError(Exception):
        pass

    def fail(*a, **kw):
        raise OperationalError("нет доступа к серверу; typed-secret")

    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=fail, Error=OperationalError)
    )
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "typed-secret")
    with pytest.raises(SystemExit) as result:
        sync_flights.main(
            [
                "--check-postgres",
                "--ask-password",
                "--lock-file",
                str(tmp_path / "lock"),
            ]
        )
    assert result.value.code == 1
    assert "нет доступа к серверу" in caplog.text
    assert "typed-secret" not in caplog.text
