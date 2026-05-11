"""
SBP Tether Backend — PostgreSQL + optional Redis pub/sub (Tier 1).

Production OSS option. Multi-replica safe when Redis is configured.

Schema (applied automatically at startup):

  CREATE TABLE IF NOT EXISTS tether_turns (
    id          UUID PRIMARY KEY,
    session_id  UUID NOT NULL,
    step        INTEGER NOT NULL,
    content     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    extra       JSONB NOT NULL DEFAULT '{}',
    buffered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acked_at    TIMESTAMPTZ
  );
  CREATE INDEX IF NOT EXISTS idx_tether_session_step
      ON tether_turns (session_id, step);

Multi-replica WebSocket fanout:
  When a surface reconnects to a different replica, the replica that did NOT
  buffer the turns still needs to drain them. PostgreSQL provides the durable
  store; Redis pub/sub (optional) notifies the correct replica to start
  draining on re-attach.

  If Redis is not configured, draining always reads directly from PostgreSQL,
  which is safe (slightly higher latency on large Tether queues).

Configuration (env vars):
  SBP_PG_DSN       PostgreSQL DSN, e.g. postgresql://user:pw@host/db
  SBP_REDIS_URL    Redis URL, e.g. redis://localhost:6379 (optional)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from sbp_server.backends.base import TetherBackend, TetherTurn

logger = logging.getLogger(__name__)

_PG_DSN    = os.environ.get("SBP_PG_DSN", "")
_REDIS_URL = os.environ.get("SBP_REDIS_URL", "")


class PostgresTetherBackend(TetherBackend):
    """
    PostgreSQL-backed Tether queue. Suitable for multi-replica deployments.

    Requires: asyncpg (pip install asyncpg)
    Optional: redis (pip install redis) for cross-replica WebSocket fanout.
    """

    _instance: "PostgresTetherBackend | None" = None

    def __init__(self, dsn: str = _PG_DSN, redis_url: str = _REDIS_URL) -> None:
        self._dsn = dsn
        self._redis_url = redis_url
        self._pool: Any = None
        self._redis: Any = None

    @classmethod
    def instance(cls) -> "PostgresTetherBackend":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        try:
            import asyncpg
        except ImportError:
            raise RuntimeError(
                "asyncpg is required for the PostgreSQL Tether backend. "
                "Install it: pip install asyncpg"
            )

        if not self._dsn:
            raise RuntimeError(
                "SBP_PG_DSN environment variable is not set. "
                "Example: postgresql://user:pw@localhost/sbp"
            )

        logger.info("PostgresTetherBackend: connecting to %s", self._dsn.split("@")[-1])
        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)

        # Ensure schema exists
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)

        # Optional Redis
        if self._redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("PostgresTetherBackend: Redis pub/sub enabled")
            except Exception as exc:
                logger.warning(
                    "PostgresTetherBackend: Redis unavailable (%s). "
                    "Multi-replica fanout disabled — drain falls back to PostgreSQL.",
                    exc,
                )
                self._redis = None

        logger.info("PostgresTetherBackend: ready")

    async def shutdown(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("PostgresTetherBackend: closed")

    def _conn(self):
        if self._pool is None:
            raise RuntimeError(
                "PostgresTetherBackend.startup() has not been called."
            )
        return self._pool.acquire()

    # ── Core operations ───────────────────────────────────────────────────────

    async def enqueue(self, turn: TetherTurn) -> None:
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO tether_turns
                    (id, session_id, step, content, model, extra, buffered_at, acked_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, NULL)
                ON CONFLICT (id) DO NOTHING
                """,
                turn.turn_id,
                turn.session_id,
                turn.step,
                turn.content,
                turn.model,
                json.dumps(turn.extra),
                turn.buffered_at,
            )

        # Notify via Redis so any replica watching this session_id can drain
        if self._redis:
            try:
                await self._redis.publish(
                    f"sbp:tether:{turn.session_id}",
                    json.dumps({"turn_id": turn.turn_id, "step": turn.step}),
                )
            except Exception as exc:
                logger.warning("Redis publish failed (non-fatal): %s", exc)

        logger.debug(
            "Tether enqueue session=%s step=%d turn=%s",
            turn.session_id[:8], turn.step, turn.turn_id[:8],
        )

    async def drain(self, session_id: str) -> list[TetherTurn]:
        async with self._conn() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, step, content, model, extra, buffered_at, acked_at
                FROM tether_turns
                WHERE session_id = $1 AND acked_at IS NULL
                ORDER BY step ASC
                """,
                session_id,
            )

        turns = [
            TetherTurn(
                turn_id=str(r["id"]),
                session_id=str(r["session_id"]),
                step=r["step"],
                content=r["content"],
                model=r["model"],
                buffered_at=r["buffered_at"],
                acked_at=r["acked_at"],
                extra=r["extra"] or {},
            )
            for r in rows
        ]
        logger.debug(
            "Tether drain session=%s → %d pending turns",
            session_id[:8], len(turns),
        )
        return turns

    async def ack(self, session_id: str, turn_ids: list[str]) -> None:
        if not turn_ids:
            return
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE tether_turns
                SET acked_at = now()
                WHERE session_id = $1 AND id = ANY($2::uuid[]) AND acked_at IS NULL
                """,
                session_id,
                turn_ids,
            )
        logger.debug(
            "Tether ack session=%s %d turns", session_id[:8], len(turn_ids)
        )

    async def clear(self, session_id: str) -> int:
        async with self._conn() as conn:
            result = await conn.execute(
                "DELETE FROM tether_turns WHERE session_id = $1",
                session_id,
            )
        # asyncpg returns "DELETE N" string
        count = int(result.split()[-1]) if result else 0
        logger.info("Tether clear session=%s removed %d turns", session_id[:8], count)
        return count

    async def pending_count(self, session_id: str) -> int:
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM tether_turns WHERE session_id = $1 AND acked_at IS NULL",
                session_id,
            )
        return row[0] if row else 0

    async def purge_expired(self, max_age_seconds: int = 30 * 86_400) -> int:
        async with self._conn() as conn:
            result = await conn.execute(
                """
                DELETE FROM tether_turns
                WHERE buffered_at < now() - ($1 || ' seconds')::interval
                """,
                str(max_age_seconds),
            )
        count = int(result.split()[-1]) if result else 0
        if count:
            logger.info("Tether purge_expired removed %d turns older than %ds", count, max_age_seconds)
        return count


# ── DDL (applied at startup) ──────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tether_turns (
    id          UUID PRIMARY KEY,
    session_id  UUID NOT NULL,
    step        INTEGER NOT NULL,
    content     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    extra       JSONB NOT NULL DEFAULT '{}',
    buffered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acked_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tether_session_step
    ON tether_turns (session_id, step);

CREATE INDEX IF NOT EXISTS idx_tether_pending
    ON tether_turns (session_id, acked_at)
    WHERE acked_at IS NULL;
"""
