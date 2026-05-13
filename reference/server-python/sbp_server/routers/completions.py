"""
POST /v1/chat/completions — SBP L1/L2 stateful proxy.

Wraps any OpenAI-compatible LLM endpoint with SBP session management:
  - Resolves or creates a session for the caller
  - Returns a suspended session as HTTP 202 if one exists
  - Proxies the request to SBP_LLM_BASE_URL with the SBP 'sbp' namespace stripped
  - Appends an 'sbp' namespace to the response with session metadata

SBP is model-agnostic: set SBP_LLM_BASE_URL to point at OpenAI, Anthropic,
a local Ollama instance, a vLLM deployment, or any other provider.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from sbp_server.ws_connection_manager import manager

from sbp_server.models.completions import (
    ChatCompletionRequest,
    ResumeAvailableResponse,
    SBPResponseMeta,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _llm_base_url() -> str:
    return os.environ.get("SBP_LLM_BASE_URL", "").rstrip("/")


def _llm_headers() -> dict[str, str]:
    key = os.environ.get("SBP_LLM_API_KEY", "")
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _default_model() -> str:
    return os.environ.get("SBP_DEFAULT_MODEL", "gpt-4o")


async def _call_llm(url: str, request_dict: dict) -> httpx.Response:
    """
    Make a single non-streaming POST to the configured LLM endpoint.
    Extracted for testability — tests monkeypatch this function directly.
    Raises HTTP 503 on connection failure.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            return await client.post(url, json=request_dict, headers=_llm_headers())
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach LLM endpoint ({url}): {exc}",
        )


async def _proxy_streaming(
    messages: list[dict],
    request_dict: dict,
    session_id: str,
    session_token: str,
) -> Any:
    """Yield SSE chunks from the upstream LLM (plain HTTP streaming path)."""
    url = f"{_llm_base_url()}/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=request_dict, headers=_llm_headers()) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk


