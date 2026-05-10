"""
WebSocket Connection Manager — SBP live surface registry.

Maintains an in-memory map of session_id → live WebSocket connection.
Provides:
  - register / disconnect lifecycle
  - send JSON frames to an attached surface
  - surface context lookup (device_type, mcp_tools, etc.)
  - MCP Tool Call Bridge: asyncio.Future-based TOOL_CALL / TOOL_RESULT rendezvous

NOTE ON THE TETHER QUEUE:
  The Tether queue does NOT live here. Buffering turns while a surface is
  offline belongs in a durable, cross-replica store (TetherQueue backend).
  This manager is purely a live-connection registry; it is process-local and
  loses all state on restart by design.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSConnectionManager:
    """
    In-memory registry: session_id → live WebSocket + surface metadata.

    For fan-out across replicas, a Redis pub/sub layer (or equivalent) would
    sit above this. The interface is designed to be drop-in replaceable.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._surface_ctx: dict[str, dict[str, Any]] = {}
        self._tool_futures: dict[str, asyncio.Future] = {}
        self._session_tool_calls: dict[str, set[str]] = {}

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def register(self, session_id: str, ws: WebSocket, surface: dict[str, Any]) -> None:
        """Register an accepted WebSocket for a session."""
        self._connections[session_id] = ws
        self._surface_ctx[session_id] = surface
        self._session_tool_calls.setdefault(session_id, set())
        logger.info(
            "SBP surface attached  session=%s device=%s mcp_tools=%s",
            session_id,
            surface.get("device_type", "unknown"),
            surface.get("mcp_tools", []),
        )

    def disconnect(self, session_id: str) -> None:
        """
        Remove a WebSocket from the registry.
        Surface context is retained for post-disconnect operations.
        Cancels any pending MCP tool call futures for this session.
        """
        if session_id in self._connections:
            del self._connections[session_id]
            logger.info("SBP surface detached  session=%s", session_id)

        for call_id in self._session_tool_calls.pop(session_id, set()):
            fut = self._tool_futures.pop(call_id, None)
            if fut and not fut.done():
                fut.cancel()
                logger.debug("SBP MCP call cancelled on disconnect call_id=%s", call_id)

    def is_connected(self, session_id: str) -> bool:
        return session_id in self._connections

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send(self, session_id: str, data: dict[str, Any]) -> bool:
        """Send a JSON frame. Returns True if delivered, False if no live connection."""
        ws = self._connections.get(session_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception as exc:
            logger.warning("WS send failed session=%s err=%s", session_id, exc)
            self.disconnect(session_id)
            return False

    # ── Surface context ───────────────────────────────────────────────────────

    def get_surface(self, session_id: str) -> dict[str, Any] | None:
        """Return the surface context dict for a session (even if disconnected)."""
        return self._surface_ctx.get(session_id)

    def clear_surface(self, session_id: str) -> None:
        """Remove surface context entirely (called on session completion)."""
        self._surface_ctx.pop(session_id, None)

    # ── MCP Tool Call Bridge (L5) ─────────────────────────────────────────────

    async def request_tool_call(
        self,
        session_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Send a TOOL_CALL frame to the surface and await its TOOL_RESULT reply.

        The call is given a unique call_id so concurrent tool calls can be
        multiplexed over the same WebSocket connection.

        Raises:
          RuntimeError  — if no live surface is connected for this session
          TimeoutError  — if the surface doesn't respond within `timeout` seconds
        """
        if not self.is_connected(session_id):
            raise RuntimeError(f"No live surface for session {session_id!r}")

        call_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._tool_futures[call_id] = fut
        self._session_tool_calls.setdefault(session_id, set()).add(call_id)

        sent = await self.send(session_id, {
            "type": "TOOL_CALL",
            "call_id": call_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        if not sent:
            self._tool_futures.pop(call_id, None)
            self._session_tool_calls.get(session_id, set()).discard(call_id)
            raise RuntimeError(f"Failed to deliver TOOL_CALL to session {session_id!r}")

        logger.info("SBP MCP tool_call session=%s tool=%s call_id=%s",
                    session_id, tool_name, call_id)

        try:
            result = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning("SBP MCP tool_call timeout session=%s call_id=%s",
                           session_id, call_id)
            raise TimeoutError(f"Surface tool call timed out: {tool_name!r}")
        finally:
            self._tool_futures.pop(call_id, None)
            self._session_tool_calls.get(session_id, set()).discard(call_id)

    def resolve_tool_call(self, call_id: str, result: dict[str, Any]) -> bool:
        """
        Called by the WebSocket router when a TOOL_RESULT frame arrives.
        Resolves the waiting Future created by request_tool_call().

        Returns True if the call_id was found and resolved, False otherwise.
        """
        fut = self._tool_futures.get(call_id)
        if fut is None:
            logger.warning("SBP MCP: TOOL_RESULT for unknown call_id=%s", call_id)
            return False
        if not fut.done():
            fut.set_result(result)
            logger.info("SBP MCP tool resolved call_id=%s", call_id)
            return True
        return False


# Process-level singleton imported by routers
manager = WSConnectionManager()
