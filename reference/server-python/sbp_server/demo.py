"""
sbp-demo — interactive multi-surface Tether demonstration.

Four-device cascade:
  💻 Laptop   → streams agent reply, WiFi drops mid-answer
  📱 Phone    → reconnects, recovers full buffered answer
  ⌚ Watch    → new LLM call: agent distils to 2-sentence summary
  🎧 AirPods → macOS 'say' speaks the summary through laptop speakers

Usage:
    sbp-demo
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess

import httpx
import websockets

# ── ANSI colours ──────────────────────────────────────────────────────────────
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SERVER    = "http://localhost:8080"
WS_SERVER = "ws://localhost:8080"
CHAR_LIMIT = 100


# ── Cross-platform TTS ────────────────────────────────────────────────────────

def _speak_sync(text: str) -> bool:
    """Speak text using the best available TTS engine. Returns True if audio played."""
    system = platform.system()

    if system == "Darwin":
        # macOS — built-in 'say'
        if shutil.which("say"):
            subprocess.run(["say", text])
            return True

    elif system == "Linux":
        # Try speech-dispatcher first (Ubuntu/Fedora default), then espeak variants
        for cmd in (["spd-say", "--wait", text], ["espeak", text], ["espeak-ng", text]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd)
                return True

    elif system == "Windows":
        # PowerShell ships on all modern Windows — no install needed
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
        )
        if result.returncode == 0:
            return True

    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _banner(icon: str, label: str) -> None:
    print(f"\n{BOLD}{icon}  {label}{RESET}")
    print(f"{DIM}{'─' * 40}{RESET}")


def _check_env() -> bool:
    missing = [
        v for v in ("SBP_LLM_BASE_URL", "SBP_LLM_API_KEY", "SBP_MODEL", "SBP_JWT_SECRET")
        if not os.environ.get(v)
    ]
    if missing:
        print(f"{RED}Missing environment variables: {', '.join(missing)}{RESET}")
        print("Set them and re-run sbp-demo.")
        return False
    return True


async def _create_session() -> tuple[str, str, str]:
    """Create a new SBP session and capture the agent's opening question.

    Returns (session_id, session_token, greeting_text).
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SERVER}/v1/chat/completions",
            json={
                "model": os.environ["SBP_MODEL"],
                "messages": [
                    {"role": "user", "content": "Ask me what I'd like to explore today. One sentence only."},
                ],
                "sbp": {},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    session_id    = data["sbp"]["session_id"]
    session_token = data["sbp"]["session_token"]

    try:
        greeting_text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        greeting_text = "What would you like to explore today?"

    return session_id, session_token, greeting_text


async def _fire(tok: str, messages: list[dict]) -> None:
    """Fire a streaming completions request — server routes chunks to the connected WS surface."""
    async with httpx.AsyncClient(timeout=120) as client:
        await client.post(
            f"{SERVER}/v1/chat/completions",
            json={
                "model": os.environ["SBP_MODEL"],
                "stream": True,
                "messages": messages,
                "sbp": {},
            },
            headers={"X-Session-Token": tok},
        )


async def _attach(sid: str, tok: str, device: str):
    """Open a WebSocket, send ATTACH_SESSION, wait for SESSION_ATTACHED."""
    uri = f"{WS_SERVER}/v1/sbp/ws/{sid}"
    ws = await websockets.connect(uri)
    await ws.send(json.dumps({
        "type": "ATTACH_SESSION", "session_id": sid,
        "session_token": tok, "surface_context": {"device_type": device},
    }))
    while True:
        frame = json.loads(await ws.recv())
        if frame["type"] == "SESSION_ATTACHED":
            return ws, frame


# ── Device phases ─────────────────────────────────────────────────────────────

async def _laptop_phase(sid: str, tok: str, question: str) -> None:
    _banner("💻", "LAPTOP")
    print(f"You: {question}\n", flush=True)

    ws, _ = await _attach(sid, tok, "desktop")
    chars_shown = 0
    first_chunk = True

    try:
        messages = [{"role": "user", "content": question}]
        asyncio.create_task(_fire(tok, messages))
        while True:
            try:
                frame_str = await asyncio.wait_for(ws.recv(), timeout=30)
                frame = json.loads(frame_str)
                ftype = frame.get("type", "")

                if ftype == "TURN_CHUNK":
                    content = frame.get("content", "")
                    if first_chunk:
                        print(f"{BOLD}Agent:{RESET} ", end="", flush=True)
                        first_chunk = False
                    print(f"{CYAN}{content}{RESET}", end="", flush=True)
                    chars_shown += len(content)
                    if chars_shown >= CHAR_LIMIT:
                        print(f"\n\n{RED}📶  WiFi dropped — you walked out the door{RESET}\n",
                              flush=True)
                        break

                elif ftype == "TURN_COMPLETE":
                    print()
                    break

            except asyncio.TimeoutError:
                break
    finally:
        await ws.close()
    # Closing the WebSocket signals the server to queue remaining content as TETHER_TURN.


async def _phone_phase(sid: str, tok: str) -> str:
    """Reconnect on mobile and recover the buffered answer. Returns the full recovered text."""
    _banner("📱", "PHONE")

    ws, attached = await _attach(sid, tok, "mobile")
    queued = attached.get("queued_turns", 0)
    print(f"{GREEN}✅  Reconnected{RESET}", flush=True)
    if queued:
        print(f"{GREEN}📬  Recovering {queued} buffered turn(s)...{RESET}\n", flush=True)

    recovered_text = ""
    try:
        while True:
            try:
                frame_str = await asyncio.wait_for(ws.recv(), timeout=15)
                frame = json.loads(frame_str)
                ftype = frame.get("type", "")

                if ftype == "TETHER_TURN":
                    content = frame.get("content", "")
                    recovered_text = content
                    print(f"{CYAN}{content}{RESET}", flush=True)
                    break

                elif ftype == "TURN_COMPLETE":
                    break

            except asyncio.TimeoutError:
                break
    finally:
        await ws.close()

    return recovered_text


async def _watch_phase(sid: str, tok: str, original_question: str, full_answer: str) -> str:
    """Ask the LLM to distil the conversation to 2 sentences. Returns the summary text."""
    _banner("⌚", "APPLE WATCH")
    print(f"{DIM}Asking agent for a watch-sized summary...{RESET}\n", flush=True)

    ws, _ = await _attach(sid, tok, "iot")
    summary = ""
    first_chunk = True

    # Provide full conversation context so the LLM can actually summarise it
    messages = [
        {"role": "user",      "content": original_question},
        {"role": "assistant", "content": full_answer},
        {"role": "user",      "content": (
            "Summarise your previous answer in exactly 2 short sentences, "
            "30 words maximum. No preamble — just the summary."
        )},
    ]

    try:
        asyncio.create_task(_fire(tok, messages))
        while True:
            try:
                frame_str = await asyncio.wait_for(ws.recv(), timeout=30)
                frame = json.loads(frame_str)
                ftype = frame.get("type", "")

                if ftype == "TURN_CHUNK":
                    content = frame.get("content", "")
                    if first_chunk:
                        print(f"{BOLD}Agent:{RESET} ", end="", flush=True)
                        first_chunk = False
                    print(f"{CYAN}{content}{RESET}", end="", flush=True)
                    summary += content

                elif ftype == "TURN_COMPLETE":
                    print()
                    break

            except asyncio.TimeoutError:
                break
    finally:
        await ws.close()

    return summary


async def _airpods_phase(sid: str, tok: str, original_question: str, full_answer: str) -> None:
    """Ask the LLM for a voice-friendly version, then speak it aloud."""
    _banner("🎧", "AIRPODS")
    print(f"{DIM}Generating audio version...{RESET}\n", flush=True)

    # Ask for a voice-optimised rendition — conversational, no markdown
    messages = [
        {"role": "user",      "content": original_question},
        {"role": "assistant", "content": full_answer},
        {"role": "user",      "content": (
            "Give me a spoken-word version of your answer — 2 sentences max, "
            "no bullet points, no markdown, natural conversational tone, "
            "as if you're speaking directly to me."
        )},
    ]

    spoken_text = ""
    first_chunk = True
    ws, _ = await _attach(sid, tok, "wearable")

    try:
        asyncio.create_task(_fire(tok, messages))
        while True:
            try:
                frame_str = await asyncio.wait_for(ws.recv(), timeout=30)
                frame = json.loads(frame_str)
                ftype = frame.get("type", "")

                if ftype == "TURN_CHUNK":
                    content = frame.get("content", "")
                    if first_chunk:
                        print(f"{BOLD}Agent:{RESET} ", end="", flush=True)
                        first_chunk = False
                    print(f"{CYAN}{content}{RESET}", end="", flush=True)
                    spoken_text += content

                elif ftype == "TURN_COMPLETE":
                    print()
                    break

            except asyncio.TimeoutError:
                break
    finally:
        await ws.close()

    if not spoken_text.strip():
        print(f"{DIM}Nothing to speak.{RESET}")
        return

    print(f"\n{GREEN}Speaking through your speakers...{RESET}\n", flush=True)
    loop = asyncio.get_running_loop()
    played = await loop.run_in_executor(None, _speak_sync, spoken_text)
    if played:
        print(f"{GREEN}✅  Playback complete{RESET}", flush=True)
    else:
        system = platform.system()
        hints = {
            "Linux":   "Install espeak:  sudo apt install espeak   (or dnf install espeak)",
            "Windows": "PowerShell not found — update Windows or install PowerShell 7+",
            "Darwin":  "'say' not found — this shouldn't happen on macOS",
        }
        hint = hints.get(system, f"No TTS engine found on {system}")
        print(f"{YELLOW}⚠️  Could not play audio — {hint}{RESET}")
        print(f"{DIM}Text that would have been spoken:{RESET}")
        print(f"{CYAN}{spoken_text}{RESET}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not _check_env():
        return

    print(f"\n{BOLD}━━━ SBP Tether Demo ━━━{RESET}")
    print("Your AI agent survives the commute home.\n")
    print(f"{DIM}💻 Laptop → 📱 Phone → ⌚ Watch → 🎧 AirPods{RESET}")

    print(f"\n{YELLOW}Starting session...{RESET}", flush=True)

    try:
        sid, tok, greeting_text = asyncio.run(_create_session())
    except Exception as exc:
        print(f"{RED}Cannot reach server: {exc}{RESET}")
        print("Is sbp-server running on port 8080?")
        return

    print(f"{GREEN}Connected ✓{RESET}\n", flush=True)
    print(f"{BOLD}Agent:{RESET} {CYAN}{greeting_text}{RESET}\n", flush=True)

    try:
        question = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not question:
        question = "What are the most interesting unsolved problems in mathematics?"

    asyncio.run(_run_with_session(sid, tok, question))


async def _run_with_session(sid: str, tok: str, question: str) -> None:
    """Run the four-device cascade using an already-created session."""
    # 1 ─ Laptop: streams answer, WiFi drops mid-answer
    await _laptop_phase(sid, tok, question)

    print(f"{YELLOW}[ Agent keeps thinking in the background... ]{RESET}", flush=True)
    await asyncio.sleep(8)

    # 2 ─ Phone: recovers full buffered answer
    full_answer = await _phone_phase(sid, tok)
    await asyncio.sleep(1)

    # 3 ─ Watch: real LLM call with full context, agent distils to 2-sentence summary
    await _watch_phase(sid, tok, question, full_answer)
    await asyncio.sleep(1)

    # 4 ─ AirPods: its own LLM call → voice-friendly text → spoken aloud
    await _airpods_phase(sid, tok, question, full_answer)


if __name__ == "__main__":
    main()
