"""
Pydantic models for the SBP stateful proxy.

The request body is OpenAI-compatible, extended with an 'sbp' namespace.
The response mirrors the OpenAI shape and appends an 'sbp' field.

SBP is model-agnostic: the 'model' field is passed through verbatim to
whatever LLM endpoint is configured via SBP_LLM_BASE_URL. The session
records which model was used per turn but has no model affinity.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────────────

class SBPRequestOptions(BaseModel):
    """SBP extension namespace in the request body."""
    force_new_session: bool = False
    checkpoint_every: int = Field(default=1, ge=1)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-4o"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    sbp: SBPRequestOptions = Field(default_factory=SBPRequestOptions)


# ── Response ──────────────────────────────────────────────────────────────────

class SBPResponseMeta(BaseModel):
    """SBP extension namespace in the response body."""
    session_id: str
    snapshot_id: str | None = None
    resume_available: bool = False
    resume_prompt: str | None = None
    last_checkpoint: str | None = None
    step_count: int = 0
    cost_usd: float | None = None
    model_routed_to: str | None = None


class ResumeAvailableResponse(BaseModel):
    """HTTP 202 returned when a suspended session exists."""
    sbp: SBPResponseMeta


# ── SBP Surface Context (L4 — WebSocket ATTACH_SESSION) ───────────────────────

class SurfaceContext(BaseModel):
    """
    Describes the connecting surface so the gateway can tailor output.
    Sent inside the ATTACH_SESSION WebSocket frame.

    Servers MUST tolerate unknown fields (model_config extra='allow').
    """
    model_config = {"extra": "allow"}

    device_type: Literal["mobile", "desktop", "iot", "browser", "voice", "unknown"] = "unknown"
    max_output_tokens: int | None = None
    ui_capabilities: list[str] = []
    locale: str = "en"
    surface_id: str | None = None
    mcp_tools: list[str] = []
