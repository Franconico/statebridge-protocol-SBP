/**
 * SBP WebSocket frame types — full catalog for SBP v1.2.
 *
 * Server → client frames (9 types):
 *   SESSION_ATTACHED, SESSION_NOT_FOUND, FORBIDDEN, PROTOCOL_ERROR,
 *   TETHER_TURN, TURN_CHUNK, TURN_COMPLETE, TOOL_CALL, PING
 *
 * Client → server frames (4 types):
 *   ATTACH_SESSION, DETACH, TOOL_RESULT, PONG
 */

// ── Client → Server ───────────────────────────────────────────────────────────

export interface SurfaceContext {
  device_type?: "mobile" | "desktop" | "iot" | "browser" | "voice" | "unknown";
  max_output_tokens?: number;
  ui_capabilities?: string[];
  locale?: string;
  surface_id?: string;
  mcp_tools?: string[];
  [key: string]: unknown; // forward-compatible: unknown fields MUST be tolerated
}

export interface AttachSessionFrame {
  type: "ATTACH_SESSION";
  session_id: string;
  session_token: string;
  surface_context?: SurfaceContext;
}

export interface DetachFrame {
  type: "DETACH";
}

export interface ToolResultFrame {
  type: "TOOL_RESULT";
  call_id: string;
  result?: unknown;
  error?: string;
}

export interface PongFrame {
  type: "PONG";
}

export type ClientFrame =
  | AttachSessionFrame
  | DetachFrame
  | ToolResultFrame
  | PongFrame;

// ── Server → Client ───────────────────────────────────────────────────────────

export interface SessionAttachedFrame {
  type: "SESSION_ATTACHED";
  session_id: string;
  surface_id: string | null;
  device_type: string;
  queued_turns: number;
  mcp_tools_registered: string[];
  sbp_version: string;
}

export interface SessionNotFoundFrame {
  type: "SESSION_NOT_FOUND";
  session_id: string;
}

export interface ForbiddenFrame {
  type: "FORBIDDEN";
  detail: string;
}

export interface ProtocolErrorFrame {
  type: "PROTOCOL_ERROR";
  detail: string;
}

export interface TetherTurnFrame {
  type: "TETHER_TURN";
  session_id: string;
  turn: {
    role: string;
    content: string;
    model_used?: string;
  };
}

export interface TurnChunkFrame {
  type: "TURN_CHUNK";
  session_id: string;
  chunk: string;
  step: number;
  model?: string;
}

export interface TurnCompleteFrame {
  type: "TURN_COMPLETE";
  session_id: string;
  step: number;
  model?: string;
  cost_usd?: number;
}

export interface ToolCallFrame {
  type: "TOOL_CALL";
  call_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
}

export interface PingFrame {
  type: "PING";
}

export type ServerFrame =
  | SessionAttachedFrame
  | SessionNotFoundFrame
  | ForbiddenFrame
  | ProtocolErrorFrame
  | TetherTurnFrame
  | TurnChunkFrame
  | TurnCompleteFrame
  | ToolCallFrame
  | PingFrame;
