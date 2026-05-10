# SBP Conformance Test Suite

Validates any SBP server implementation against the normative requirements
in `spec/SPEC.md`. Tests are organized by conformance level; each level
includes all tests from previous levels.

## Requirements

```bash
pip install httpx websockets
```

## Usage

```bash
# Test a server at L1 (stateful proxy)
python conformance/runner.py --target http://localhost:8080 --level L1

# Test at L3 (runs L1 + L2 + L3)
python conformance/runner.py --target http://localhost:8080 --level L3

# Full L5 with verbose output
python conformance/runner.py --target http://localhost:8080 --level L5 --verbose
```

Exit code `0` = conformant. Exit code `1` = one or more failures.

## Test levels

| Level | Includes | Requirement |
|---|---|---|
| L1 | Stateful Proxy | `sbp.session_id` in response, `X-Session-Token` header, `sbp` namespace stripped from upstream |
| L2 | L1 + Tether + Resume | HTTP 202 on suspended session, `force_new_session` bypass |
| L3 | L2 + Roaming | Export → import → single-use enforcement; tampered-token rejection; handoff; fork |
| L4 | L3 + Surface negotiation | ATTACH_SESSION handshake; first-frame rule; unknown-fields tolerance |
| L5 | L4 + MCP Bridge | Tether drain count on attach; TOOL_CALL / TOOL_RESULT call_id round-trip |

## Claiming conformance

To claim a conformance level:

1. Run the suite against your server: `python conformance/runner.py --target <your-server> --level L5`
2. All tests must pass (exit code 0).
3. Open a PR adding your server to `docs/implementations.md` with the level badge.

The reference server (`reference/server-python`) is tested against L5 in CI
via `.github/workflows/conformance-self-test.yml`.

## Test fixture format

Each test is a JSON file with the following shape:

```json
{
  "description": "Human-readable test name",
  "level": "L3",
  "transport": "http",
  "steps": [
    {
      "id": "step_name",
      "request": { "method": "POST", "path": "/v1/...", "body": {} },
      "expect": { "status": 201, "body_contains": { "field": "value" } },
      "extract": { "variable_name": "$.field.path" }
    }
  ]
}
```

Variables extracted in one step (via `extract`) are interpolated into later
steps as `${variable_name}`.

For WebSocket tests, add `"transport": "websocket"` and use `"protocol": "websocket"`
in the step, with `connect`, `send`, and `expect_receive` fields.
