#!/usr/bin/env python3
"""
SBP Conformance Test Runner

Validates a server URL against a conformance level (L1–L5).

Usage:
  python conformance/runner.py --target http://localhost:8080 --level L3
  python conformance/runner.py --target http://localhost:8080 --level L5 --verbose

Exit code 0 = all required tests passed.
Exit code 1 = one or more tests failed or errored.

NOTE: WebSocket tests (L4, L5) require the 'websockets' package:
  pip install websockets
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(2)

LEVELS = ["L1", "L2", "L3", "L4", "L5"]

# Which test directories are included at each level (cumulative)
LEVEL_DIRS: dict[str, list[str]] = {
    "L1": ["L1-stateful-proxy"],
    "L2": ["L1-stateful-proxy", "L2-resume"],
    "L3": ["L1-stateful-proxy", "L2-resume", "L3-roaming"],
    "L4": ["L1-stateful-proxy", "L2-resume", "L3-roaming", "L4-surfaces"],
    "L5": ["L1-stateful-proxy", "L2-resume", "L3-roaming", "L4-surfaces", "L5-mcp-bridge"],
}

TESTS_DIR = Path(__file__).parent / "tests"

# State shared across steps within a test
_ctx: dict[str, Any] = {}


def _interpolate(obj: Any, ctx: dict) -> Any:
    """Replace ${var} placeholders with values from ctx."""
    if isinstance(obj, str):
        for key, val in ctx.items():
            obj = obj.replace(f"${{{key}}}", str(val))
        return obj
    if isinstance(obj, dict):
        return {k: _interpolate(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate(i, ctx) for i in obj]
    return obj


def _extract(data: dict, response: httpx.Response, ctx: dict) -> None:
    """Pull values from a response into ctx for later steps."""
    for name, path in data.items():
        if path.startswith("headers."):
            header = path[len("headers."):]
            ctx[name] = response.headers.get(header, "")
        elif path.startswith("$."):
            try:
                body = response.json()
                parts = path[2:].split(".")
                val = body
                for p in parts:
                    val = val[p]
                ctx[name] = val
            except Exception:
                ctx[name] = None


def _check_body(expect: dict, body: dict, ctx: dict, label: str) -> list[str]:
    """Return a list of failure messages for body assertions."""
    failures: list[str] = []
    contains = expect.get("body_contains", {})
    for dotpath, expected in contains.items():
        parts = dotpath.split(".")
        actual = body
        try:
            for p in parts:
                actual = actual[p]
        except (KeyError, TypeError):
            failures.append(f"  {label}: body missing field '{dotpath}'")
            continue

        if isinstance(expected, str):
            exp = _interpolate(expected, ctx)
            if actual != exp:
                failures.append(f"  {label}: '{dotpath}' expected '{exp}' got '{actual}'")
        elif isinstance(expected, bool):
            if actual is not expected:
                failures.append(f"  {label}: '{dotpath}' expected {expected} got {actual}")
        elif isinstance(expected, dict):
            typ = expected.get("type")
            if typ == "string" and not isinstance(actual, str):
                failures.append(f"  {label}: '{dotpath}' expected string, got {type(actual).__name__}")
            if typ == "number" and not isinstance(actual, (int, float)):
                failures.append(f"  {label}: '{dotpath}' expected number, got {type(actual).__name__}")
            if "format" in expected and expected["format"] == "uuid":
                try:
                    uuid.UUID(str(actual))
                except ValueError:
                    failures.append(f"  {label}: '{dotpath}' is not a valid UUID: '{actual}'")
            if "not_equal" in expected:
                ne = _interpolate(expected["not_equal"], ctx)
                if str(actual) == ne:
                    failures.append(f"  {label}: '{dotpath}' must not equal '{ne}' but did")
            if "min" in expected:
                if actual < expected["min"]:
                    failures.append(f"  {label}: '{dotpath}' expected >= {expected['min']}, got {actual}")
            if "pattern" in expected:
                if not re.match(expected["pattern"], str(actual)):
                    failures.append(f"  {label}: '{dotpath}' does not match pattern '{expected['pattern']}'")
    return failures


async def _run_http_step(
    client: httpx.AsyncClient,
    target: str,
    step: dict,
    ctx: dict,
    verbose: bool,
) -> tuple[bool, list[str]]:
    req = _interpolate(step.get("request", {}), ctx)
    method = req.get("method", "GET")
    path = req.get("path", "/")
    headers = req.get("headers", {})
    body = req.get("body")

    url = target.rstrip("/") + path
    if verbose:
        print(f"    → {method} {url}")

    try:
        resp = await client.request(method, url, json=body, headers=headers)
    except Exception as exc:
        return False, [f"  HTTP error: {exc}"]

    if verbose:
        print(f"    ← {resp.status_code}")

    expect = step.get("expect", {})
    failures: list[str] = []

    status = expect.get("status")
    status_oneof = expect.get("status_oneof")
    if status is not None and resp.status_code != status:
        failures.append(f"  expected status {status}, got {resp.status_code}")
    if status_oneof and resp.status_code not in status_oneof:
        failures.append(f"  expected status in {status_oneof}, got {resp.status_code}")

    headers_include = expect.get("headers_include", [])
    for h in headers_include:
        if h not in resp.headers:
            failures.append(f"  missing expected header: '{h}'")

    try:
        body_json = resp.json()
    except Exception:
        body_json = {}

    failures += _check_body(expect, body_json, ctx, step.get("id", "?"))

    # Extract values for subsequent steps
    if "extract" in step:
        _extract(step["extract"], resp, ctx)

    return len(failures) == 0, failures


async def _run_ws_test(target: str, test: dict, ctx: dict, verbose: bool) -> tuple[bool, list[str]]:
    """Run a WebSocket-based test. Returns (passed, failure_messages)."""
    try:
        import websockets
    except ImportError:
        return False, ["  websockets package required: pip install websockets"]

    ws_target = target.replace("http://", "ws://").replace("https://", "wss://")
    failures: list[str] = []

    for step in test.get("steps", []):
        if step.get("protocol") == "http":
            async with httpx.AsyncClient() as client:
                ok, errs = await _run_http_step(client, target, step, ctx, verbose)
                if not ok:
                    failures.extend(errs)
            continue

        if step.get("protocol") in ("websocket", "websocket_continue"):
            connect_path = _interpolate(step.get("connect", ""), ctx)
            url = ws_target.rstrip("/") + connect_path
            send_frame = _interpolate(step.get("send", {}), ctx)
            expect_receive = step.get("expect_receive", {})
            expect_sequence = step.get("expect_receive_sequence", [])
            expect_close_code = step.get("expect_close_code")

            if verbose:
                print(f"    → WS {url}")

            try:
                async with websockets.connect(url) as ws:
                    await ws.send(json.dumps(send_frame))

                    if expect_sequence:
                        for exp in expect_sequence:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            frame = json.loads(raw)
                            if "type" in exp and frame.get("type") != exp["type"]:
                                failures.append(
                                    f"  WS: expected frame type '{exp['type']}', got '{frame.get('type')}'"
                                )
                            for k, v in exp.items():
                                if k == "type":
                                    continue
                                actual = frame.get(k)
                                exp_val = _interpolate(v, ctx) if isinstance(v, str) else v
                                if actual != exp_val:
                                    failures.append(f"  WS: frame['{k}'] expected {exp_val!r}, got {actual!r}")
                    elif expect_receive:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        frame = json.loads(raw)
                        for k, v in expect_receive.items():
                            actual = frame.get(k)
                            exp_val = _interpolate(v, ctx) if isinstance(v, str) else v
                            if actual != exp_val:
                                failures.append(f"  WS: frame['{k}'] expected {exp_val!r}, got {actual!r}")

            except asyncio.TimeoutError:
                failures.append(f"  WS: timed out waiting for frame")
            except Exception as exc:
                if expect_close_code:
                    # Connection closed — check close code
                    code = getattr(exc, "code", None)
                    if code != expect_close_code:
                        failures.append(f"  WS: expected close code {expect_close_code}, got {code}")
                else:
                    failures.append(f"  WS error: {exc}")

    return len(failures) == 0, failures


async def run_test(
    target: str,
    test_file: Path,
    verbose: bool,
) -> tuple[bool, str, list[str]]:
    """Run one test file. Returns (passed, description, failures)."""
    with open(test_file) as f:
        test = json.load(f)

    description = test.get("description", test_file.name)
    ctx: dict[str, Any] = {}

    transport = test.get("transport", "http")

    if transport == "websocket":
        passed, failures = await _run_ws_test(target, test, ctx, verbose)
        return passed, description, failures

    # HTTP single-step or multi-step
    steps = test.get("steps", [])
    if not steps:
        # Single-step shorthand
        steps = [{"id": "main", "request": test.get("request", {}), "expect": test.get("expect", {})}]

    failures: list[str] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for step in steps:
            if step.get("note"):
                continue  # note-only steps are documentation
            ok, errs = await _run_http_step(client, target, step, ctx, verbose)
            if not ok:
                failures.extend(errs)

    return len(failures) == 0, description, failures


async def main() -> int:
    parser = argparse.ArgumentParser(description="SBP Conformance Test Runner")
    parser.add_argument("--target", required=True, help="Server URL, e.g. http://localhost:8080")
    parser.add_argument(
        "--level", required=True, choices=LEVELS,
        help="Conformance level to test (cumulative: L3 runs L1+L2+L3)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show HTTP request/response details")
    args = parser.parse_args()

    dirs = LEVEL_DIRS[args.level]
    test_files: list[Path] = []
    for d in dirs:
        test_dir = TESTS_DIR / d
        if test_dir.exists():
            test_files.extend(sorted(test_dir.glob("*.json")))

    if not test_files:
        print(f"No test files found for level {args.level} under {TESTS_DIR}")
        return 1

    print(f"\nSBP Conformance Suite — Level {args.level}")
    print(f"Target: {args.target}")
    print(f"Tests:  {len(test_files)}\n")

    passed_count = 0
    failed_count = 0

    for test_file in test_files:
        passed, description, failures = await run_test(args.target, test_file, args.verbose)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {description}")
        if not passed:
            for msg in failures:
                print(msg)
            failed_count += 1
        else:
            passed_count += 1

    print(f"\nResults: {passed_count} passed, {failed_count} failed")

    if failed_count == 0:
        print(f"\n✓ Server is SBP {args.level} conformant.\n")
        return 0
    else:
        print(f"\n✗ Server is NOT conformant at level {args.level}.\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
