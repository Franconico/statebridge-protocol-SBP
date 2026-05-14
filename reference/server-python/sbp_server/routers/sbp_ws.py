"""
SBP L4/L5 WebSocket endpoint.

ws://host/v1/sbp/ws/{session_id}

Protocol sequence:
  1. Client opens WebSocket
  2. Client sends ATTACH_SESSION frame (MUST be first message)
  3. Server validates session_token
  4. Server sends SESSION_ATTACHED (includes queued_turns count)
  5. Server drains Tether queue and streams TETHER_TURN frames
  6. Server signals TetherQueue to clear
  7. Bidirectional loop: server pushes TETHER_TURN; client pushes TOOL_RESULT
  8. Client sends DETACH (or drops) → server re-activates Tether buffering

Frame types (server → client):
  SESSION_ATTACHED  — handshake success
  SESSION_NOT_FOUND — no session with that ID
  FORBIDDEN         — session_token invalid
  PROTOCOL_ERROR    — unexpected frame type
  TETHER_TURN       — buffered turn delivered on reconnect
  TURN_CHUNK        — streaming chunk (for streaming LLM responses)
  TURN_COMPLETE     — stream finished
  TOOL_CALL         — gateway asks surface to execute a local MCP tool (L5)
  PING              — keepalive

Frame types (client → server):
  ATTACH_SESSION    — must be first frame
  DETACH            — graceful disconnect
  TOOL_RESULT       — reply to a TOOL_CALL (L5)
  PONG              — reply to PING
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sbp_server.ws_connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{session_id}")
async def sbp_websocket(session_id: str, ws: WebSocket) -> None:
    """SBP live surface attachment endpoint (L4/L5)."""
    await ws.accept()

    # WebSocket inherits from HTTPConnection; app state is accessible via ws.app.state
    session_store = ws.app.state.session_store
    tether_queue = ws.app.state.tether_queue

    # ── Receive and validate ATTACH_SESSION ───────────────────────────────────
    try:
        frame = await ws.receive_json()
    except Exception as exc:
        logger.warning("SBP WS: failed to receive first frame session=%s err=%s",
                       session_id, exc)
        await ws.close(code=1003)
        return

    if frame.get("type") != "ATTACH_SESSION":
        await ws.send_json({
            "type": "PROTOCOL_ERROR",
            "detail": (
                f"Expected ATTACH_SESSION as first frame, got '{frame.get('type')}'. "
                "Close and reconnect with ATTACH_SESSION."
            ),
        })
        await ws.close(code=1003)
        return

    session_id_claim = frame.get("session_id", "")
    session_token = frame.get("session_token", "")
    surface_raw = frame.get("surface_context", {})

    if session_id_claim != session_id:
        await ws.send_json({
            "type": "PROTOCOL_ERROR",
            "detail": "session_id in frame does not match URL path parameter",
        })
        await ws.close(code=1003)
        return

    # ── Validate session ownership ────────────────────────────────────────────
    session = await session_store.get(session_id)
    if not session:
        await ws.send_json({"type": "SESSION_NOT_FOUND", "session_id": session_id})
        await ws.close(code=4004)
        return

    if session.get("session_token") != session_token:
        await ws.send_json({"type": "FORBIDDEN", "detail": "session_token invalid"})
        await ws.close(code=4003)
        return

    # ── Parse surface context ─────────────────────────────────────────────────
    from sbp_server.models.completions import SurfaceContext
    try:
        surface = SurfaceContext(**surface_raw)
    except Exception:
        surface = SurfaceContext()

    surface_dict = surface.model_dump()
    manager.register(session_id, ws, surface_dict)
    await session_store.update_status(session_id, "active")

    # ── Drain Tether queue (L2 Resume) ────────────────────────────────────────
    tether_turns = await tether_queue.drain(session_id)

    # ── Acknowledge handshake ─────────────────────────────────────────────────
    await ws.send_json({
        "type": "SESSION_ATTACHED",
        "session_id": session_id,
        "surface_id": surface.surface_id,
        "device_type": surface.device_type,
        "queued_turns": len(tether_turns),
        "mcp_tools_registered": surface.mcp_tools,
        "sbp_version": "0.9",
    })

    # ── Stream buffered Tether turns ──────────────────────────────────────────
    if tether_turns:
        drained = 0
        for turn in tether_turns:
            try:
                await ws.send_json(turn)
                drained += 1
            except Exception:
                logger.warning(
                    "SBP Tether drain interrupted at turn %d/%d session=%s",
                    drained, len(tether_turns), session_id,
                )
                break
        await tether_queue.clear(session_id)
        logger.info("SBP Tether drained %d/%d turns session=%s",
                    drained, len(tether_turns), session_id)

    logger.info("SBP WS ready session=%s device=%s tools=%s",
                session_id, surface.device_type, surface.mcp_tools)

    # ── Bidirectional loop ────────────────────────────────────────────────────
    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")

            if msg_type == "DETACH":
                logger.info("SBP WS graceful detach session=%s", session_id)
                break

            elif msg_type == "PONG":
                pass  # keepalive reply — no action needed

            elif msg_type == "TOOL_RESULT":
                # L5: surface returns MCP tool output
                call_id = msg.get("call_id", "")
                error = msg.get("error")
                result_payload = (
                    {"error": error, "call_id": call_id}
                    if error
                    else {"output": msg.get("result", {}), "call_id": call_id}
                )
                manager.resolve_tool_call(call_id, result_payload)

            else:
                # Unknown frame type — log and ignore (forward-compatible)
                logger.debug("SBP WS unknown frame type=%s session=%s", msg_type, session_id)

    except WebSocketDisconnect:
        logger.info("SBP WS disconnected session=%s", session_id)

    except Exception as exc:
        logger.warning("SBP WS error session=%s err=%s", session_id, exc)

    finally:
        manager.disconnect(session_id)
        # Re-activate Tether — buffer future output turns for next surface attach
        await session_store.update_status(session_id, "suspended")
