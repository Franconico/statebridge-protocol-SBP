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

import logging
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from sbp_server.models.completions import (
    ChatCompletionRequest,
    ResumeAvailableResponse,
    SBPResponseMeta,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_LLM_BASE_URL = os.environ.get("SBP_LLM_BASE_URL", "").rstrip("/")
_LLM_API_KEY = os.environ.get("SBP_LLM_API_KEY", "")
_DEFAULT_MODEL = os.environ.get("SBP_DEFAULT_MODEL", "gpt-4o")


def _llm_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if _LLM_API_KEY:
        h["Authorization"] = f"Bearer {_LLM_API_KEY}"
    return h


async def _proxy_streaming(
    messages: list[dict],
    request_dict: dict,
    session_id: str,
    session_token: str,
) -> Any:
    """Yield SSE chunks from the upstream LLM, prepending the session header."""
    url = f"{_LLM_BASE_URL}/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=request_dict, headers=_llm_headers()) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk


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

    # ── L2: Resume check — return HTTP 202 if a suspended session exists ──────
    if not body.sbp.force_new_session and x_session_token:
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
        request_dict["model"] = _DEFAULT_MODEL

    if not _LLM_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SBP_LLM_BASE_URL is not configured",
        )

    # ── Streaming path ────────────────────────────────────────────────────────
    if body.stream:
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
    url = f"{_LLM_BASE_URL}/chat/completions"
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=request_dict, headers=_llm_headers())

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

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

    # ── Append SBP metadata to response ──────────────────────────────────────
    response_dict["sbp"] = SBPResponseMeta(
        session_id=session_id,
        snapshot_id=snapshot_id,
        step_count=step_count,
        model_routed_to=actual_model,
    ).model_dump()

    return JSONResponse(
        content=response_dict,
        headers={"X-Session-Token": session["session_token"]},
    )
