"""
In-memory backend — development only.

Implements SessionStore, TetherQueue, SnapshotStore, and RoamingTokenStore
using plain Python dicts. Zero dependencies beyond the standard library.

IMPORTANT LIMITATIONS:
  - State is lost on process restart.
  - Not safe for multi-process or multi-replica deployments.
  - consume() is NOT atomic under concurrent coroutines (asyncio is single-
    threaded so it's safe within one process, but not across processes).

Use this backend for local development and the conformance test suite.
For production, see: https://silkbridge.io/enterprise
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._by_token: dict[str, str] = {}
        self._messages: dict[str, list[dict[str, Any]]] = {}

    async def create(
        self,
        session_id: str,
        agent_id: str,
        session_token: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session: dict[str, Any] = {
            "id": session_id,
            "agent_id": agent_id,
            "session_token": session_token,
            "status": "idle",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }
        self._sessions[session_id] = session
        self._by_token[session_token] = session_id
        self._messages[session_id] = []
        return session

    async def get(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    async def get_by_token(self, session_token: str) -> dict[str, Any] | None:
        sid = self._by_token.get(session_token)
        return self._sessions.get(sid) if sid else None

    async def update_status(self, session_id: str, status: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = status
            self._sessions[session_id]["updated_at"] = datetime.now(UTC).isoformat()

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._messages.get(session_id, []))

    async def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        self._messages.setdefault(session_id, []).append(message)

    async def delete(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            self._by_token.pop(session.get("session_token", ""), None)
        self._messages.pop(session_id, None)


class InMemoryTetherQueue:
    def __init__(self) -> None:
        self._queues: dict[str, list[dict[str, Any]]] = {}

    async def enqueue(self, session_id: str, turn: dict[str, Any]) -> None:
        self._queues.setdefault(session_id, []).append(turn)

    async def drain(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._queues.get(session_id, []))

    async def clear(self, session_id: str) -> None:
        self._queues.pop(session_id, None)


class InMemorySnapshotStore:
    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._latest: dict[str, str] = {}

    async def write(
        self,
        session_id: str,
        snapshot: dict[str, Any],
        *,
        snapshot_type: str = "checkpoint",
    ) -> str:
        snapshot_id = str(uuid.uuid4())
        record = {
            "id": snapshot_id,
            "session_id": session_id,
            "snapshot_type": snapshot_type,
            "state": snapshot,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._snapshots[snapshot_id] = record
        self._latest[session_id] = snapshot_id
        return snapshot_id

    async def latest(self, session_id: str) -> dict[str, Any] | None:
        sid = self._latest.get(session_id)
        return self._snapshots.get(sid) if sid else None

    async def get(self, snapshot_id: str) -> dict[str, Any] | None:
        return self._snapshots.get(snapshot_id)


class InMemoryRoamingTokenStore:
    def __init__(self) -> None:
        self._exports: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def record_export(
        self,
        export_id: str,
        bundle: dict[str, Any],
        *,
        expires_at: float,
        session_id: str,
        label: str | None = None,
    ) -> None:
        self._exports[export_id] = {
            "export_id": export_id,
            "session_id": session_id,
            "bundle": bundle,
            "expires_at": expires_at,
            "label": label,
            "consumed_at": None,
            "import_session_id": None,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def consume(self, export_id: str) -> dict[str, Any] | None:
        async with self._lock:
            record = self._exports.get(export_id)
            if record is None or record["consumed_at"] is not None:
                return None
            record["consumed_at"] = datetime.now(UTC).isoformat()
            return record

    async def inspect(self, export_id: str) -> dict[str, Any] | None:
        record = self._exports.get(export_id)
        if not record:
            return None
        return {k: v for k, v in record.items() if k != "bundle"}

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in r.items() if k != "bundle"}
            for r in self._exports.values()
            if r["session_id"] == session_id
        ]


def make_in_memory_backends() -> tuple[
    InMemorySessionStore,
    InMemoryTetherQueue,
    InMemorySnapshotStore,
    InMemoryRoamingTokenStore,
]:
    """Return a fresh set of in-memory backend instances."""
    return (
        InMemorySessionStore(),
        InMemoryTetherQueue(),
        InMemorySnapshotStore(),
        InMemoryRoamingTokenStore(),
    )
