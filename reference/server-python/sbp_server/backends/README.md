# SBP Backend Interfaces

The reference server ships with an in-memory backend (`memory.py`) that is
suitable for development and the conformance test suite. For production
deployments, implement the four protocol interfaces defined in `base.py`.

## The four interfaces

### `SessionStore`

Manages session lifecycle records.

```python
class SessionStore(Protocol):
    async def create(session_id, agent_id, session_token, *, metadata) -> dict
    async def get(session_id) -> dict | None
    async def get_by_token(session_token) -> dict | None
    async def update_status(session_id, status) -> None
    async def list_messages(session_id) -> list[dict]
    async def append_message(session_id, message) -> None
    async def delete(session_id) -> None
```

**Durability contract**: `create`, `update_status`, and `append_message` MUST
be durable — a process restart MUST NOT lose committed records.

**Status transitions**: `idle → active → suspended → completed | failed`

---

### `TetherQueue`

Buffers `TETHER_TURN` frames while no surface is attached.

```python
class TetherQueue(Protocol):
    async def enqueue(session_id, turn) -> None
    async def drain(session_id) -> list[dict]
    async def clear(session_id) -> None
```

**Durability contract**: `enqueue` MUST be durable. A turn that was enqueued
before a pod restart or scaling event MUST survive and appear in a subsequent
`drain` call — even from a different replica. This is the key requirement
that the in-memory backend cannot satisfy.

**Replica safety**: the drain + clear sequence MUST be safe for concurrent
execution across replicas. A turn MUST NOT be delivered twice. The
recommended pattern is a transactional `drain` that atomically reads and
deletes, or a leased `drain` that requires an explicit `clear` before the
lease expires.

---

### `SnapshotStore`

Stores agent state snapshots for checkpoint/resume and handoff.

```python
class SnapshotStore(Protocol):
    async def write(session_id, snapshot, *, snapshot_type) -> str  # returns snapshot_id
    async def latest(session_id) -> dict | None
    async def get(snapshot_id) -> dict | None
```

**snapshot_type** SHOULD be one of: `pre_action`, `post_action`, `checkpoint`,
`crash_recovery`.

**Durability contract**: `write` MUST be durable. The `latest` query MUST
reflect the most recently written snapshot across all replicas.

---

### `RoamingTokenStore`

Manages export bundles and enforces single-use semantics on roaming tokens.

```python
class RoamingTokenStore(Protocol):
    async def record_export(export_id, bundle, *, expires_at, session_id, label) -> None
    async def consume(export_id) -> dict | None   # atomic — returns None if already consumed
    async def inspect(export_id) -> dict | None   # non-destructive metadata read
    async def list_for_session(session_id) -> list[dict]
```

**Atomicity contract**: `consume` MUST be atomic. Concurrent calls with the
same `export_id` MUST result in exactly one returning the bundle and the
rest returning `None`. A database-level `UPDATE ... WHERE consumed_at IS NULL
RETURNING *` or a Redis `SET NX` satisfies this.

---

## Wiring your backend

Register your implementations in `sbp_server/app.py`:

```python
from your_package import MySessionStore, MyTetherQueue, MySnapshotStore, MyRoamingTokenStore

def create_app() -> FastAPI:
    app = FastAPI(...)
    app.state.session_store   = MySessionStore(...)
    app.state.tether_queue    = MyTetherQueue(...)
    app.state.snapshot_store  = MySnapshotStore(...)
    app.state.roaming_store   = MyRoamingTokenStore(...)
    ...
    return app
```

All routers access backends via `request.app.state.*`, so no other changes
are needed.

---

## Production backends

For production-grade durable backends — Temporal-backed Tether (survives pod
restarts, scaling events, and 30-day disconnects with guaranteed delivery),
Postgres state storage, Redis pub/sub for multi-replica fan-out, and
autonomous session lifecycle management — see
[SilkBridge Enterprise](https://silkbridge.io/enterprise).
