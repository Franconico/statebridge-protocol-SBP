# Contributing to SBP

Thanks for contributing. SBP has two kinds of changes — **spec changes** and
**implementation changes** — and they follow different processes.

## Implementation changes (reference server, reference client, conformance suite)

Standard pull-request flow:

1. Fork the repo and create a feature branch.
2. Make your change. If you change behavior, add or update a test in the
   relevant directory:
   - `reference/server-python/tests/` — Python server tests.
   - `reference/client-typescript/` — TS client tests.
   - `conformance/tests/L<level>/` — language-agnostic conformance fixtures.
3. Run the local checks:
   - `cd reference/server-python && pytest`
   - `npx ajv-cli validate -s spec/schemas/<schema>.json -d 'spec/examples/<file>'`
4. Open a pull request against `main`. Use the PR template.

CI runs the full schema validation suite and the conformance self-test on every
PR. Both must be green to merge.

## Spec changes

The wire protocol is what every implementation depends on. Changes are
versioned strictly:

| Type of change                              | Versioning            | Process              |
| ------------------------------------------- | --------------------- | -------------------- |
| Editorial (clarification, typo, example)    | None — no version bump | Regular PR           |
| Backwards-compatible addition (new OPTIONAL field, new error code, new well-known surface type) | Minor bump (e.g. 1.2 → 1.3) | RFC issue → PR       |
| Backwards-incompatible change               | Major bump (e.g. 1.x → 2.0) | RFC issue → PR, with migration notes and a transition period |

### RFC flow for additions or breaking changes

1. **Open an issue** using the **Spec proposal** template. Describe the
   problem, the proposed change, the migration path, and any prior art (MCP,
   OpenAI, RFC standards) that informs the design.
2. **Discussion** stays on the issue for at least **14 days** (the comment
   period). Anyone can comment.
3. **Implementation in the reference server** must accompany the spec PR. We
   do not accept spec changes without a working reference implementation —
   this prevents un-implementable specs.
4. **PR must update**: `spec/SPEC.md`, the relevant `spec/schemas/*.json`,
   `spec/examples/*`, the reference server, the conformance suite for the
   relevant level, and `CHANGELOG.md`.
5. **Merge requires** sign-off from at least two maintainers (see
   [`GOVERNANCE.md`](GOVERNANCE.md)).

## Style

- Markdown: hard-wrap at 80 columns where it doesn't break tables.
- Code: format with the language's standard tool (`ruff` for Python, `prettier`
  for TS/JS/JSON).
- Commit messages: imperative ("Add fork lineage field"), not past-tense.
- Each commit should be independently buildable and testable. Squash WIP
  commits before merging.

## Getting set up

```bash
git clone https://github.com/statebridge-protocol/sbp.git
cd sbp

# Reference Python server
cd reference/server-python
pip install -e ".[dev]"
pytest

# Reference TypeScript client
cd ../client-typescript
npm install
npm test
```

## What we will not accept

- Spec changes without a corresponding reference-server implementation.
- Vendor-specific fields baked into the core spec — those belong in
  vendor-prefixed extensions (`x-vendorname-*`).
- Breaking changes that lack a migration path or transition period.
- New required fields without strong justification (additions should default to
  OPTIONAL).
