"""
SBP Backend Protocol interfaces.

Implement these four protocols to plug in any storage backend.
The default implementation (memory.py) uses in-process dicts and is
suitable for development only — it loses all state on restart.

For production, see: https://silkbridge.io/enterprise
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SessionStore(Protocol):
    """Persistent store for SBP session records."""

    async def create(
        self,
        session_id: str,
        agent_id: str,
        session_token: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new session record.

        Returns the created session dict with at minimum:
          id, agent_id, session_token, status, created_at
        """
        ...

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Return the session dict or None if not found."""
        ...

    async def get_by_token(self, session_token: str) -> dict[str, Any] | None:
        """Return the session dict keyed by session_token, or None."""
        ...

    async def update_status(self, session_id: str, status: str) -> None:
        """
        Update session lifecycle status.
        Valid transitions: idle → active → suspended → completed | failed
        """
        ...

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return all messages for a session in chronological order."""
        ...

    async def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Append a message to the session history."""
        ...

    async def delete(self, session_id: str) -> None:
        """Permanently remove a session and all associated data."""
        ...


@runtime_checkable
class TetherQueue(Protocol):
    """
    Durable queue that buffers TETHER_TURN frames while a surface is offline.

    MUST be durable and cross-replica in production deployments.
    The in-memory default (memory.py) is single-process only — correct for
    development, but will lose buffered turns on process restart or pod replacement.

    Implementations MUST guarantee at-least-once delivery: a turn enqueued
    before a drain call MUST appear in the drain result.
    """

    async def enqueue(self, session_id: str, turn: dict[str, Any]) -> None:
        """Buffer a TETHER_TURN frame for delivery when the surface reconnects."""
        ...

    async def drain(self, session_id: str) -> list[dict[str, Any]]:
        """
        Return all buffered turns for a session in enqueue order.
        Does NOT clear the queue — call clear() after successful delivery.
        """
        ...

    async def clear(self, session_id: str) -> None:
        """Remove all buffered turns after successful drain-and-deliver."""
        ...


@runtime_checkable
class SnapshotStore(Protocol):
    """
    Store for agent state snapshots (pre-action, post-action, checkpoint).

    Snapshots are used to resume sessions after a disconnect or hand off
    state to another agent.
    """

    async def write(
        self,
        session_id: str,
        snapshot: dict[str, Any],
        *,
        snapshot_type: str = "checkpoint",
    ) -> str:
        """
        Persist a snapshot. Returns the snapshot_id.

        snapshot_type SHOULD be one of:
          pre_action, post_action, checkpoint, crash_recovery
        """
        ...

    async def latest(self, session_id: str) -> dict[str, Any] | None:
        """Return the most recent snapshot for a session, or None."""
        ...

    async def get(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return a specific snapshot by ID, or None."""
        ...


@runtime_checkable
class RoamingTokenStore(Protocol):
    """
    Store for roaming token bundles.

    A bundle is a full session export: messages, memory, state snapshot, provenance.
    Tokens are single-use by default; implementations MUST enforce this atomically.
    """

    async def record_export(
        self,
        export_id: str,
        bundle: dict[str, Any],
        *,
        expires_at: float,
        session_id: str,
        label: str | None = None,
    ) -> None:
        """Persist an export bundle keyed by export_id."""
        ...

    async def consume(self, export_id: str) -> dict[str, Any] | None:
        """
        Atomically mark a bundle as consumed and return it.

        Returns None if not found or already consumed.
        MUST be atomic — concurrent consume calls for the same export_id
        MUST result in exactly one returning the bundle and the rest returning None.
        """
        ...

    async def inspect(self, export_id: str) -> dict[str, Any] | None:
        """
        Return bundle metadata without consuming or marking it.

        Returns dict with at minimum:
          export_id, session_id, expires_at, consumed_at, label
        Or None if not found.
        """
        ...

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return all export records (active and consumed) for a session."""
        ...
