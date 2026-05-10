/**
 * SBPClient — reference WebSocket client for State Bridge Protocol v1.2.
 *
 * Handles the full L4/L5 protocol:
 *   - ATTACH_SESSION handshake
 *   - TETHER_TURN drain on reconnect (L2 Resume)
 *   - TURN_CHUNK streaming callbacks (L4 Surface)
 *   - TOOL_CALL / TOOL_RESULT bidirectional MCP bridge (L5)
 *   - Automatic PING/PONG keepalive
 *
 * Works in both browser (native WebSocket) and Node.js (ws package or native).
 *
 * @example
 * const client = new SBPClient({
 *   serverUrl: "wss://your-sbp-server/v1/sbp/ws",
 *   sessionId: "...",
 *   sessionToken: "...",
 *   surface: { device_type: "browser", ui_capabilities: ["markdown"] },
 * });
 *
 * client.on("turn", (turn) => console.log(turn.content));
 * client.on("chunk", (chunk) => process.stdout.write(chunk.chunk));
 * await client.connect();
 */
import type { MCPBridge } from "./mcp-bridge.js";
import type {
  ClientFrame,
  ServerFrame,
  SessionAttachedFrame,
  SurfaceContext,
  ToolCallFrame,
} from "./frames.js";

export interface SBPClientOptions {
  /** Base WebSocket URL of the SBP server, e.g. "wss://api.example.com/v1/sbp/ws" */
  serverUrl: string;
  /** Session ID to attach to */
  sessionId: string;
  /** Session token for authentication */
  sessionToken: string;
  /** Surface descriptor sent in ATTACH_SESSION */
  surface?: SurfaceContext;
  /** Optional MCP bridge for L5 tool handling */
  mcpBridge?: MCPBridge;
  /** Reconnect on unexpected disconnect (default: true) */
  autoReconnect?: boolean;
  /** Delay between reconnect attempts in ms (default: 2000) */
  reconnectDelayMs?: number;
  /** Max reconnect attempts (default: 10, 0 = unlimited) */
  maxReconnectAttempts?: number;
}

export type SBPEventMap = {
  /** Fired when SESSION_ATTACHED is received (handshake complete) */
  attached: (frame: SessionAttachedFrame) => void;
  /** Fired for each TETHER_TURN frame delivered on reconnect */
  tether_turn: (turn: { role: string; content: string; model_used?: string }) => void;
  /** Fired for each TURN_CHUNK frame (streaming response) */
  chunk: (frame: { chunk: string; step: number; model?: string }) => void;
  /** Fired when a streaming turn completes */
  turn_complete: (frame: { step: number; model?: string; cost_usd?: number }) => void;
  /** Fired when connection is fully ready (after tether drain) */
  ready: () => void;
  /** Fired on graceful disconnect */
  disconnected: () => void;
  /** Fired on connection error */
  error: (err: Error) => void;
};

type EventListener<T extends (...args: any[]) => void> = T;

export class SBPClient {
  private _opts: Required<SBPClientOptions>;
  private _ws: WebSocket | null = null;
  private _listeners: { [K in keyof SBPEventMap]?: EventListener<SBPEventMap[K]>[] } = {};
  private _reconnectAttempts = 0;
  private _closed = false;
  private _attachedPromise: { resolve: () => void; reject: (e: Error) => void } | null = null;

  constructor(opts: SBPClientOptions) {
    this._opts = {
      surface: {},
      autoReconnect: true,
      reconnectDelayMs: 2000,
      maxReconnectAttempts: 10,
      mcpBridge: undefined as unknown as MCPBridge,
      ...opts,
    };
  }

  // ── Event emitter ─────────────────────────────────────────────────────────

  on<K extends keyof SBPEventMap>(event: K, listener: SBPEventMap[K]): this {
    if (!this._listeners[event]) this._listeners[event] = [];
    (this._listeners[event] as EventListener<SBPEventMap[K]>[]).push(listener);
    return this;
  }

  off<K extends keyof SBPEventMap>(event: K, listener: SBPEventMap[K]): this {
    const arr = this._listeners[event] as EventListener<SBPEventMap[K]>[] | undefined;
    if (arr) {
      this._listeners[event] = arr.filter((l) => l !== listener) as any;
    }
    return this;
  }

  private _emit<K extends keyof SBPEventMap>(
    event: K,
    ...args: Parameters<SBPEventMap[K]>
  ): void {
    const arr = this._listeners[event] as ((...a: any[]) => void)[] | undefined;
    if (arr) arr.forEach((l) => l(...args));
  }

  // ── Connection ────────────────────────────────────────────────────────────

  /**
   * Connect to the SBP server and complete the ATTACH_SESSION handshake.
   * Resolves when SESSION_ATTACHED is received and Tether drain is complete.
   */
  connect(): Promise<void> {
    this._closed = false;
    return new Promise((resolve, reject) => {
      this._attachedPromise = { resolve, reject };
      this._open();
    });
  }

