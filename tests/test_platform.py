import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

from server.app import build_app
from server.backend import DomainError
from storage.backend import RulesBackend
from storage.repository import SQLiteRepository
from server.contracts import HealthEvent
from server.identity import BearerMapping, Identity
from server.notifications import Notifications

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)
A = Identity("home-a", "America/Chicago")
B = Identity("home-b", "America/Chicago")
TOKEN = "a" * 40


@pytest.fixture
def backend(tmp_path):
    return RulesBackend(SQLiteRepository(tmp_path / "test.sqlite3"))


def add(backend, who=A):
    return backend.execute("add_cat", {"name": "Mochi", "idempotency_key": "create-cat"}, who, NOW)["cat"]["cat_id"]


def event(cat, **values):
    return HealthEvent.model_validate({"cat_id": cat, "idempotency_key": "event-key", "event_type": "vomiting", **values}).model_dump(mode="json", exclude_none=True)


def test_retry_update_restart_and_isolation(backend):
    cat = add(backend)
    first = backend.execute("log_health_event", event(cat), A, NOW)
    assert backend.execute("log_health_event", event(cat), A, NOW) == first
    corrected = backend.execute("log_health_event", event(cat, event_id=first["event_id"], idempotency_key="follow-up", details={"blood": None}), A, NOW)
    assert corrected["event_id"] == first["event_id"]
    assert corrected["event"]["details"]["blood"] is None
    restarted = RulesBackend(SQLiteRepository(backend.repository.path))
    assert len(restarted.execute("get_today", {"cat_id": cat}, A, NOW)["events"]) == 1
    with pytest.raises(DomainError, match="Cat not found"):
        restarted.execute("get_today", {"cat_id": cat}, B, NOW)
    with pytest.raises(DomainError) as conflict:
        backend.execute("log_health_event", event(cat, details={"blood": True}), A, NOW)
    assert conflict.value.code == "idempotency_conflict"


def test_concurrent_retry(backend):
    cat = add(backend)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: backend.execute("log_health_event", event(cat), A, NOW), range(8)))
    assert len({r["event_id"] for r in results}) == 1


def test_timezone_and_event_boundaries(backend):
    cat = add(backend)
    for index, timestamp in enumerate(["2026-10-12T04:59:59Z", "2026-10-12T05:00:00Z", "2026-10-12T05:00:00Z"]):
        backend.execute("log_health_event", event(cat, idempotency_key=f"time-key-{index}", occurred_at=timestamp), A, NOW)
    assert len(backend.execute("get_today", {"cat_id": cat}, A, NOW)["events"]) == 2
    with pytest.raises(DomainError, match="future"):
        backend.execute("log_health_event", event(cat, idempotency_key="future-key", occurred_at="2026-10-13T00:00:00Z"), A, NOW)


