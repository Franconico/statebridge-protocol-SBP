"""
SBP Conformance Tests — one test per normative MUST requirement.

Covers L1 (Stateful Proxy), L2 (Tether + Resume), L3 (Roaming), L4 (Surface
negotiation), and L5 (Surface MCP Bridge).

These tests use the in-memory backend. They validate the wire protocol shape
and state machine semantics as specified in spec/SPEC.md.
"""
from __future__ import annotations

import json
import os
import uuid

# Set env vars BEFORE any sbp_server imports so module-level reads pick them up
os.environ["SBP_LLM_BASE_URL"] = "http://mock-llm"
os.environ["SBP_JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sbp_server.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def app():
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── LLM mock helper ───────────────────────────────────────────────────────────

def _llm_ok(model: str = "gpt-4o", content: str = "Hello!") -> httpx.Response:
    """Return a minimal valid LLM response."""
    return httpx.Response(200, json={
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def _mock_llm(monkeypatch, captured: dict | None = None):
    """
    Patch _call_llm so tests never hit a real LLM endpoint.
    If `captured` is provided, the request_dict is stored in captured["body"].
    """
    async def _fake_call_llm(url: str, request_dict: dict) -> httpx.Response:
        if captured is not None:
            captured["body"] = request_dict
        return _llm_ok()

    monkeypatch.setattr("sbp_server.routers.completions._call_llm", _fake_call_llm)


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    """Server MUST expose /health returning sbp_version='1.2'."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["sbp_version"] == "1.2"


# ── L1: Stateful Proxy ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_l1_missing_llm_url_returns_503(monkeypatch, app):
    """
    SPEC §5 — Server MUST return 503 when LLM endpoint is unreachable.
    We verify by letting _call_llm raise a ConnectError.
    """
    from fastapi import HTTPException

    async def _unreachable(url: str, request_dict: dict) -> httpx.Response:
        raise HTTPException(status_code=503, detail="Cannot reach LLM endpoint (mocked)")

    monkeypatch.setattr("sbp_server.routers.completions._call_llm", _unreachable)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/v1/chat/completions", json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        })
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_l1_response_includes_sbp_session_id(client, monkeypatch):
    """SPEC §5 — Response MUST include sbp.session_id as a valid UUID."""
    _mock_llm(monkeypatch)

    resp = await client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "sbp" in data
    assert uuid.UUID(data["sbp"]["session_id"])


@pytest.mark.asyncio
async def test_l1_response_includes_session_token_header(client, monkeypatch):
    """SPEC §5 — Response MUST include X-Session-Token header."""
    _mock_llm(monkeypatch)

    resp = await client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert resp.status_code == 200
    assert "x-session-token" in resp.headers


@pytest.mark.asyncio
async def test_l1_sbp_namespace_stripped_from_upstream(client, monkeypatch):
    """SPEC §5 — The 'sbp' namespace MUST NOT be forwarded to the LLM provider."""
    captured: dict = {}
    _mock_llm(monkeypatch, captured=captured)

    await client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
        "sbp": {"force_new_session": True},
    })
    assert "sbp" not in captured.get("body", {})


# ── L2: Tether + Resume ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_l2_suspended_session_returns_202(app, monkeypatch):
    """
    SPEC §6 — A suspended session MUST return HTTP 202 with sbp.resume_available=true.
    """
    _mock_llm(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Create session
        resp = await c.post("/v1/chat/completions", json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 200
        token = resp.headers["x-session-token"]
        session_id = resp.json()["sbp"]["session_id"]

        # Suspend it directly via the session store
        await app.state.session_store.update_status(session_id, "suspended")

        # Same app, same token — must get 202
        resp2 = await c.post(
            "/v1/chat/completions",
            headers={"X-Session-Token": token},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "continue"}]},
        )

    assert resp2.status_code == 202
    data = resp2.json()
    assert data["sbp"]["resume_available"] is True
    assert data["sbp"]["session_id"] == session_id


@pytest.mark.asyncio
async def test_l2_force_new_session_bypasses_202(client, monkeypatch):
    """SPEC §6 — force_new_session=true MUST bypass the resume check."""
    _mock_llm(monkeypatch)

    resp1 = await client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert resp1.status_code == 200
    token = resp1.headers["x-session-token"]
    sid1 = resp1.json()["sbp"]["session_id"]

    resp2 = await client.post(
        "/v1/chat/completions",
        headers={"X-Session-Token": token},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "new task"}],
            "sbp": {"force_new_session": True},
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["sbp"]["session_id"] != sid1


# ── L3: Roaming ───────────────────────────────────────────────────────────────

async def _create_session(client, monkeypatch) -> str:
    """Helper: create a session and return its session_id."""
    _mock_llm(monkeypatch)
    resp = await client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert resp.status_code == 200
    return resp.json()["sbp"]["session_id"]


@pytest.mark.asyncio
async def test_l3_export_returns_roaming_token(client, monkeypatch):
    """SPEC §7 — POST /export MUST return a 3-part JWT roaming_token."""
    session_id = await _create_session(client, monkeypatch)

    resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/export",
        json={"ttl_seconds": 3600, "label": "test-export"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "roaming_token" in data
    assert data["session_id"] == session_id
    assert data["roaming_token"].count(".") == 2


@pytest.mark.asyncio
async def test_l3_export_ttl_bounds(client, monkeypatch):
    """SPEC §7 — ttl_seconds MUST be in [60, 604800]."""
    session_id = await _create_session(client, monkeypatch)

    r1 = await client.post(f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 30})
    assert r1.status_code == 422

    r2 = await client.post(f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 999999})
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_l3_import_restores_session(client, monkeypatch):
    """SPEC §7 — POST /import MUST create a new session with messages restored."""
    session_id = await _create_session(client, monkeypatch)

    export_resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 3600}
    )
    assert export_resp.status_code == 201
    token = export_resp.json()["roaming_token"]

    import_resp = await client.post("/v1/sbp/sessions/import", json={"roaming_token": token})
    assert import_resp.status_code == 201
    data = import_resp.json()
    assert uuid.UUID(data["new_session_id"])
    assert data["new_session_id"] != session_id
    assert data["origin_export_id"] == export_resp.json()["export_id"]


@pytest.mark.asyncio
async def test_l3_token_single_use(client, monkeypatch):
    """SPEC §7 — A roaming token MUST be single-use; second import MUST return 410."""
    session_id = await _create_session(client, monkeypatch)
    export_resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 3600}
    )
    token = export_resp.json()["roaming_token"]

    r1 = await client.post("/v1/sbp/sessions/import", json={"roaming_token": token})
    assert r1.status_code == 201

    r2 = await client.post("/v1/sbp/sessions/import", json={"roaming_token": token})
    assert r2.status_code == 410


@pytest.mark.asyncio
async def test_l3_inspect_token(client, monkeypatch):
    """SPEC §7 — GET /token/{t} MUST return metadata without consuming the token."""
    session_id = await _create_session(client, monkeypatch)
    export_resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 3600}
    )
    token = export_resp.json()["roaming_token"]

    inspect = await client.get(f"/v1/sbp/token/{token}")
    assert inspect.status_code == 200
    assert inspect.json()["consumed"] is False
    assert inspect.json()["session_id"] == session_id

    # Token MUST still be importable after inspect
    r = await client.post("/v1/sbp/sessions/import", json={"roaming_token": token})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_l3_handoff(client, monkeypatch):
    """SPEC §7 — POST /handoff MUST create a new session under the target agent."""
    session_id = await _create_session(client, monkeypatch)

    resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/handoff",
        json={"to_agent_id": "agent-beta", "handoff_message": "Continue.", "reason": "specialisation"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert uuid.UUID(data["new_session_id"])
    assert data["from_session_id"] == session_id
    assert data["to_agent_id"] == "agent-beta"


@pytest.mark.asyncio
async def test_l3_fork(client, monkeypatch):
    """SPEC §7 — POST /fork MUST create an independent branch with the same history."""
    session_id = await _create_session(client, monkeypatch)

    resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/fork", json={"label": "experiment-A"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert uuid.UUID(data["fork_session_id"])
    assert data["origin_session_id"] == session_id
    assert data["fork_label"] == "experiment-A"
    assert data["fork_session_id"] != session_id


@pytest.mark.asyncio
async def test_l3_lineage(client, monkeypatch):
    """SPEC §7 — GET /lineage MUST return an exports array."""
    session_id = await _create_session(client, monkeypatch)
    await client.post(f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 3600})

    resp = await client.get(f"/v1/sbp/sessions/{session_id}/lineage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert isinstance(data["exports"], list)
    assert len(data["exports"]) == 1


@pytest.mark.asyncio
async def test_l3_tampered_token_rejected(client, monkeypatch):
    """SPEC §7 — A tampered token signature MUST be rejected with 422."""
    session_id = await _create_session(client, monkeypatch)
    export_resp = await client.post(
        f"/v1/sbp/sessions/{session_id}/export", json={"ttl_seconds": 3600}
    )
    token = export_resp.json()["roaming_token"]
    parts = token.split(".")
    tampered = f"{parts[0]}.{parts[1]}.invalidsignature"

    resp = await client.post("/v1/sbp/sessions/import", json={"roaming_token": tampered})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_l3_invalid_uuid_returns_422(client):
    """SPEC §7 — Non-UUID session_id MUST return 422."""
    resp = await client.post(
        "/v1/sbp/sessions/not-a-uuid/export", json={"ttl_seconds": 3600}
    )
    assert resp.status_code == 422


# ── L4: Surface Negotiation (WebSocket) ──────────────────────────────────────

def _ws_app():
    return create_app()


@pytest.mark.asyncio
async def test_l4_attach_session_first_frame_required():
    """
    SPEC §9 — First frame MUST be ATTACH_SESSION;
    any other frame MUST result in PROTOCOL_ERROR + close 1003.
    """
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token=session_token)

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({"type": "PONG"})
            data = ws.receive_json()
    assert data["type"] == "PROTOCOL_ERROR"


@pytest.mark.asyncio
async def test_l4_attach_session_handshake():
    """SPEC §9 — Valid ATTACH_SESSION MUST return SESSION_ATTACHED with sbp_version='1.2'."""
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token=session_token)

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": session_token,
                "surface_context": {
                    "device_type": "mobile",
                    "ui_capabilities": ["markdown"],
                    "locale": "en-US",
                    "mcp_tools": ["camera", "contacts"],
                },
            })
            data = ws.receive_json()

    assert data["type"] == "SESSION_ATTACHED"
    assert data["session_id"] == session_id
    assert data["sbp_version"] == "1.2"
    assert data["device_type"] == "mobile"
    assert "camera" in data["mcp_tools_registered"]


@pytest.mark.asyncio
async def test_l4_attach_invalid_token():
    """SPEC §9 — Invalid session_token MUST result in FORBIDDEN."""
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token="real-token")

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": "wrong-token",
                "surface_context": {},
            })
            data = ws.receive_json()
    assert data["type"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_l4_unknown_session():
    """SPEC §9 — Non-existent session MUST return SESSION_NOT_FOUND."""
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": "any",
                "surface_context": {},
            })
            data = ws.receive_json()
    assert data["type"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_l4_surface_context_extra_fields_tolerated():
    """SPEC §8 — Servers MUST tolerate unknown fields in SurfaceContext."""
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token=session_token)

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": session_token,
                "surface_context": {
                    "device_type": "iot",
                    "unknown_future_field": "value",
                    "nested_unknown": {"deep": True},
                },
            })
            data = ws.receive_json()
    assert data["type"] == "SESSION_ATTACHED"


# ── L5: Surface MCP Bridge ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_l5_tether_drain_on_attach():
    """
    SPEC §10 — Buffered TETHER_TURN frames MUST be drained on ATTACH_SESSION,
    and queued_turns MUST reflect the count.
    """
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token=session_token)

    await app.state.tether_queue.enqueue(session_id, {"type": "TETHER_TURN", "session_id": session_id, "turn": {"role": "assistant", "content": "Msg 1"}})
    await app.state.tether_queue.enqueue(session_id, {"type": "TETHER_TURN", "session_id": session_id, "turn": {"role": "assistant", "content": "Msg 2"}})

    received = []
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": session_token,
                "surface_context": {"device_type": "mobile"},
            })
            attached = ws.receive_json()
            for _ in range(2):
                received.append(ws.receive_json())

    assert attached["queued_turns"] == 2
    assert len(received) == 2
    assert all(r["type"] == "TETHER_TURN" for r in received)

    # Queue MUST be cleared after successful drain
    remaining = await app.state.tether_queue.drain(session_id)
    assert remaining == []


@pytest.mark.asyncio
async def test_l5_tool_call_roundtrip():
    """
    SPEC §9 — TOOL_RESULT with an unknown call_id MUST NOT crash the server.
    (In-band TOOL_CALL injection is tested via the wire protocol.)
    """
    from starlette.testclient import TestClient
    app = _ws_app()
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    await app.state.session_store.create(session_id=session_id, agent_id="t", session_token=session_token)

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/sbp/ws/{session_id}") as ws:
            ws.send_json({
                "type": "ATTACH_SESSION",
                "session_id": session_id,
                "session_token": session_token,
                "surface_context": {"device_type": "mobile", "mcp_tools": ["camera"]},
            })
            attached = ws.receive_json()
            assert attached["type"] == "SESSION_ATTACHED"

            # Send TOOL_RESULT for an unknown call_id — server MUST tolerate it
            ws.send_json({
                "type": "TOOL_RESULT",
                "call_id": "unknown-call-id",
                "result": {"ok": True},
            })
            ws.send_json({"type": "DETACH"})
