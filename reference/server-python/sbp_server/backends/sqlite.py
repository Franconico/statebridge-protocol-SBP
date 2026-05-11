"""
SBP Tether Backend — SQLite (Tier 0, default).

Zero external dependencies. Single-node. File-based durability.

The Tether queue is a single SQLite table:

  tether_turns(
    id          TEXT PRIMARY KEY,   -- turn_id (UUID)
    session_id  TEXT NOT NULL,
    step        INTEGER NOT NULL,
    content     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    extra_json  TEXT NOT NULL DEFAULT '{}',
    buffered_at TEXT NOT NULL,      -- ISO-8601 UTC
    acked_at    TEXT                -- NULL = pending
  )

Design notes:
  - aiosqlite provides async I/O without a thread pool.
  - WAL mode: concurrent reads do not block writes.
  - Idempotency: INSERT OR IGNORE on turn_id.
  - All operations use parameterised queries (no string interpolation).
  - startup() creates the table if it doesn't exist — safe to call multiple times.

Configuration (via settings or env):
  SBP_SQLITE_PATH   Path to the SQLite file.
                    Default: ./sbp_tether.db
                    Use ":memory:" for tests (NOT production-safe).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from sbp_server.backends.base import TetherBackend, TetherTurn

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.environ.get("SBP_SQLITE_PATH", "./sbp_tether.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tether_turns (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    step        INTEGER NOT NULL,
    content     TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    extra_json  TEXT NOT NULL DEFAULT '{}',
    buffered_at TEXT NOT NULL,
    acked_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tether_session_step
    ON tether_turns (session_id, step);
CREATE INDEX IF NOT EXISTS idx_tether_acked
    ON tether_turns (session_id, acked_at);
"""


def _row_to_turn(row: aiosqlite.Row) -> TetherTurn:
    return TetherTurn(
        turn_id=row["id"],
        session_id=row["session_id"],
        step=row["step"],
        content=row["content"],
        model=row["model"],
        buffered_at=datetime.fromisoformat(row["buffered_at"]),
        acked_at=datetime.fromisoformat(row["acked_at"]) if row["acked_at"] else None,
        extra=json.loads(row["extra_json"] or "{}"),
    )


class SQLiteTetherBackend(TetherBackend):
    """
    SQLite-backed Tether queue. Zero external dependencies.

    Single-node only. For multi-replica deployments, use PostgresTetherBackend.
    """

    _instance: "SQLiteTetherBackend | None" = None

    def __init__(self, db_path: str = _DEFAULT_PATH) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    @classmethod
    def instance(cls) -> "SQLiteTetherBackend":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        logger.info("SQLiteTetherBackend: opening %s", self._db_path)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        # WAL mode — concurrent readers don't block writers
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_CREATE_TABLE)
        await self._db.commit()
        logger.info("SQLiteTetherBackend: ready")

    async def shutdown(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
        logger.info("SQLiteTetherBackend: closed")

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError(
                "SQLiteTetherBackend.startup() has not been called. "
                "Ensure it is awaited during application startup."
            )
        return self._db

    # ── Core operations ───────────────────────────────────────────────────────

    async def enqueue(self, turn: TetherTurn) -> None:
        db = self._conn()
        await db.execute(
            """
            INSERT OR IGNORE INTO tether_turns
                (id, session_id, step, content, model, extra_json, buffered_at, acked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                turn.turn_id,
                turn.session_id,
                turn.step,
                turn.content,
                turn.model,
                json.dumps(turn.extra),
                turn.buffered_at.isoformat(),
            ),
        )
        await db.commit()
        logger.debug(
            "Tether enqueue session=%s step=%d turn=%s",
            turn.session_id[:8], turn.step, turn.turn_id[:8],
        )

    async def drain(self, session_id: str) -> list[TetherTurn]:
        db = self._conn()
        async with db.execute(
            """
            SELECT * FROM tether_turns
            WHERE session_id = ? AND acked_at IS NULL
            ORDER BY step ASC
            """,
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        turns = [_row_to_turn(r) for r in rows]
        logger.debug(
            "Tether drain session=%s → %d pending turns",
            session_id[:8], len(turns),
        )
        return turns

    async def ack(self, session_id: str, turn_ids: list[str]) -> None:
        if not turn_ids:
            return
        db = self._conn()
        now = datetime.now(UTC).isoformat()
        placeholders = ",".join("?" * len(turn_ids))
        await db.execute(
            f"""
            UPDATE tether_turns
            SET acked_at = ?
            WHERE session_id = ? AND id IN ({placeholders}) AND acked_at IS NULL
            """,
            [now, session_id, *turn_ids],
        )
        await db.commit()
        logger.debug(
            "Tether ack session=%s %d turns", session_id[:8], len(turn_ids)
        )

    async def clear(self, session_id: str) -> int:
        db = self._conn()
        cursor = await db.execute(
            "DELETE FROM tether_turns WHERE session_id = ?",
            (session_id,),
        )
        await db.commit()
        count = cursor.rowcount
        logger.info("Tether clear session=%s removed %d turns", session_id[:8], count)
        return count

    async def pending_count(self, session_id: str) -> int:
        db = self._conn()
        async with db.execute(
            "SELECT COUNT(*) FROM tether_turns WHERE session_id = ? AND acked_at IS NULL",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def purge_expired(self, max_age_seconds: int = 30 * 86_400) -> int:
        """Remove turns older than max_age_seconds (default 30 days)."""
        db = self._conn()
        cutoff = datetime.now(UTC).timestamp() - max_age_seconds
        # buffered_at is stored as ISO-8601; SQLite can compare ISO strings lexicographically
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()
        cursor = await db.execute(
            "DELETE FROM tether_turns WHERE buffered_at < ?",
            (cutoff_iso,),
        )
        await db.commit()
        count = cursor.rowcount
        if count:
            logger.info("Tether purge_expired removed %d turns older than %ds", count, max_age_seconds)
        return count