async def _stream_to_websocket(
    session_id: str,
    request_dict: dict,
    session_store: Any,
    tether_queue: Any,
) -> None:
    """
    Stream LLM output as TURN_CHUNK frames to an attached WebSocket surface.

    If the surface disconnects mid-stream, the server keeps consuming from the
    LLM and queues the accumulated content as a TETHER_TURN so nothing is lost.
    This is The Tether in action: the agent keeps thinking even when the surface
    goes offline.
    """
    url = f"{_llm_base_url()}/chat/completions"
    accumulated: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", url, json=request_dict, headers=_llm_headers()
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = (
                            (chunk.get("choices") or [{}])[0]
                            .get("delta", {})
                            .get("content") or ""
                        )
                        if not content:
                            continue
                        accumulated.append(content)
                        if manager.is_connected(session_id):
                            await manager.send(session_id, {
                                "type": "TURN_CHUNK",
                                "session_id": session_id,
                                "content": content,
                            })
                    except Exception:
                        continue
    except Exception as exc:
        logger.warning("SBP stream_to_ws error session=%s err=%s", session_id, exc)

    full_content = "".join(accumulated)
    if not full_content:
        return

    # Persist assistant message
    await session_store.append_message(session_id, {
        "role": "assistant",
        "content": full_content,
    })

    if manager.is_connected(session_id):
        # Surface still live — signal stream end
        await manager.send(session_id, {
            "type": "TURN_COMPLETE",
            "session_id": session_id,
        })
    else:
        # Surface went offline mid-stream — queue for next reconnect
        logger.info("SBP Tether queuing streamed turn session=%s chars=%d",
                    session_id, len(full_content))
        await tether_queue.enqueue(session_id, {
            "type": "TETHER_TURN",
            "session_id": session_id,
            "content": full_content,
        })


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
    x_agent_id: str | None = Header(default=None, alias="X-Agent-ID"),
):
    session_store = request.app.state.session_store
    snapshot_store = request.app.state.snapshot_store

    agent_id = x_agent_id or "anonymous"

    # ── L2: Resume check — 202 only when no new messages (status probe) ─────────
    # If the client sends new messages alongside a suspended session token, we
    # process them normally and queue the response in the Tether (L2 buffering).
    # 202 is reserved for clients that explicitly probe session status without
    # sending new content (e.g. a reconnect check before attaching a surface).
    if not body.sbp.force_new_session and x_session_token and not body.messages:
        session = await session_store.get_by_token(x_session_token)
        if session and session.get("status") == "suspended":
            snapshot = await snapshot_store.latest(session["id"])
            last_checkpoint = (
                snapshot["created_at"] if snapshot else None
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=ResumeAvailableResponse(
                    sbp=SBPResponseMeta(
                        session_id=session["id"],
                        resume_available=True,
                        resume_prompt=(
                            "A suspended session was found. "
                            "Reply with 'continue' to resume, or send a new task."
                        ),
                        last_checkpoint=last_checkpoint,
                    )
                ).model_dump(),
            )

    # ── Load or create session ────────────────────────────────────────────────
    session: dict[str, Any] | None = None
    if x_session_token and not body.sbp.force_new_session:
        session = await session_store.get_by_token(x_session_token)
        if session and session.get("status") == "suspended":
            await session_store.update_status(session["id"], "active")

    if session is None:
        session_id = str(uuid.uuid4())
        token = x_session_token or str(uuid.uuid4())
        session = await session_store.create(
            session_id=session_id,
            agent_id=agent_id,
            session_token=token,
        )
        await session_store.update_status(session_id, "active")

    session_id = session["id"]

    # ── Append the user message ───────────────────────────────────────────────
    messages = [m.model_dump(exclude_none=True) for m in body.messages]
    for msg in messages:
        await session_store.append_message(session_id, msg)

    # ── Build upstream request — strip 'sbp' namespace ───────────────────────
    request_dict = body.model_dump(exclude={"sbp"}, exclude_none=True)
    if not request_dict.get("model"):
        request_dict["model"] = _default_model()

    base_url = _llm_base_url()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SBP_LLM_BASE_URL is not configured",
        )

    # ── Streaming path ────────────────────────────────────────────────────────
    if body.stream:
        if manager.is_connected(session_id):
            # Surface is live — stream chunks as TURN_CHUNK frames over WebSocket.
            # If the surface disconnects mid-stream, the background task switches
            # to Tether queuing automatically so nothing is lost.
            asyncio.create_task(
                _stream_to_websocket(
                    session_id,
                    request_dict,
                    session_store,
                    request.app.state.tether_queue,
                )
            )
            # Return immediately so the curl caller gets an ack, not an HTTP stream.
            return Response(
                content=json.dumps({
                    "sbp": {
                        "session_id": session_id,
                        "session_token": session["session_token"],
                        "streaming": "websocket",
                    }
                }),
                media_type="application/json",
                headers={"X-Session-Token": session["session_token"]},
            )
        # No surface attached — fall back to plain HTTP SSE stream.
        return StreamingResponse(
            _proxy_streaming(messages, request_dict, session_id, session["session_token"]),
            media_type="text/event-stream",
            headers={
                "X-Session-Token": session["session_token"],
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # ── Non-streaming path ────────────────────────────────────────────────────
    url = f"{base_url}/chat/completions"
    t0 = time.monotonic()
    resp = await _call_llm(url, request_dict)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text.replace("\n", " ")
        raise HTTPException(status_code=resp.status_code, detail=detail)

    response_dict = resp.json()

    # ── Extract assistant message and persist it ──────────────────────────────
    choices = response_dict.get("choices") or []
    assistant_content = (
        (choices[0].get("message") or {}).get("content") or "" if choices else ""
    )
    actual_model = response_dict.get("model") or request_dict.get("model")
    usage = response_dict.get("usage") or {}

    if assistant_content:
        await session_store.append_message(session_id, {
            "role": "assistant",
            "content": assistant_content,
            "model_used": actual_model,
        })

    # ── Snapshot (L2: checkpoint_every) ──────────────────────────────────────
    all_messages = await session_store.list_messages(session_id)
    step_count = sum(1 for m in all_messages if m.get("role") == "assistant")
    snapshot_id: str | None = None
    if step_count > 0 and (step_count % body.sbp.checkpoint_every == 0):
        snapshot_id = await snapshot_store.write(
            session_id,
            {"messages": all_messages, "step": step_count},
            snapshot_type="checkpoint",
        )

    # ── Tether: push to live surface or queue for later drain (L2) ───────────
    if assistant_content:
        turn_frame = {
            "type": "TETHER_TURN",
            "session_id": session_id,
            "content": assistant_content,
            "model": actual_model,
            "step_count": step_count,
        }
        if manager.is_connected(session_id):
            # Surface is live — push directly to the WebSocket
            await manager.send(session_id, turn_frame)
        else:
            # Surface offline — queue for the next ATTACH_SESSION drain
            await request.app.state.tether_queue.enqueue(session_id, turn_frame)

    # ── Append SBP metadata to response ──────────────────────────────────────
    response_dict["sbp"] = SBPResponseMeta(
        session_id=session_id,
        session_token=session["session_token"],
        snapshot_id=snapshot_id,
        step_count=step_count,
        model_routed_to=actual_model,
    ).model_dump()

    return Response(
        content=json.dumps(response_dict, ensure_ascii=True),
        media_type="application/json",
        headers={"X-Session-Token": session["session_token"]},
    )
