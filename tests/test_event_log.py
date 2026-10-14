import sqlite3

import pytest

from nexo.events.log import EventLog


@pytest.fixture
def log(tmp_path):
    lg = EventLog(tmp_path / "events.db")
    yield lg
    lg.close()


def test_append_and_read(log):
    log.append("intent", {"text": "hola"}, correlation_id="c1")
    log.append("action", {"tool": "fs.write"}, correlation_id="c1")
    log.append("intent", {"text": "otra"}, correlation_id="c2")
    assert len(log.read()) == 3
    assert [e["kind"] for e in log.read(correlation_id="c1")] == ["intent", "action"]
    assert len(log.read(kind="intent")) == 2


def test_secrets_are_redacted(log):
    log.append("cfg", {"github_token": "ghp_SECRET", "nested": {"password": "p", "ok": 1}})
    p = log.read()[0]["payload"]
    assert p["github_token"] == "[REDACTED]"
    assert p["nested"]["password"] == "[REDACTED]"
    assert p["nested"]["ok"] == 1


def test_append_only(log):
    log.append("x", {})
    with pytest.raises(sqlite3.DatabaseError):
        log._conn.execute("UPDATE events SET kind='y'")
    with pytest.raises(sqlite3.DatabaseError):
        log._conn.execute("DELETE FROM events")
    assert len(log.read()) == 1