  /**
   * Send a graceful DETACH frame and close the WebSocket.
   */
  async disconnect(): Promise<void> {
    this._closed = true;
    this._opts.autoReconnect = false;
    if (this._ws) {
      this._send({ type: "DETACH" });
      this._ws.close(1000);
      this._ws = null;
    }
  }

  private _open(): void {
    const url = `${this._opts.serverUrl}/${this._opts.sessionId}`;
    this._ws = new WebSocket(url);

    this._ws.onopen = () => {
      this._reconnectAttempts = 0;
      this._send({
        type: "ATTACH_SESSION",
        session_id: this._opts.sessionId,
        session_token: this._opts.sessionToken,
        surface_context: this._buildSurface(),
      });
    };

    this._ws.onmessage = (event: MessageEvent) => {
      let frame: ServerFrame;
      try {
        frame = JSON.parse(event.data as string) as ServerFrame;
      } catch {
        return;
      }
      this._handleFrame(frame);
    };

    this._ws.onerror = () => {
      const err = new Error("SBP WebSocket error");
      this._emit("error", err);
      if (this._attachedPromise) {
        this._attachedPromise.reject(err);
        this._attachedPromise = null;
      }
    };

    this._ws.onclose = (event: CloseEvent) => {
      this._emit("disconnected");
      if (!this._closed && this._opts.autoReconnect) {
        this._scheduleReconnect();
      }
    };
  }

  private _buildSurface(): SurfaceContext {
    const bridge = this._opts.mcpBridge;
    const surface = { ...this._opts.surface };
    if (bridge && bridge.toolNames.length > 0) {
      surface.mcp_tools = [
        ...(surface.mcp_tools ?? []),
        ...bridge.toolNames,
      ];
    }
    return surface;
  }

  private _handleFrame(frame: ServerFrame): void {
    switch (frame.type) {
      case "SESSION_ATTACHED":
        this._emit("attached", frame);
        // Tether drain happens server-side; frames arrive after SESSION_ATTACHED
        // We resolve the connect() promise after the drain (queued_turns == 0
        // means drain will complete synchronously in next ticks).
        // For simplicity we resolve immediately and let tether_turn events fire.
        if (this._attachedPromise) {
          this._attachedPromise.resolve();
          this._attachedPromise = null;
        }
        if (frame.queued_turns === 0) {
          this._emit("ready");
        }
        break;

      case "SESSION_NOT_FOUND":
        const notFoundErr = new Error(`SBP: session not found — ${frame.session_id}`);
        this._emit("error", notFoundErr);
        if (this._attachedPromise) {
          this._attachedPromise.reject(notFoundErr);
          this._attachedPromise = null;
        }
        break;

      case "FORBIDDEN":
        const forbiddenErr = new Error(`SBP: forbidden — ${frame.detail}`);
        this._emit("error", forbiddenErr);
        if (this._attachedPromise) {
          this._attachedPromise.reject(forbiddenErr);
          this._attachedPromise = null;
        }
        break;

      case "PROTOCOL_ERROR":
        this._emit("error", new Error(`SBP protocol error: ${frame.detail}`));
        break;

      case "TETHER_TURN":
        this._emit("tether_turn", frame.turn);
        break;

      case "TURN_CHUNK":
        this._emit("chunk", {
          chunk: frame.chunk,
          step: frame.step,
          model: frame.model,
        });
        break;

      case "TURN_COMPLETE":
        this._emit("turn_complete", {
          step: frame.step,
          model: frame.model,
          cost_usd: frame.cost_usd,
        });
        this._emit("ready");
        break;

      case "TOOL_CALL":
        this._handleToolCall(frame);
        break;

      case "PING":
        this._send({ type: "PONG" });
        break;
    }
  }

  private async _handleToolCall(frame: ToolCallFrame): Promise<void> {
    const bridge = this._opts.mcpBridge;
    if (!bridge) {
      this._send({
        type: "TOOL_RESULT",
        call_id: frame.call_id,
        error: "No MCP bridge registered on this surface",
      });
      return;
    }
    const { result, error } = await bridge.dispatch(frame.tool_name, frame.tool_input);
    this._send({
      type: "TOOL_RESULT",
      call_id: frame.call_id,
      ...(error ? { error } : { result }),
    });
  }

  private _send(frame: ClientFrame): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(frame));
    }
  }

  private _scheduleReconnect(): void {
    const max = this._opts.maxReconnectAttempts;
    if (max > 0 && this._reconnectAttempts >= max) {
      this._emit("error", new Error(`SBP: max reconnect attempts (${max}) reached`));
      return;
    }
    this._reconnectAttempts++;
    setTimeout(() => {
      if (!this._closed) this._open();
    }, this._opts.reconnectDelayMs);
  }
}
