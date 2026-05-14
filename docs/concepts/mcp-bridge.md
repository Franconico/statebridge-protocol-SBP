---
title: "Concept: The MCP Bridge (Northbound MCP)"
layout: default
---

# The MCP Bridge — Northbound MCP

The MCP Bridge is SBP's most distinctive capability: it turns the SBP WebSocket
into a **bidirectional MCP bridge**, allowing the AI agent to call tools that
physically live on the user's device.

---

## The problem it solves

MCP (Model Context Protocol) gives agents access to server-side tools:
databases, APIs, file systems, web search. These tools run in data centers.

But some of the most valuable tools for a human-facing agent are **on the device
the human is holding**: the camera, GPS, the contact book, local files,
biometric sensors, the microphone. These tools are not accessible to a server-side
MCP client.

The MCP Bridge solves this by making the **surface an MCP server** — reachable
through the SBP WebSocket.

---

## How it works

```
1. Surface declares tools at attach time:
   surface_context.mcp_tools: ["camera", "gps", "contacts"]

2. Gateway injects tool schemas into the LLM's context:
   The LLM now "knows" it can call camera, gps, contacts.

3. LLM requests a tool call:
   { "tool_calls": [{ "function": { "name": "surface_camera", ... } }] }

4. Gateway sends TOOL_CALL to the surface:
   { "type": "TOOL_CALL", "call_id": "uuid", "tool_name": "camera", "tool_input": {...} }

5. Surface executes the tool (takes a photo):
   { "type": "TOOL_RESULT", "call_id": "uuid", "result": { "data_url": "..." } }

6. Gateway delivers the result to the LLM as a tool response.
   The LLM continues with the photo in its context.
```

The surface needs **no knowledge of MCP** beyond handling two frame types.
The gateway handles the MCP protocol layer.

---

## What the protocol specifies

SBP v0.9 specifies:
- The `mcp_tools` declaration in `SurfaceContext`.
- The `TOOL_CALL` and `TOOL_RESULT` frame schemas.
- The `call_id` correlation mechanism for multiplexed in-flight calls.
- The 30-second default timeout and cancellation on disconnect.

SBP v0.9 does **not** specify:
- How tool schemas are negotiated (generic passthrough schemas in v0.9; full schema exchange deferred to a future version).
- How the gateway injects tools into the LLM's context (implementation-defined; must be compatible with the LLM's tool-calling conventions).
- Per-tool authorization policies (see §13.6 — implementations SHOULD validate against an allowlist).

---

## Call multiplexing

Multiple tool calls MAY be in-flight simultaneously. Each is identified by a
unique `call_id` UUID. The surface MUST respond with the same `call_id` in its
`TOOL_RESULT` frame.

```
Gateway → Surface: TOOL_CALL (call_id: aaa, tool: camera)
Gateway → Surface: TOOL_CALL (call_id: bbb, tool: gps)
Surface → Gateway: TOOL_RESULT (call_id: bbb, result: {lat: 35.68, lon: 139.76})
Surface → Gateway: TOOL_RESULT (call_id: aaa, result: {data_url: "..."})
```

The gateway matches each `TOOL_RESULT` to its waiting `TOOL_CALL` by `call_id`
and delivers it to the appropriate LLM request.

---

## The Northbound MCP diagram

```
                ┌─────────────────────┐
                │  Surface (phone)    │
                │  MCP server:        │
                │   camera, gps,      │
                │   contacts          │
                └──────────┬──────────┘
                           │ SBP WebSocket
                    TOOL_CALL / TOOL_RESULT frames
                           │
                ┌──────────┴──────────┐
                │  Agent Gateway      │
                │  (SBP L5)           │
                │                     │
                │  ↕ Temporal/LLM     │
                │  ↕ MCP Southbound   │
                └──────────┬──────────┘
                           │ MCP
                ┌──────────┴──────────┐
                │  Server-side tools  │
                │  DB, APIs, files    │
                └─────────────────────┘
```

MCP flows both ways: Southbound to server-side tools, Northbound to surface
tools, all through the same gateway.

---

## Model-agnostic tool injection

Because SBP is model-agnostic, tool schema injection MUST be compatible with
whichever LLM the gateway routes to. An L5 gateway routing to Claude MUST use
Claude's tool schema format; routing to GPT-4o MUST use OpenAI's format. The
SBP spec does not prescribe tool schema format — this is an implementation
concern for the LLM router.

---

## Normative source

- **SPEC.md §10** — Surface MCP Bridge
- **SPEC.md §10.1** — Tool declaration
- **SPEC.md §10.2** — TOOL_CALL frame
- **SPEC.md §10.3** — TOOL_RESULT frame
- **SPEC.md §10.4** — Timeout and cancellation
- **SPEC.md §14** — MCP Interoperability
- **spec/examples/08-l5-tool-call.json**
- **spec/examples/09-l5-tool-result.json**
