# Governance

The State Bridge Protocol is a vendor-neutral, model-agnostic, open standard.
Its governance is designed to prevent capture by any single company, model
provider, or infrastructure vendor.

## Principles

1. **Vendor neutrality** — no clause in the spec may require a specific LLM,
   cloud provider, database, or orchestration engine. The spec defines
   contracts; it does not mandate implementations.
2. **Model agnosticism** — SBP MUST remain compatible with any LLM that speaks
   the OpenAI-compatible chat completions format. Proposals that bake in
   vendor-specific model features (e.g. "requires Anthropic extended thinking")
   are out of scope.
3. **Server agnosticism** — the reference server ships with pluggable backend
   interfaces. Proposals that break the `SessionStore` / `TetherQueue` /
   `SnapshotStore` / `RoamingTokenStore` abstraction layer require exceptional
   justification.
4. **Implementer diversity** — decisions should favour the widest range of
   implementers (solo developers, enterprises, on-premises deployments,
   air-gapped environments, edge devices).
5. **Stability** — breaking changes in the wire protocol are versioned and
   come with migration paths.

## Maintainers

The current maintainers are:

- Franco Perez Lissi ([@Franconico](https://github.com/Franconico)) — protocol
  author, founding maintainer

New maintainers may be added by unanimous vote of existing maintainers. The
goal is to reach at least three maintainers from different organizations before
v2.0.

## Decision-making

| Change type | Who decides |
|---|---|
| Editorial (typo, clarification, reword) | Any maintainer merges |
| New OPTIONAL field or well-known value | One maintainer + one reviewer from outside the author's organization |
| New conformance level | Two maintainers |
| Backwards-incompatible (wire-breaking) | All maintainers + 30-day public comment period |
| Transfer or archival of the repo | All maintainers |

## Spec change process

1. **Issue** — open a Spec Proposal issue.
2. **Comment period** — at least 14 days (30 for breaking changes). Anyone may
   comment; maintainers facilitate, not gatekeep.
3. **Implementation** — a reference-server PR must accompany the spec PR.
4. **Review** — required sign-offs as per the table above.
5. **Merge** — maintainer merges; CHANGELOG updated; version bumped if
   applicable.

## Conformance registry

Implementations claiming a conformance level (L1–L5) may open a PR to add
themselves to [`docs/implementations.md`](docs/implementations.md). Listing
requirements:

- The implementation MUST pass the relevant `conformance/` test suite.
- The listing MUST indicate the conformance level claimed.
- The listing MUST indicate whether the implementation is open-source or
  commercial.
- The listing MUST NOT misrepresent features not covered by the SBP spec as
  "SBP features" (e.g. vendor-specific memory schemas should be listed as
  "vendor extensions on top of SBP").

## Memory schema registry

The bundle `memory.schema_id` field accepts a URI identifying the memory
schema used. Anyone may register a schema URI by opening a PR to add it to
the registry table in `spec/SPEC.md §14`. Registry listings are
informational only — the protocol does not validate memory payloads.

## Code of Conduct

All participants are expected to follow the
[Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
