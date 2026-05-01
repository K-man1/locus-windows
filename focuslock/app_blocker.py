"""Block all apps except those on the whitelist — Windows implementation.

Uses ctypes (Win32 API) to enumerate visible GUI windows, psutil to map
PIDs to process names, and taskkill to terminate disallowed processes.
"""

import ctypes
import ctypes.wintypes
import os
import psutil
import subprocess
import threading
import time
from typing import Set, Dict, Callable, Optional, List

try:
    from .analytics import log_event as _log_event
except Exception:
    def _log_event(*a, **kw): pass


# Always allowed, regardless of session
ALWAYS_ALLOWED = {
    "explorer",                   # Windows Explorer / desktop shell
    "chrome", "msedge", "brave", "vivaldi", "opera", "firefox",
    "Locus", "locusd", "tray_app",
    "python", "python3", "pythonw", "python3.exe",
    "cmd", "powershell", "pwsh", "WindowsTerminal",
    "taskmgr",                    # Task Manager
    "SearchHost", "SearchApp", "StartMenuExperienceHost", "ShellExperienceHost",
    "RuntimeBroker", "SystemSettings", "TextInputHost", "LockApp",
    "dwm", "winlogon", "csrss", "svchost",
    "SecurityHealthSystray", "SecurityHealthService",
    "sihost", "ctfmon",
    "conhost", "fontdrvhost", "lsass", "services", "wininit",
    "audiodg", "spoolsv",
}

# Substrings — any process whose name contains one of these is always allowed
ALWAYS_ALLOWED_SUBSTRINGS = ("Helper", "Agent", "Daemon", "Service", "Host", "Runtime")


# ── Win32 constants / types ───────────────────────────────────────────────────

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WS_VISIBLE = 0x10000000
GW_OWNER = 4

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,
                                  ctypes.wintypes.HWND,
                                  ctypes.wintypes.LPARAM)


def _enum_windows_callback(hwnd, pid_set_ptr):
    """Called by EnumWindows for every top-level window."""
    # Must be visible and have a non-empty title
    if not _user32.IsWindowVisible(hwnd):
        return True
    length = _user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    pid = ctypes.wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value:
        pid_set = ctypes.cast(pid_set_ptr, ctypes.py_object).value
        pid_set.add(pid.value)
    return True


def _get_running_gui_pids() -> Set[int]:
    """Return PIDs of all processes that own a visible titled window."""
    pid_set: Set[int] = set()
    cb = WNDENUMPROC(_enum_windows_callback)
    _user32.EnumWindows(cb, ctypes.cast(ctypes.py_object(pid_set), ctypes.c_void_p))
    return pid_set


