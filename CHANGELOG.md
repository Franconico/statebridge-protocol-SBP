# Changelog

All notable changes to the State Bridge Protocol (SBP) and the reference
implementations are recorded here. The protocol follows [Semantic Versioning](https://semver.org/);
the major.minor pair is what wire frames advertise via `sbp_version`.

## [v1.2.0] — Initial public release

The first public release of SBP corresponds to wire-version **1.2** as already
shipping in production at MARGNE-AI. Earlier internal versions (1.0, 1.1) are
considered pre-history and are not part of the public spec.

### Spec — what's normative in v1.2

- **L1 — Stateful Proxy**: OpenAI `/v1/chat/completions` extended with the
  top-level `sbp` request and response namespaces.
- **L2 — Tether + Resume**: session lifecycle (`idle → active → suspended →
  completed | failed`), pre-action / post-action snapshot model, and the
  replica-safe Tether drain requirement.
- **L3 — Roaming**: Roaming Token (compact HS256 JWT), bundle envelope
  (`session`, `messages`, `memory`, `state_snapshot`, `metadata`), and the four
  REST operations: `export`, `import`, `handoff`, `fork`. Lineage read API.
- **L4 — Surface negotiation**: `SurfaceContext` schema (six well-known
  `device_type` values, `ui_capabilities`, `locale`, `max_output_tokens`,
  `surface_id`, `mcp_tools`).
- **L5 — Surface MCP Bridge**: `TOOL_CALL` / `TOOL_RESULT` frames with
  `call_id` correlation.
- **WebSocket frame catalog** — 9 server→client + 4 client→server frame types,
  ATTACH-first ordering rule, `sbp_version` advertisement on
  `SESSION_ATTACHED`.

### Reference server (Python) — initial release

- L5-conformant FastAPI implementation extracted from MARGNE-AI's production code.
- Pluggable backend interfaces: `SessionStore`, `TetherQueue`, `SnapshotStore`,
  `RoamingTokenStore`. Default in-process / in-memory backends.
- HS256 JWT roaming-token sign/verify (stdlib only, no PyJWT dependency).

### Reference client (TypeScript) — initial release

- Minimal `SBPClient` browser/Node class.
- Frame parsing as TypeScript discriminated unions.
- Surface-side MCP tool registration helper.

### Conformance suite

- Language-agnostic HTTP fixtures organized by level (L1–L5).
- `runner.py` validates a target server URL against a chosen level.

### Reserved (not normative in v1.2)

- HITL approval flow.
- Memory schemas beyond the bundle envelope (`schema_id` URI registry is open
  but unpopulated; `silkbridge.memory.v1` is one registered example).
- Cross-tenant authorization model.
- Surface-tool authorization model beyond the basic "surface declared the tool"
  check.

## Pre-history

- **v1.1** *(internal, MARGNE-AI Phase 11)* — first SBP State Roaming
  implementation; bundle envelope finalized; lineage tracking added.
- **v1.0** *(internal, MARGNE-AI Phase 10)* — first end-to-end "stateful proxy
  with Tether queue + Resume" implementation; predates the SBP name.
