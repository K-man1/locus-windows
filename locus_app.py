"""Locus — Windows desktop GUI entry point."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from qfluentwidgets import (
    FluentIcon as FIF, FluentWindow, NavigationItemPosition, Theme, setTheme, setThemeColor,
)

from focuslock.paths import APP_DATA_DIR

from locus_gui.analytics import AnalyticsInterface
from locus_gui.config import ConfigStore
from locus_gui.connectors import ConnectorsInterface
from locus_gui.prompt_handler import PromptHandler
from locus_gui.settings import SettingsInterface
from locus_gui.start import StartInterface
from locus_gui.theme import ACCENT, load_fonts, resource_dir, apply_appearance


# ── Daemon launch ─────────────────────────────────────────────────────────────

_daemon_proc: subprocess.Popen | None = None


def _quit_old_locus_app():
    """On macOS, quit the installed Swift Locus app so it doesn't intercept prompts."""
    if sys.platform != "darwin":
        return
    try:
        result = subprocess.run(
            ["pgrep", "-x", "FocusLockApp"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(
                ["osascript", "-e", 'tell application "Locus" to quit'],
                capture_output=True, timeout=3,
            )
    except Exception as e:
        print(f"[locus] could not quit old Locus app: {e}")


def _daemon_already_running() -> bool:
    """Return True if a live locusd process owns the lock file."""
    from focuslock.paths import LOCK_PATH
    try:
        import psutil
        with open(LOCK_PATH) as f:
            pid = int(f.read().strip())
        return psutil.pid_exists(pid)
    except Exception:
        return False


_BROWSER_CANDIDATES = [
    # Chrome — user install, machine install, 32-bit machine install
    (r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",       "Chrome"),
    (r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",       "Chrome"),
    (r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",  "Chrome"),
    # Edge
    (r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",      "Edge"),
    (r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",      "Edge"),
    (r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe", "Edge"),
    # Brave
    (r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe", "Brave"),
    # Vivaldi
    (r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",            "Vivaldi"),
]


def _find_browser_exe() -> tuple[str, str] | None:
    """Return (path, name) for the first Chromium browser found, or None."""
    import shutil
    for template, name in _BROWSER_CANDIDATES:
        path = os.path.expandvars(template)
        if os.path.exists(path):
            return path, name
    # Fallback: try PATH
    for exe, name in [("chrome", "Chrome"), ("msedge", "Edge"), ("brave", "Brave")]:
        found = shutil.which(exe)
        if found:
            return found, name
    return None


def _launch_browser_with_debug_port():
    """Launch a Chromium browser with --remote-debugging-port=9222 if not already open."""
    import requests
    try:
        requests.get("http://localhost:9222/json", timeout=1)
        print("[locus] browser already listening on port 9222")
        return
    except Exception:
        pass

    result = _find_browser_exe()
    if result is None:
        print("[locus] no supported browser found — website blocking disabled")
        return

    path, name = result

    # Check if the browser process is already running (without debug port).
    # On Windows, Chrome/Edge are single-instance — launching a second copy
    # just opens a tab in the existing process, which won't have the debug port.
    import psutil
    exe_name = os.path.basename(path).lower()
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == exe_name:
                print(
                    f"[locus] {name} is already running without --remote-debugging-port. "
                    "Close it and restart Locus for website blocking to work."
                )
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"[locus] launching {name} with debug port 9222")
    subprocess.Popen(
        [path, "--remote-debugging-port=9222", "--remote-allow-origins=*"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# ── Chrome launcher setup ─────────────────────────────────────────────────────

_CHROME_VBS_NAME = "chrome_locus.vbs"
_CHROME_SETUP_MARKER = "chrome_launcher_setup.done"

_CHROME_VBS_TEMPLATE = (
    "' Locus Chrome launcher \x97 always opens Chrome with remote debugging enabled.\r\n"
    "Dim fso, chromePath, i, arg, args, WshShell\r\n"
    "Set fso = CreateObject(\"Scripting.FileSystemObject\")\r\n"
    "Set WshShell = CreateObject(\"WScript.Shell\")\r\n"
    "\r\n"
    "Dim candidates(2)\r\n"
    "candidates(0) = WshShell.ExpandEnvironmentStrings(\"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe\")\r\n"
    "candidates(1) = WshShell.ExpandEnvironmentStrings(\"%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe\")\r\n"
    "candidates(2) = WshShell.ExpandEnvironmentStrings(\"%PROGRAMFILES(X86)%\\Google\\Chrome\\Application\\chrome.exe\")\r\n"
    "\r\n"
    "chromePath = \"\"\r\n"
    "For i = 0 To 2\r\n"
    "    If fso.FileExists(candidates(i)) Then\r\n"
    "        chromePath = candidates(i)\r\n"
    "        Exit For\r\n"
    "    End If\r\n"
    "Next\r\n"
    "\r\n"
    "If chromePath = \"\" Then\r\n"
    "    MsgBox \"Google Chrome not found. Please install Chrome.\", vbExclamation, \"Locus\"\r\n"
    "    WScript.Quit 1\r\n"
    "End If\r\n"
    "\r\n"
    "args = \"\"\r\n"
    "For i = 0 To WScript.Arguments.Count - 1\r\n"
    "    arg = WScript.Arguments(i)\r\n"
    "    If InStr(arg, \" \") > 0 Then\r\n"
    "        args = args & \" \"\"\" & arg & \"\"\"\"\r\n"
    "    Else\r\n"
    "        args = args & \" \" & arg\r\n"
    "    End If\r\n"
    "Next\r\n"
    "\r\n"
    "WshShell.Run \"\"\"\" & chromePath & \"\"\" --remote-debugging-port=9222 --remote-allow-origins=*\" & args, 0, False\r\n"
)

_PATCH_PS1 = r"""
param([string]$VbsPath)
$wscript = "$env:SystemRoot\System32\wscript.exe"
$WshShell = New-Object -ComObject WScript.Shell
$searchPaths = @(
    "$env:USERPROFILE\Desktop",
    "$env:APPDATA\Microsoft\Windows\Start Menu",
    "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch",
    "C:\ProgramData\Microsoft\Windows\Start Menu"
)
$patched = 0
foreach ($base in $searchPaths) {
    if (-not (Test-Path $base)) { continue }
    Get-ChildItem -Path $base -Recurse -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $lnk = $WshShell.CreateShortcut($_.FullName)
            if ($lnk.TargetPath -ilike "*chrome.exe" -and $lnk.TargetPath -ine $wscript) {
                $orig = $lnk.Arguments
                $newArgs = "`"$VbsPath`""
                if ($orig) { $newArgs += " $orig" }
                $lnk.TargetPath = $wscript
                $lnk.Arguments = $newArgs
                $lnk.Save()
                $patched++
            }
        } catch {}
    }
}
Write-Output $patched
""".strip()


def chrome_launcher_setup_done() -> bool:
    marker = os.path.join(APP_DATA_DIR, _CHROME_SETUP_MARKER)
    return os.path.exists(marker)


def setup_chrome_launcher() -> tuple[bool, str]:
    """
    Write a VBScript Chrome wrapper and patch all Chrome shortcuts to use it.
    Returns (success, message).
    """
    if sys.platform != "win32":
        return False, "Chrome launcher setup is Windows-only."

    result = _find_browser_exe()
    if result is None or "chrome" not in result[1].lower():
        return False, "Google Chrome not found. Install Chrome first."

    vbs_path = os.path.join(APP_DATA_DIR, _CHROME_VBS_NAME)
    try:
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(_CHROME_VBS_TEMPLATE)
    except Exception as e:
        return False, f"Could not write launcher script: {e}"

    ps1_path = os.path.join(APP_DATA_DIR, "patch_chrome_shortcuts.ps1")
    try:
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write(_PATCH_PS1)
    except Exception as e:
        return False, f"Could not write patch script: {e}"

    try:
        proc = subprocess.run(
            [
                "powershell", "-ExecutionPolicy", "Bypass",
                "-File", ps1_path,
                "-VbsPath", vbs_path,
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        count = proc.stdout.strip() or "0"
    except Exception as e:
        return False, f"Shortcut patching failed: {e}"

    marker = os.path.join(APP_DATA_DIR, _CHROME_SETUP_MARKER)
    try:
        with open(marker, "w") as f:
            f.write("done")
    except Exception:
        pass

    return True, f"Done — patched {count} Chrome shortcut(s). Chrome will now always open with debugging enabled."


def start_daemon():
    global _daemon_proc
    if _daemon_already_running():
        print("[locus] daemon already running, skipping launch")
        return
    try:
        base = resource_dir()
        if getattr(sys, "frozen", False):
            cmd = [os.path.join(base, "locusd.exe")]
        else:
            cmd = [sys.executable, os.path.join(base, "locusd_entry.py")]
        _daemon_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[locus] failed to start daemon: {e}")


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(FluentWindow):
    def __init__(self, config: ConfigStore):
        super().__init__()
        self.config = config
        self.setWindowTitle("Locus")
        self.resize(1000, 680)

        self.start_iface      = StartInterface()
        self.settings_iface   = SettingsInterface(config)
        self.connectors_iface = ConnectorsInterface(config)
        self.analytics_iface  = AnalyticsInterface()

        self.addSubInterface(self.start_iface,      FIF.PLAY,    "Start")
        self.addSubInterface(self.settings_iface,   FIF.SETTING, "Settings")
        self.addSubInterface(self.connectors_iface, FIF.LINK,    "Connectors")
        self.addSubInterface(
            self.analytics_iface, FIF.PIE_SINGLE, "Analytics",
            position=NavigationItemPosition.SCROLL,
        )

        self.navigationInterface.setExpandWidth(220)

        # Blocking-dialog handler (replaces the Swift app's prompt handling)
        self._prompt_handler = PromptHandler(self)

        # Re-apply theme when config is saved (e.g. reload from disk)
        config.changed.connect(lambda: apply_appearance(config.appearance))


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Locus")
    app.setOrganizationName("Locus")

    load_fonts()

    # Suppress text-selection highlight across all labels
    app.setStyleSheet(
        "QLabel { selection-background-color: transparent; selection-color: inherit; }"
    )

    config = ConfigStore()

    # Apply initial theme before building the window so all widgets start correctly
    apply_appearance(config.appearance)
    setThemeColor(QColor(ACCENT))

    # Quit the old Swift Locus GUI so it doesn't intercept blocking dialogs
    _quit_old_locus_app()

    if sys.platform == "win32" and not chrome_launcher_setup_done():
        ok, msg = setup_chrome_launcher()
        print(f"[locus] chrome launcher setup: {msg}")

    _launch_browser_with_debug_port()
    start_daemon()

    win = MainWindow(config)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
