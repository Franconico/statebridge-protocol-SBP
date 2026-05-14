# @statebridge/sbp-client

**State Bridge Protocol v0.9 — reference TypeScript client**

Works in browser and Node.js. Handles the full L4/L5 WebSocket protocol:
ATTACH_SESSION handshake, Tether drain on reconnect, TURN_CHUNK streaming,
and the bidirectional TOOL_CALL / TOOL_RESULT MCP bridge.

## Install

```bash
npm install @statebridge/sbp-client
```

## Quickstart

```typescript
import { SBPClient } from "@statebridge/sbp-client";

const client = new SBPClient({
  serverUrl: "wss://your-sbp-server/v1/sbp/ws",
  sessionId: "550e8400-e29b-41d4-a716-446655440000",
  sessionToken: "your-session-token",
  surface: {
    device_type: "browser",
    ui_capabilities: ["markdown", "tables"],
    locale: "en-US",
  },
});

client.on("tether_turn", (turn) => {
  console.log("[buffered]", turn.content);
});

client.on("chunk", ({ chunk }) => {
  process.stdout.write(chunk);
});

client.on("turn_complete", ({ step, model }) => {
  console.log(`\n— turn ${step} complete (${model})`);
});

await client.connect();
console.log("surface attached");
```

## L5: Surface MCP Bridge

Register local tools that the gateway can invoke via TOOL_CALL frames:

```typescript
import { SBPClient, MCPBridge } from "@statebridge/sbp-client";

const bridge = new MCPBridge()
  .register("camera", async (input) => {
    const image = await captureCamera(input);
    return { image_base64: image };
  })
  .register("contacts", async ({ query }) => {
    return { contacts: await searchContacts(query as string) };
  });

const client = new SBPClient({
  serverUrl: "wss://your-sbp-server/v1/sbp/ws",
  sessionId: "...",
  sessionToken: "...",
  surface: {
    device_type: "mobile",
    mcp_tools: bridge.toolNames, // declared at attach; bridge handles dispatch
  },
  mcpBridge: bridge,
});

await client.connect();
```

## Auto-reconnect

The client reconnects automatically after unexpected disconnects (default:
up to 10 attempts with a 2 s delay). On reconnect, the server drains any
Tether turns buffered while the surface was offline — they arrive as
`tether_turn` events before `ready` fires again.

```typescript
client.on("tether_turn", (turn) => {
  renderBufferedMessage(turn.content);
});
```

## API

### `new SBPClient(options)`

| Option | Type | Default | Description |
|---|---|---|---|
| `serverUrl` | `string` | required | Base WebSocket URL (without session_id suffix) |
| `sessionId` | `string` | required | Session UUID |
| `sessionToken` | `string` | required | Session authentication token |
| `surface` | `SurfaceContext` | `{}` | Surface capability descriptor |
| `mcpBridge` | `MCPBridge` | none | L5 tool dispatch bridge |
| `autoReconnect` | `boolean` | `true` | Reconnect on unexpected disconnect |
| `reconnectDelayMs` | `number` | `2000` | Delay between reconnect attempts |
| `maxReconnectAttempts` | `number` | `10` | Max reconnect attempts (0 = unlimited) |

### Events

| Event | Payload | When |
|---|---|---|
| `attached` | `SessionAttachedFrame` | SESSION_ATTACHED received |
| `tether_turn` | `{ role, content, model_used? }` | Buffered turn delivered |
| `chunk` | `{ chunk, step, model? }` | Streaming response chunk |
| `turn_complete` | `{ step, model?, cost_usd? }` | Streaming response complete |
| `ready` | — | Surface is ready for the next turn |
| `disconnected` | — | WebSocket closed |
| `error` | `Error` | Protocol error or max reconnects reached |

### `client.connect(): Promise<void>`

Connects and waits for SESSION_ATTACHED.

### `client.disconnect(): Promise<void>`

Sends DETACH and closes the WebSocket cleanly.
