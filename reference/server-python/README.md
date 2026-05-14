# SBP Reference Server (Python)

**State Bridge Protocol v0.9 — L5 conformant reference implementation**

This FastAPI server implements the full SBP spec (L1–L5) using pluggable
backend interfaces and an in-memory default backend.

## Model-agnostic. Server-agnostic.

The reference server routes LLM calls to **any OpenAI-compatible endpoint**.
Set `SBP_LLM_BASE_URL` to point at OpenAI, Anthropic, a local Ollama instance,
a vLLM deployment, or any other provider. Sessions, snapshots, and roaming
tokens are model-agnostic — they record which model was used per turn, but the
session itself has no model affinity.

The backend is **pluggable**: `SessionStore`, `TetherQueue`, `SnapshotStore`,
and `RoamingTokenStore` are Python `Protocol` classes. The default backend
uses in-process dicts (fast, zero dependencies, single-process only). Wire in
your own backend by implementing the four protocols.

## Quickstart

```bash
pip install sbp-server-reference

# Required
export SBP_LLM_BASE_URL="https://api.openai.com/v1"   # any OpenAI-compatible URL
export SBP_LLM_API_KEY="sk-..."
export SBP_JWT_SECRET="your-256-bit-secret"

# Optional
export SBP_LOG_LEVEL="info"
export SBP_PORT="8080"

sbp-server start
```

Or with Docker:

```bash
docker run -e SBP_LLM_BASE_URL=... -e SBP_LLM_API_KEY=... -e SBP_JWT_SECRET=... \
  -p 8080:8080 ghcr.io/statebridge-protocol/sbp-server-reference:latest
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `SBP_LLM_BASE_URL` | Yes | — | Any OpenAI-compatible base URL (e.g. `https://api.openai.com/v1`) |
| `SBP_LLM_API_KEY` | Yes | — | API key for the LLM provider |
| `SBP_JWT_SECRET` | Yes | — | HS256 signing secret for Roaming Tokens (min 32 chars) |
| `SBP_PORT` | No | `8080` | Server port |
| `SBP_LOG_LEVEL` | No | `info` | Logging level |
| `SBP_DEFAULT_MODEL` | No | `gpt-4o` | Default model if request omits the `model` field |

## Backend abstraction

The reference server ships with an in-memory backend suitable for development.

**For production**, implement the four backend protocols in
`sbp_server/backends/base.py` and register your implementation in
`sbp_server/app.py`. See `sbp_server/backends/README.md` for the contract
each interface MUST fulfill.

> **SilkBridge Enterprise** ships a production-grade Temporal + PostgreSQL +
> Redis backend that satisfies the durability and cross-replica requirements
> of the SBP Tether. See https://silkbridge.io/enterprise.

## Running tests

```bash
pip install -e ".[dev]"
pytest -v
```

## Conformance

This implementation is tested against the SBP conformance suite:

```bash
cd ../../
python conformance/runner.py --target http://localhost:8080 --level L5
```

## License

Apache-2.0. See [../../LICENSE](../../LICENSE).
