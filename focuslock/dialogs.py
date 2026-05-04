"""User-facing prompts — prompt.json ↔ response.json IPC.

The locus-windows GUI (PromptHandler) reads prompt.json and shows a native
Qt dialog, then writes response.json.  This module is the daemon side: write
the prompt, block until the GUI responds, return the result.

show_notification uses a Windows toast (PowerShell) so it never blocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Optional, Tuple

from .paths import PROMPT_PATH, RESPONSE_PATH

_prompt_lock = threading.Lock()
_PROMPT_TIMEOUT_SECONDS = 600


# ── Core IPC ──────────────────────────────────────────────────────────────────

def _prompt(prompt: dict, timeout: int = _PROMPT_TIMEOUT_SECONDS) -> dict:
    """Write prompt.json, block until the GUI writes a matching response.json."""
    with _prompt_lock:
        pid = uuid.uuid4().hex
        prompt["id"] = pid

        # Remove any stale response from a previous prompt.
        try:
            os.remove(RESPONSE_PATH)
        except FileNotFoundError:
            pass

        tmp = PROMPT_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(prompt, f)
            os.replace(tmp, PROMPT_PATH)
        except Exception as e:
            print(f"[Locus] prompt write failed: {e}")
            return {}

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with open(RESPONSE_PATH, encoding="utf-8") as f:
                    resp = json.load(f)
                if resp.get("id") == pid:
                    try:
                        os.remove(RESPONSE_PATH)
                    except FileNotFoundError:
                        pass
                    try:
                        os.remove(PROMPT_PATH)
                    except FileNotFoundError:
                        pass
                    return resp
            except FileNotFoundError:
                pass
            except Exception:
                pass
            time.sleep(0.15)

        # Timeout — clean up so the next prompt starts fresh.
        try:
            os.remove(PROMPT_PATH)
        except FileNotFoundError:
            pass
        return {}


# ── Dialog helpers ────────────────────────────────────────────────────────────

def ask_reason(
    blocked_name: str,
    blocked_type: str,
    session_name: str,
) -> Tuple[str, str]:
    """Returns (action, reason). action ∈ {"submit", "override", "cancel"}."""
    resp = _prompt({
        "type": "ask_reason",
        "blocked_name": blocked_name,
        "blocked_type": blocked_type,
        "session_name": session_name,
    })
    action = resp.get("action") or "cancel"
    if action not in ("submit", "override", "cancel"):
        action = "cancel"
    return action, (resp.get("reason") or "").strip()


def ask_override_code(expected: str) -> bool:
    if not expected or not expected.strip():
        show_override_wrong()
        return False
    resp = _prompt({
        "type": "ask_override",
        "is_pi_hint": expected.startswith("3141592653589"),
    })
    if (resp.get("action") or "cancel") != "submit":
        return False
    entered = (resp.get("code") or "").strip()
    if expected.startswith("3141592653589") or expected.isdigit():
        cleaned = "".join(c for c in entered if c.isdigit())
        return cleaned == expected
    return entered == expected.strip()


def show_result(
    approved: bool,
    explanation: str,
    target_name: str,
    minutes: int = 15,
):
    _prompt({
        "type": "show_result",
        "approved": bool(approved),
        "explanation": explanation,
        "target_name": target_name,
        "minutes": int(minutes),
    })


def ask_off_topic_reason(
    domain: str,
    tab_title: str,
    session_name: str,
    ai_reason: str,
) -> Tuple[str, str]:
    resp = _prompt({
        "type": "ask_off_topic",
        "blocked_name": domain,
        "tab_title": tab_title,
        "session_name": session_name,
        "ai_reason": ai_reason,
    })
    action = resp.get("action") or "cancel"
    if action not in ("submit", "cancel"):
        action = "cancel"
    return action, (resp.get("reason") or "").strip()


def ask_long_session(session_name: str, timeout: int = 300) -> str:
    """Returns 'continue' or 'end'. Empty response (timeout) → 'end'."""
    resp = _prompt({
        "type": "long_session",
        "session_name": session_name,
    }, timeout=timeout)
    return "continue" if resp.get("action") == "continue" else "end"


def show_override_wrong():
    show_notification("Locus", "Incorrect override code.")


# ── Non-blocking notification ─────────────────────────────────────────────────

def show_notification(title: str, message: str):
    """Fire-and-forget system notification — never blocks the caller."""
    try:
        if sys.platform == "win32":
            _win_toast(title, message)
        elif sys.platform == "darwin":
            _esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
            script = f'display notification "{_esc(message)}" with title "{_esc(title)}"'
            subprocess.run(["osascript", "-e", script], capture_output=True)
    except Exception:
        pass


def _win_toast(title: str, message: str):
    """Show a Windows toast notification via PowerShell (non-blocking)."""
    # Sanitise strings to avoid PS injection.
    def _esc(s: str) -> str:
        return s.replace("'", "\\'").replace('"', '\\"')[:200]

    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f"$n.ShowBalloonTip(3000, '{_esc(title)}', '{_esc(message)}', "
        "[System.Windows.Forms.ToolTipIcon]::None); "
        "Start-Sleep -Milliseconds 3500; "
        "$n.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
