---
title: "Concept: Session Lineage"
layout: default
---

# Session Lineage

Lineage is the audit trail of a session's history: where it came from, where it
went, and what branches it spawned.

Every roaming operation (export, import, handoff, fork) creates a lineage record.
The `GET /v1/sbp/sessions/{id}/lineage` endpoint returns the complete family tree.

---

## What lineage tracks

```
Session A (origin)
  │
  ├── export ──→ token T1 ──→ import into Session B (device handoff)
  │                                │
  │                                └── fork ──→ Session C (A/B exploration)
  │
  └── handoff ──→ Session D (agent handoff to booking-agent)
```

For each session, lineage exposes:
- **Exports** — all tokens created from this session (including consumed/expired)
- **Outgoing handoffs** — sessions this session handed off to
- **Incoming handoffs** — sessions that handed off *to* this session
- **Forks** — sessions branched from this session
- **Origin** — if this session is itself a fork, its parent

---

## Use cases

- **Audit trails** — "How did this agent session come to have this context?"
- **Cost attribution** — "Which sessions descended from the original planning session?"
- **Debugging multi-agent workflows** — "Did the handoff from the planning agent to the booking agent succeed?"
- **Security** — "Was this roaming token imported more than once?"

---

## Normative source

- **SPEC.md §8.8** — Lineage
- **spec/schemas/lineage.schema.json**
