---
title: "Concept: The Tether"
layout: default
---

# The Tether

The Tether is SBP's answer to the fundamental problem of AI agents: **what
happens to the agent's work when the user's device goes offline?**

Without the Tether, the answer is: it's lost. The WebSocket closes, the agent's
output buffer is discarded, and the user comes back to an empty conversation.

With the Tether, the agent keeps working. Its output turns are buffered in a
durable queue on the server. When the user's device reconnects, the buffered
turns drain through the live WebSocket in order — as if the connection had never
dropped.

---

## How it works

```
Surface online:
  Agent → Gateway → WebSocket → Surface ✓

Surface offline (Tether active):
  Agent → Gateway → Tether Queue [turn 1, turn 2, turn 3, ...]

Surface reconnects (Tether drain):
  Gateway → SESSION_ATTACHED (queued_turns: 3)
  Gateway → TETHER_TURN (turn 0)
  Gateway → TETHER_TURN (turn 1)
  Gateway → TETHER_TURN (turn 2)
  Gateway signals: clear queue
  Gateway → live output (turn 4, 5, ...)
```

---

## Replica safety — why the queue must be durable

The Tether queue **MUST** be stored in durable backend storage, not in the
server process's memory.

In a multi-replica deployment, a reconnecting surface may route to a different
server replica than the one that was handling the session. If the queue is stored
in-process, the new replica's queue is empty — and the buffered turns are lost.

The reference server's in-memory backend deliberately violates this constraint
(it is single-process by design). Production deployments **SHOULD** use a
durable backend — Redis, Temporal, Kafka, or any storage that is visible to all
replicas.

This requirement is intentionally backend-agnostic: SBP specifies the contract
(durable, cross-replica), not the implementation. Choose the backend that fits
your infrastructure.

---

## Activating and deactivating the Tether

The Tether is controlled by signals from the surface:

- **`DETACH` frame** (or WebSocket close) → server activates Tether, starts queuing.
- **`ATTACH_SESSION` frame** → server deactivates Tether, drains queue, resumes
  live output.

The Tether is automatically activated on unexpected disconnection (WebSocket
error or timeout), not just graceful `DETACH`. The agent should never need to
know whether a surface is attached.

---

## Normative source

- **SPEC.md §7.3** — Tether semantics
- **SPEC.md §7.4** — Resume semantics
- **SPEC.md §11.1** — `ATTACH_SESSION` frame
- **SPEC.md §11.2** — `TETHER_TURN` and `SESSION_ATTACHED` frames
