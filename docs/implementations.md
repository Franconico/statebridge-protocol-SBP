---
title: Known Implementations
layout: default
---

# Known Implementations

Implementations that have passed the [SBP conformance suite](../conformance/)
may be listed here. Open a PR to add your implementation.

**Listing requirements:**
1. Pass the relevant conformance tests (`conformance/runner.py --level LX`).
2. Specify which conformance level is claimed.
3. Indicate whether the implementation is open-source or commercial.
4. Do not misrepresent vendor-specific extensions as "SBP features."

---

## Reference Implementations (this repo)

| Name | Language | Conformance Level | License | Notes |
|---|---|---|---|---|
| [sbp-server-reference](../reference/server-python/) | Python (FastAPI) | L5 | Apache-2.0 | In-memory backend. Single-process. Not for production multi-replica use. |
| [sbp-client-ts](../reference/client-typescript/) | TypeScript | L5 (client) | Apache-2.0 | Browser + Node. |

---

## Production Implementations

| Name | Language | Conformance Level | License | Notes |
|---|---|---|---|---|
| [SilkBridge Enterprise](https://silkbridge.io/enterprise) | Python + Temporal | L5 | Commercial | Production-grade Temporal backend. Contextual Translation Pipeline. HITL workflows. Reference implementation for the spec. |

---

## Community Implementations

*None listed yet. Be the first — open a PR.*

---

## Memory Schema Registry

Registered `memory.schema_id` URIs:

| URI | Owner | Description |
|---|---|---|
| `silkbridge.memory.v1` | SilkBridge | Episodic, semantic, and procedural memory. Implementation-defined payload. Not part of the SBP open spec. |

*To register a memory schema URI, open a PR to this file and to `spec/SPEC.md §15.2`.*
