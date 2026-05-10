"""
SBP L3 Roaming — REST endpoints.

POST /v1/sbp/sessions/{id}/export     — snapshot session → roaming token
POST /v1/sbp/sessions/import          — restore roaming token → new session
GET  /v1/sbp/token/{token}            — inspect a roaming token
POST /v1/sbp/sessions/{id}/handoff    — transfer session to another agent
POST /v1/sbp/sessions/{id}/fork       — branch session at current checkpoint
GET  /v1/sbp/sessions/{id}/exports    — list all exports for a session
GET  /v1/sbp/sessions/{id}/lineage    — full session family tree
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from sbp_server.token import bundle_hash, sign_token, verify_token

router = APIRouter(tags=["sbp"])

_JWT_SECRET = os.environ.get("SBP_JWT_SECRET", "")
_BUNDLE_VERSION = "1.0"


# ── Request models ────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    label: str | None = Field(default=None, max_length=120)


class ImportRequest(BaseModel):
    roaming_token: str
    target_agent_id: str | None = None
    allow_reuse: bool = False


class HandoffRequest(BaseModel):
    to_agent_id: str
    handoff_message: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=500)


class ForkRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_secret() -> str:
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SBP_JWT_SECRET is not configured",
        )
    return _JWT_SECRET


def _validate_uuid(value: str, label: str = "ID") -> None:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {label}: '{value}' is not a valid UUID",
        )


async def _build_bundle(
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    snapshot: dict[str, Any] | None,
    export_id: str,
) -> dict[str, Any]:
    return {
        "sbp_version": _BUNDLE_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "session": {
            "id": session["id"],
            "agent_id": session.get("agent_id"),
            "status": session.get("status"),
            "created_at": session.get("created_at"),
        },
        "messages": messages,
        "memory": {},
        "state_snapshot": snapshot.get("state") if snapshot else None,
        "metadata": {
            "message_count": len(messages),
            "export_id": export_id,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/export", status_code=status.HTTP_201_CREATED)
async def export_session(session_id: str, req: ExportRequest, request: Request):
    """
    Snapshot the full state of a session into a signed, portable roaming token.
    """
    _validate_uuid(session_id)
    secret = _require_secret()

    session_store = request.app.state.session_store
    snapshot_store = request.app.state.snapshot_store
    roaming_store = request.app.state.roaming_store

    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    messages = await session_store.list_messages(session_id)
    snapshot = await snapshot_store.latest(session_id)
    export_id = str(uuid.uuid4())

    bundle = await _build_bundle(session, messages, snapshot, export_id)
    bundle["hash"] = bundle_hash(bundle)

    now = datetime.now(UTC).timestamp()
    exp = now + req.ttl_seconds

    token = sign_token(
        {"sub": export_id, "sid": session_id, "iat": int(now), "exp": int(exp)},
        secret,
    )

    await roaming_store.record_export(
        export_id=export_id,
        bundle=bundle,
        expires_at=exp,
        session_id=session_id,
        label=req.label,
    )

    return {
        "export_id": export_id,
        "roaming_token": token,
        "session_id": session_id,
        "expires_at": datetime.fromtimestamp(exp, UTC).isoformat(),
        "label": req.label,
        "message_count": len(messages),
    }


@router.post("/sessions/import", status_code=status.HTTP_201_CREATED)
async def import_session(req: ImportRequest, request: Request):
    """
    Import a roaming token, creating a new session with full context restored.
    """
    secret = _require_secret()

    try:
        payload = verify_token(req.roaming_token, secret)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    export_id = payload.get("sub", "")

    session_store = request.app.state.session_store
    roaming_store = request.app.state.roaming_store
    snapshot_store = request.app.state.snapshot_store

    if req.allow_reuse:
        record = await roaming_store.inspect(export_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Export not found")
        # Get bundle separately — inspect doesn't return it
        full_record = await roaming_store.consume(export_id)
        if full_record is None:
            # Already consumed; treat allow_reuse as fork — create a new export
            raise HTTPException(
                status_code=410,
                detail="Token already consumed. To fork, re-export from the original session.",
            )
        bundle = full_record["bundle"]
    else:
        record = await roaming_store.consume(export_id)
        if record is None:
            raise HTTPException(
                status_code=410,
                detail="Token not found or already consumed",
            )
        bundle = record["bundle"]

    # Verify bundle integrity
    stored_hash = bundle.pop("hash", None)
    if stored_hash and bundle_hash(bundle) != stored_hash:
        raise HTTPException(status_code=422, detail="Bundle integrity check failed")

    # Create new session from bundle
    new_session_id = str(uuid.uuid4())
    new_token = str(uuid.uuid4())
    agent_id = req.target_agent_id or bundle.get("session", {}).get("agent_id", "anonymous")

    new_session = await session_store.create(
        session_id=new_session_id,
        agent_id=agent_id,
        session_token=new_token,
        metadata={"origin_export_id": export_id},
    )

    # Replay messages
    for msg in bundle.get("messages", []):
        await session_store.append_message(new_session_id, msg)

    # Inject provenance message
    await session_store.append_message(new_session_id, {
        "role": "system",
        "content": f"[SBP] Session imported from export {export_id}. Context fully restored.",
    })

    # Restore snapshot
    if bundle.get("state_snapshot"):
        await snapshot_store.write(
            new_session_id,
            bundle["state_snapshot"],
            snapshot_type="checkpoint",
        )

    await session_store.update_status(new_session_id, "active")

    return {
        "new_session_id": new_session_id,
        "session_token": new_token,
        "origin_export_id": export_id,
        "messages_restored": len(bundle.get("messages", [])),
        "agent_id": agent_id,
    }


@router.get("/token/{roaming_token}")
async def inspect_token(roaming_token: str, request: Request):
    """Inspect a roaming token without consuming it."""
    secret = _require_secret()

    try:
        payload = verify_token(roaming_token, secret)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    export_id = payload.get("sub", "")
    roaming_store = request.app.state.roaming_store

    record = await roaming_store.inspect(export_id)
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")

    return {
        "export_id": export_id,
        "session_id": payload.get("sid"),
        "expires_at": datetime.fromtimestamp(payload["exp"], UTC).isoformat(),
        "consumed": record.get("consumed_at") is not None,
        "consumed_at": record.get("consumed_at"),
        "label": record.get("label"),
        "created_at": record.get("created_at"),
    }


@router.post("/sessions/{session_id}/handoff", status_code=status.HTTP_201_CREATED)
async def handoff_session(session_id: str, req: HandoffRequest, request: Request):
    """
    Transfer a session to a different agent with an optional bridge message.
    """
    _validate_uuid(session_id)
    secret = _require_secret()

    session_store = request.app.state.session_store
    snapshot_store = request.app.state.snapshot_store
    roaming_store = request.app.state.roaming_store

    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # Export source session
    messages = await session_store.list_messages(session_id)
    snapshot = await snapshot_store.latest(session_id)
    export_id = str(uuid.uuid4())
    bundle = await _build_bundle(session, messages, snapshot, export_id)
    bundle["hash"] = bundle_hash(bundle)

    now = datetime.now(UTC).timestamp()
    exp = now + 3600  # 1-hour token for handoff

    await roaming_store.record_export(
        export_id=export_id,
        bundle=bundle,
        expires_at=exp,
        session_id=session_id,
        label=f"handoff→{req.to_agent_id}",
    )

    # Create new session under target agent
    new_session_id = str(uuid.uuid4())
    new_token = str(uuid.uuid4())

    await session_store.create(
        session_id=new_session_id,
        agent_id=req.to_agent_id,
        session_token=new_token,
        metadata={"handoff_from": session_id, "origin_export_id": export_id},
    )

    for msg in messages:
        await session_store.append_message(new_session_id, msg)

    if req.handoff_message:
        await session_store.append_message(new_session_id, {
            "role": "system",
            "content": f"[SBP Handoff] {req.handoff_message}",
        })

    await session_store.append_message(new_session_id, {
        "role": "system",
        "content": (
            f"[SBP] Session handed off from agent '{session.get('agent_id')}'"
            f" to '{req.to_agent_id}'. Reason: {req.reason or 'not specified'}."
        ),
    })

    if snapshot:
        await snapshot_store.write(
            new_session_id,
            snapshot.get("state", {}),
            snapshot_type="checkpoint",
        )

    await session_store.update_status(new_session_id, "active")
    await session_store.update_status(session_id, "suspended")

    return {
        "new_session_id": new_session_id,
        "session_token": new_token,
        "from_session_id": session_id,
        "to_agent_id": req.to_agent_id,
        "origin_export_id": export_id,
    }


@router.post("/sessions/{session_id}/fork", status_code=status.HTTP_201_CREATED)
async def fork_session(session_id: str, req: ForkRequest, request: Request):
    """
    Create a parallel branch from the current session checkpoint.
    """
    _validate_uuid(session_id)

    session_store = request.app.state.session_store
    snapshot_store = request.app.state.snapshot_store

    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    messages = await session_store.list_messages(session_id)
    snapshot = await snapshot_store.latest(session_id)

    fork_session_id = str(uuid.uuid4())
    fork_token = str(uuid.uuid4())

    await session_store.create(
        session_id=fork_session_id,
        agent_id=session.get("agent_id", "anonymous"),
        session_token=fork_token,
        metadata={
            "fork_of": session_id,
            "fork_label": req.label,
            "fork_point_msg": len(messages),
        },
    )

    for msg in messages:
        await session_store.append_message(fork_session_id, msg)

    await session_store.append_message(fork_session_id, {
        "role": "system",
        "content": (
            f"[SBP] Session forked from '{session_id}'"
            + (f" ({req.label})" if req.label else "")
            + f" at message {len(messages)}."
        ),
    })

    if snapshot:
        await snapshot_store.write(
            fork_session_id,
            snapshot.get("state", {}),
            snapshot_type="checkpoint",
        )

    await session_store.update_status(fork_session_id, "active")

    return {
        "fork_session_id": fork_session_id,
        "session_token": fork_token,
        "origin_session_id": session_id,
        "fork_label": req.label,
        "fork_point_msg": len(messages),
    }


@router.get("/sessions/{session_id}/exports")
async def list_session_exports(session_id: str, request: Request):
    """List all state exports for a session."""
    _validate_uuid(session_id)

    session_store = request.app.state.session_store
    roaming_store = request.app.state.roaming_store

    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    exports = await roaming_store.list_for_session(session_id)
    return {"session_id": session_id, "exports": exports}


@router.get("/sessions/{session_id}/lineage")
async def get_session_lineage(session_id: str, request: Request):
    """Return the full family tree of a session."""
    _validate_uuid(session_id)

    session_store = request.app.state.session_store
    roaming_store = request.app.state.roaming_store

    session = await session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    exports = await roaming_store.list_for_session(session_id)

    # In the in-memory backend, lineage metadata is stored in session metadata
    metadata = {k: v for k, v in session.items()
                if k not in ("id", "agent_id", "session_token", "status",
                             "created_at", "updated_at")}

    origin = None
    if "fork_of" in metadata:
        origin = {
            "origin_session_id": metadata["fork_of"],
            "fork_label": metadata.get("fork_label"),
            "fork_point_msg": metadata.get("fork_point_msg"),
        }

    return {
        "session_id": session_id,
        "exports": exports,
        "outgoing_handoffs": [],
        "incoming_handoffs": (
            [{"from_session_id": metadata["handoff_from"]}]
            if "handoff_from" in metadata else []
        ),
        "forks": [],
        "origin": origin,
    }