def _get_foreground_pid() -> Optional[int]:
    """Return the PID of the process that owns the foreground window."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value if pid.value else None


class AppBlocker:
    def __init__(self, on_blocked: Callable[[str], None], poll_seconds: float = 2,
                 extra_always_allowed: Optional[List[str]] = None):
        self.session_allowed: Set[str] = set()
        self.temporarily_allowed: Dict[str, float] = {}
        self.user_always_allowed: Set[str] = set(extra_always_allowed or [])
        self.on_blocked = on_blocked
        self.poll_seconds = max(0.5, float(poll_seconds))
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._focus_thread: Optional[threading.Thread] = None
        self._handling: Set[str] = set()
        self._focus_app: Optional[str] = None
        self._focus_since: float = 0.0
        self.session_name: str = ""

    def set_session_allowed(self, apps: List[str]):
        self.session_allowed = set(apps)

    def allow_temporarily(self, app_name: str, minutes: int = 15):
        self.temporarily_allowed[app_name] = time.time() + minutes * 60
        self._handling.discard(app_name)

    def deny(self, app_name: str):
        self._handling.discard(app_name)

    def start(self):
        if self._running:
            return
        self._running = True
        self._focus_app = None
        self._focus_since = time.time()
        # Silent sweep: terminate every disallowed app currently running,
        # without firing dialogs — avoids stacking 5 prompts on session start.
        try:
            for app_name in self._get_running_gui_apps():
                if not self._is_allowed(app_name):
                    self._terminate_app(app_name)
        except Exception:
            pass
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._focus_thread = threading.Thread(target=self._focus_loop, daemon=True)
        self._focus_thread.start()

    def stop(self):
        self._flush_focus()
        self._running = False
        self.session_allowed.clear()
        self.temporarily_allowed.clear()
        self._handling.clear()
        self._focus_app = None

    def _is_allowed(self, app_name: str) -> bool:
        # Case-insensitive comparison for Windows process names
        name_lower = app_name.lower()
        if app_name in ALWAYS_ALLOWED or name_lower in {a.lower() for a in ALWAYS_ALLOWED}:
            return True
        if app_name in self.user_always_allowed:
            return True
        if any(sub.lower() in name_lower for sub in ALWAYS_ALLOWED_SUBSTRINGS):
            return True
        if app_name in self.session_allowed:
            return True
        if name_lower in {a.lower() for a in self.session_allowed}:
            return True
        if app_name in self.temporarily_allowed:
            if self.temporarily_allowed[app_name] > time.time():
                return True
            del self.temporarily_allowed[app_name]
        if name_lower in {a.lower(): v for a, v in self.temporarily_allowed.items()}:
            # Also check case-insensitive in temporarily_allowed
            for k, v in list(self.temporarily_allowed.items()):
                if k.lower() == name_lower:
                    if v > time.time():
                        return True
                    del self.temporarily_allowed[k]
        return False

    def _get_running_gui_apps(self) -> List[str]:
        """Return deduplicated list of process names that own visible titled windows."""
        try:
            pids = _get_running_gui_pids()
        except Exception:
            return []
        names: List[str] = []
        seen: Set[str] = set()
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.pid in pids:
                        raw = proc.info["name"] or ""
                        # Strip .exe extension for consistent matching
                        name = raw[:-4] if raw.lower().endswith(".exe") else raw
                        if name and name not in seen:
                            seen.add(name)
                            names.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return names

    def _terminate_app(self, app_name: str):
        """Force-kill a process by name using taskkill."""
        # Try with .exe suffix
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{app_name}.exe"],
            capture_output=True,
        )
        # Also try without suffix (some processes register without it)
        subprocess.run(
            ["taskkill", "/F", "/IM", app_name],
            capture_output=True,
        )

    def _loop(self):
        while self._running:
            try:
                running = self._get_running_gui_apps()
                for app_name in running:
                    if self._is_allowed(app_name):
                        continue
                    if app_name in self._handling:
                        # Already showing dialog — keep killing if it re-opens
                        self._terminate_app(app_name)
                        continue
                    # New violation
                    self._handling.add(app_name)
                    self._terminate_app(app_name)
                    threading.Thread(
                        target=self._handle_violation,
                        args=(app_name,),
                        daemon=True,
                    ).start()
            except Exception as e:
                print(f"[Locus] App blocker error: {e}")
            time.sleep(self.poll_seconds)

    def _handle_violation(self, app_name: str):
        try:
            self.on_blocked(app_name)
        finally:
            self._handling.discard(app_name)

    def _get_frontmost_app(self) -> Optional[str]:
        """Return the name of the process owning the current foreground window."""
        try:
            pid = _get_foreground_pid()
            if not pid:
                return None
            proc = psutil.Process(pid)
            raw = proc.name() or ""
            return raw[:-4] if raw.lower().endswith(".exe") else raw
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            return None

    def _flush_focus(self):
        app = self._focus_app
        if app and self._focus_since:
            dur = int(time.time() - self._focus_since)
            if dur >= 2:
                try:
                    _log_event("app_focus", app_name=app, duration_seconds=dur,
                               session_name=self.session_name)
                except Exception:
                    pass
        self._focus_app = None
        self._focus_since = 0.0

    def _focus_loop(self):
        while self._running:
            time.sleep(3)
            if not self._running:
                break
            try:
                current = self._get_frontmost_app()
                if current and current != self._focus_app:
                    self._flush_focus()
                    self._focus_app = current
                    self._focus_since = time.time()
            except Exception:
                pass

    def open_app(self, app_name: str):
        """Launch an application by name."""
        try:
            os.startfile(app_name)
        except Exception:
            try:
                subprocess.Popen(["start", "", app_name], shell=True)
            except Exception as e:
                print(f"[Locus] Failed to open {app_name}: {e}")
