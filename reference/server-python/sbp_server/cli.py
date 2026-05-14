"""
sbp-server CLI — start the SBP reference server.

Usage:
  sbp-server start [--host HOST] [--port PORT] [--reload]

Environment variables:
  SBP_LLM_BASE_URL   Any OpenAI-compatible base URL (required)
  SBP_LLM_API_KEY    API key for the LLM provider (required)
  SBP_JWT_SECRET     HS256 signing secret (min 32 chars, required for L3)
  SBP_PORT           Override listen port (default: 8080)
  SBP_LOG_LEVEL      Logging level (default: info)
  SBP_DEFAULT_MODEL  Default model if request omits 'model' (default: gpt-4o)
"""
from __future__ import annotations

import logging
import os
import sys

import typer
import uvicorn

app = typer.Typer(help="State Bridge Protocol reference server", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the SBP server version."""
    from sbp_server import __version__
    typer.echo(f"sbp-server {__version__} (SBP wire version 0.9)")


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(
        int(os.environ.get("SBP_PORT", "8080")),
        help="Listen port",
    ),
    reload: bool = typer.Option(False, help="Enable auto-reload (development only)"),
    log_level: str = typer.Option(
        os.environ.get("SBP_LOG_LEVEL", "info"),
        help="Logging level",
    ),
) -> None:
    """Start the SBP reference server."""
    llm_url = os.environ.get("SBP_LLM_BASE_URL", "")
    jwt_secret = os.environ.get("SBP_JWT_SECRET", "")

    if not llm_url:
        typer.echo("ERROR: SBP_LLM_BASE_URL is required", err=True)
        typer.echo("  export SBP_LLM_BASE_URL=https://api.openai.com/v1", err=True)
        sys.exit(1)

    if not jwt_secret:
        typer.echo(
            "WARNING: SBP_JWT_SECRET is not set — L3 Roaming endpoints will return 503",
            err=True,
        )
    elif len(jwt_secret) < 32:
        typer.echo(
            "WARNING: SBP_JWT_SECRET is shorter than 32 characters — consider a longer secret",
            err=True,
        )

    typer.echo(f"SBP reference server starting on {host}:{port}")
    typer.echo(f"  LLM backend: {llm_url}")
    typer.echo(f"  Log level:   {log_level}")

    uvicorn.run(
        "sbp_server.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    app()
