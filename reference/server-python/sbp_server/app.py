"""
SBP Reference Server — FastAPI application factory.

Wires the in-memory backend by default. To use a custom backend:

    from your_package import MySessionStore, MyTetherQueue, ...
    app = create_app(
        session_store=MySessionStore(...),
        tether_queue=MyTetherQueue(...),
        snapshot_store=MySnapshotStore(...),
        roaming_store=MyRoamingTokenStore(...),
    )
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI

from sbp_server.backends.memory import make_in_memory_backends
from sbp_server.routers import completions, sbp, sbp_ws

logger = logging.getLogger(__name__)


def create_app(
    *,
    session_store: Any = None,
    tether_queue: Any = None,
    snapshot_store: Any = None,
    roaming_store: Any = None,
) -> FastAPI:
    """
    Create and return the FastAPI application.

    Pass custom backend implementations to override the in-memory defaults.
    All four backends must be provided together or not at all.
    """
    app = FastAPI(
        title="SBP Reference Server",
        description=(
            "State Bridge Protocol v0.9 — L5 conformant reference implementation. "
            "Model-agnostic: point SBP_LLM_BASE_URL at any OpenAI-compatible endpoint."
        ),
        version="0.9.0",
    )

    # ── Backend wiring ────────────────────────────────────────────────────────
    if any(b is not None for b in [session_store, tether_queue, snapshot_store, roaming_store]):
        if not all(b is not None for b in [session_store, tether_queue, snapshot_store, roaming_store]):
            raise ValueError(
                "All four backends must be provided together: "
                "session_store, tether_queue, snapshot_store, roaming_store"
            )
        app.state.session_store = session_store
        app.state.tether_queue = tether_queue
        app.state.snapshot_store = snapshot_store
        app.state.roaming_store = roaming_store
        logger.info("SBP: using custom backends")
    else:
        ss, tq, snp, rs = make_in_memory_backends()
        app.state.session_store = ss
        app.state.tether_queue = tq
        app.state.snapshot_store = snp
        app.state.roaming_store = rs
        logger.info("SBP: using in-memory backends (development only)")

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(completions.router, prefix="/v1")
    app.include_router(sbp.router, prefix="/v1/sbp")
    app.include_router(sbp_ws.router, prefix="/v1/sbp")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "sbp_version": "0.9"}

    return app
