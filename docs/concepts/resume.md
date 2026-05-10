---
title: "Concept: Resume"
layout: default
---

# Resume

Resume is the L2 capability that allows the **same surface** to reconnect to a
suspended session after a disconnection — and pick up exactly where it left off.

Resume is the user-visible face of the Tether: the surface drops, comes back,
and the buffered turns drain through the live connection automatically.

---

## The three resume paths

### 1. Automatic Tether drain (same device reconnects via WebSocket)

The user's phone loses signal, reconnects 10 minutes later. The surface
sends `ATTACH_SESSION`. The server sends `SESSION_ATTACHED` with
`queued_turns: 3` and immediately delivers the three buffered `TETHER_TURN`
frames. Done.

### 2. HTTP 202 resume (different request, same agent)

The user opens a new tab or session. The next `POST /v1/chat/completions`
returns HTTP 202 with `resume_available: true` and a `resume_prompt`:

```json
{
  "sbp": {
    "resume_available": true,
    "resume_prompt": "You were last working on: planning a Tokyo trip (step 12).",
    "session_id": "..."
  }
}
```

The client shows this to the user. On confirmation, it resends the request
with the existing `session_id` — the server picks up the suspended session
rather than creating a new one.

### 3. Roaming resume (different server, different device)

A Roaming Token is imported on any SBP server. This creates a new session that
is fully initialized from the exported bundle — a remote resume that works
across servers, LLMs, and deployments. See [Roaming](roaming.md).

---

## Idempotency

Resume is idempotent. If `ATTACH_SESSION` arrives for a session that is already
`running` (e.g. the surface sent `ATTACH_SESSION` twice), the server MUST:
- Send `SESSION_ATTACHED`.
- Drain any queued turns (may be zero).
- Continue normally.

The server MUST NOT create a duplicate session or error on a repeated attach.

---

## Normative source

- **SPEC.md §6.3** — HTTP 202 Resume Available
- **SPEC.md §7.3** — Tether semantics
- **SPEC.md §7.4** — Resume semantics (idempotency)
- **spec/examples/02-l2-resume.http**