@pytest.mark.parametrize("ledger_failure", [False, True])
def test_mcp_http(backend, ledger_failure):
    class SNS:
        calls = 0
        def publish(self, **kwargs):
            self.calls += 1
            return {"MessageId": "accepted"}
    sns = SNS()
    notifications = Notifications(backend.repository.path, sns, {A.household_id: "arn:test"})
    if ledger_failure:
        class BrokenLedger:
            def send(self, *args):
                raise RuntimeError("Notification persistence unavailable")
        notifications = BrokenLedger()
    app = build_app(backend=backend, mapping=BearerMapping({TOKEN: {"household_id": A.household_id, "timezone": A.timezone}}), clock=lambda: NOW, notifications=notifications)
    with TestClient(app) as client:
        assert client.post("/mcp/", json={}).status_code == 401
        assert "www-authenticate" not in client.post("/mcp/", json={}).headers
        headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json, text/event-stream"}
        def rpc(method, params=None):
            response = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
            assert response.status_code == 200, response.text
            return response.json()["result"]
        initialized = rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        assert initialized["serverInfo"]["name"] == "cat-nanny"
        headers["MCP-Protocol-Version"] = initialized["protocolVersion"]
        tools = rpc("tools/list")["tools"]
        assert len(tools) == 8
        resources = rpc("resources/list")["resources"]
        assert len(resources) == 2
        today_tool = next(t for t in tools if t["name"] == "get_today")
        uri = today_tool["_meta"]["ui"]["resourceUri"]
        html = rpc("resources/read", {"uri": uri})["contents"][0]
        assert html["mimeType"] == "text/html;profile=mcp-app"
        assert "<!doctype html>" in html["text"]
        created = rpc("tools/call", {"name": "add_cat", "arguments": {"name": "Mochi", "idempotency_key": "create-cat"}})["structuredContent"]
        cat = created["cat"]["cat_id"]
        logged = rpc("tools/call", {"name": "log_health_event", "arguments": event(cat)})
        assert logged["structuredContent"]["logged"]
        assert logged["structuredContent"]["follow_up"]
        supplement = event(cat, event_id=logged["structuredContent"]["event_id"], idempotency_key="blood-answer", details={"blood": True})
        warning = rpc("tools/call", {"name": "log_health_event", "arguments": supplement})["structuredContent"]
        assert warning["red_flags"][0]["level"] == "urgent"
        assert warning["notification_status"]["state"] == ("failed" if ledger_failure else "sent")
        rpc("tools/call", {"name": "log_health_event", "arguments": supplement})
        assert sns.calls == (0 if ledger_failure else 1)
        assert warning["limitations"]
        queried = rpc("tools/call", {"name": "get_today", "arguments": {"cat_id": cat}})
        assert len(queried["structuredContent"]["events"]) == 1
        invalid = rpc("tools/call", {"name": "get_today", "arguments": {"cat_id": cat, "household_id": "home-b"}})
        assert invalid["isError"]
        assert invalid["structuredContent"]["error"]["code"] == "invalid_arguments"
        hostile = client.post("/mcp/", headers={**headers, "Origin": "https://evil.example"}, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert hostile.status_code == 403


@pytest.mark.parametrize("failure", [False, True])
def test_notification_deduplication_and_failure(tmp_path, failure):
    class SNS:
        calls = 0
        def publish(self, **kwargs):
            self.calls += 1
            if failure:
                raise RuntimeError("private provider error")
            return {"MessageId": "accepted-id"}
    sns = SNS()
    path = tmp_path / "notifications.sqlite3"
    notifications = Notifications(path, sns, {"home-a": "arn:fixture"})
    flags = [{"rule_id": "rule-1"}]
    expected = "uncertain" if failure else "sent"
    assert notifications.send("home-a", "event-1", flags)["state"] == expected
    assert Notifications(path, sns, {"home-a": "arn:fixture"}).send("home-a", "event-1", flags)["state"] == expected
    assert sns.calls == 1
    assert notifications.send("home-b", "event-1", flags)["state"] == "disabled"


def test_startup_requires_identity_and_blocks_unconfigured_production(monkeypatch, tmp_path):
    from server.app import create_app
    monkeypatch.setenv("CAT_NANNY_DB", str(tmp_path / "startup.sqlite3"))
    monkeypatch.delenv("CAT_NANNY_TOKEN_MAP", raising=False)
    with pytest.raises(ValueError, match="anonymous access"):
        create_app()
    monkeypatch.setenv("CAT_NANNY_MODE", "production")
    with pytest.raises(RuntimeError, match="OAuth verifier"):
        create_app()
    monkeypatch.setenv("CAT_NANNY_MODE", "local")
    monkeypatch.setenv("CAT_NANNY_TOKEN_MAP", json.dumps({TOKEN: {"household_id": A.household_id, "timezone": A.timezone}}))
    monkeypatch.delenv("CAT_NANNY_SNS_TOPICS", raising=False)
    assert create_app() is not None
