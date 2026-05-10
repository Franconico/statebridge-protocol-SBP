/**
 * @statebridge/sbp-client
 *
 * State Bridge Protocol v1.2 — reference TypeScript client.
 * Works in browser (native WebSocket) and Node.js (ws package).
 *
 * @example
 * import { SBPClient } from "@statebridge/sbp-client";
 *
 * const client = new SBPClient({
 *   serverUrl: "wss://api.example.com/v1/sbp/ws",
 *   sessionId: "550e8400-e29b-41d4-a716-446655440000",
 *   sessionToken: "my-session-token",
 *   surface: { device_type: "browser", ui_capabilities: ["markdown"] },
 * });
 *
 * client.on("tether_turn", (turn) => console.log("[buffered]", turn.content));
 * client.on("chunk", (c) => process.stdout.write(c.chunk));
 * client.on("ready", () => console.log("surface ready"));
 *
 * await client.connect();
 */
export { SBPClient } from "./client.js";
export type { SBPClientOptions, SBPEventMap } from "./client.js";
export { MCPBridge } from "./mcp-bridge.js";
export type { ToolHandler } from "./mcp-bridge.js";
export type {
  SurfaceContext,
  ClientFrame,
  ServerFrame,
  AttachSessionFrame,
  DetachFrame,
  ToolResultFrame,
  PongFrame,
  SessionAttachedFrame,
  SessionNotFoundFrame,
  ForbiddenFrame,
  ProtocolErrorFrame,
  TetherTurnFrame,
  TurnChunkFrame,
  TurnCompleteFrame,
  ToolCallFrame,
  PingFrame,
} from "./frames.js";
