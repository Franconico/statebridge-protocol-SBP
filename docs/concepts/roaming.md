---
title: "Concept: Roaming"
layout: default
---

# Roaming

Roaming is the ability to export a session's complete state into a signed,
portable token and import it into **any** conformant SBP server — on any
device, any LLM router, any infrastructure provider.

This is the protocol-level expression of the design principle: **your session
belongs to you, not to the server that created it.**

---

## The four roaming operations

### Export

`POST /v1/sbp/sessions/{id}/export`

Creates a snapshot of the session's full state — conversation history, memory
bundle, state snapshot — signs it with HMAC-SHA256, and returns a compact JWT
(the Roaming Token). The token is a reference; the bundle is stored server-side.

Default TTL: 24 hours. Maximum: 7 days.

### Import

`POST /v1/sbp/sessions/import`

Presents a Roaming Token to any conformant SBP server. The server:
1. Verifies the token signature and expiry.
2. Marks the token consumed (single-use by default).
3. Replays the message history into a new session.
4. Restores the memory bundle (if the `schema_id` is recognized).
5. Rehydrates the state snapshot.

The new session continues from exactly where the exported session left off —
on a different device, a different server, a different LLM, or a different
organization.

### Handoff

`POST /v1/sbp/sessions/{id}/handoff`

An atomic export + import + bridge message + suspend:
1. Exports the session.
2. Creates a new session under a different agent with the bundle imported.
3. Injects a bridge message (e.g. "The user approved the Tokyo itinerary.
   Please proceed to book flights.").
4. Suspends the source session.

Use handoff when one agent completes a phase and the next agent needs full context.

### Fork

`POST /v1/sbp/sessions/{id}/fork`

Creates a new session that shares all history through the fork point, then
diverges independently. Both the origin and the fork are fully independent from
the fork moment forward.

Use fork for A/B exploration ("try two different strategies from the same
context"), counterfactual testing, or parallel work streams.

---

## Bundle envelope

The exported bundle has this top-level structure:

```json
{
  "sbp_version": "1.0",
  "session": { "id": "...", "step_count": 24, ... },
  "messages": [...],
  "memory": { "schema_id": "silkbridge.memory.v1", "payload": {...} },
  "state_snapshot": {...},
  "metadata": { "export_id": "...", "message_count": 48 }
}
```

The `memory.schema_id` field is a URI. Implementations that do not recognize
the schema MUST import the session without memory — they MUST NOT reject the
import. This ensures interoperability across different implementations.

---

## Model-agnostic roaming

A session exported from a server using GPT-4o can be imported by a server
using Claude or Llama. The bundle records which model was used per turn in the
message log (for auditing), but the session itself has no model affinity. The
importing server uses whatever model is configured in its LLM router.

This is one of SBP's strongest differentiation points from proprietary state
layers: no vendor can block a roam.

---

## Lineage

`GET /v1/sbp/sessions/{id}/lineage`

Returns the full family tree of a session: all exports, all handoffs (incoming
and outgoing), all forks, and — if this session is itself a fork — its origin.

Use lineage for audit trails, debugging multi-agent workflows, and cost attribution.

---

## Normative source

- **SPEC.md §8** — full Roaming section
- **SPEC.md §8.1** — Roaming Token format (JWT)
- **SPEC.md §8.2** — Bundle envelope
- **SPEC.md §8.3–8.8** — Export, import, inspect, handoff, fork, lineage
- **spec/schemas/roaming-bundle.schema.json** — bundle JSON Schema
- **spec/examples/03–06** — wire examples for each operation
