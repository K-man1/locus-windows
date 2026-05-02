"""Theme tokens + font helpers shared by every pane."""

from __future__ import annotations

import os
import sys
from typing import Callable

from PySide6.QtGui import QFont, QFontDatabase

# ── Light-mode palette ────────────────────────────────────────────────────────

ACCENT       = "#E8A020"
ACCENT_HOVER = "#F0AC2F"
ACCENT_PRESS = "#C98D1B"
ACCENT_MUTED = "#FDF3E0"
DANGER       = "#D6453A"

# Light
SURFACE_L = "#FDFAF5"
CARD_L    = "#F7F2E8"
BORDER_L  = "#E8DFC8"
INK_L     = "#1A1410"
INK_MUTED_L = "#7A6F60"

# Dark
SURFACE_D = "#1E1E1E"
CARD_D    = "#2A2A2A"
BORDER_D  = "#404040"
INK_D     = "#F0EBE0"
INK_MUTED_D = "#9A9080"

# Current values — updated by set_dark()
SURFACE   = SURFACE_L
CARD      = CARD_L
BORDER    = BORDER_L
INK       = INK_L
INK_MUTED = INK_MUTED_L

SERIF_FAMILY = "Instrument Serif"
MONO_FAMILY  = "DM Mono"

# ── Dark-mode registry ────────────────────────────────────────────────────────

_dark: bool = False
_callbacks: list[Callable[[bool], None]] = []


def is_dark() -> bool:
    return _dark


def register_for_theme(callback: Callable[[bool], None]) -> None:
    """Register a callable that is invoked whenever the theme changes."""
    _callbacks.append(callback)


def set_dark(dark: bool) -> None:
    """Switch the global dark flag and notify all registered callbacks."""
    global _dark, SURFACE, CARD, BORDER, INK, INK_MUTED
    _dark = dark
    if dark:
        SURFACE, CARD, BORDER, INK, INK_MUTED = SURFACE_D, CARD_D, BORDER_D, INK_D, INK_MUTED_D
    else:
        SURFACE, CARD, BORDER, INK, INK_MUTED = SURFACE_L, CARD_L, BORDER_L, INK_L, INK_MUTED_L
    for cb in list(_callbacks):
        try:
            cb(dark)
        except Exception:
            pass


def apply_appearance(appearance: str) -> None:
    """Apply a theme setting value ('system', 'light', 'dark') immediately."""
    import sys
    import subprocess
    from qfluentwidgets import setTheme, Theme  # imported lazily — needs QApplication

    if appearance == "dark":
        setTheme(Theme.DARK)
        set_dark(True)
    elif appearance == "light":
        setTheme(Theme.LIGHT)
        set_dark(False)
    else:
        setTheme(Theme.AUTO)
        dark = False
        if sys.platform == "darwin":
            try:
                r = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True, text=True, timeout=2,
                )
                dark = r.stdout.strip().lower() == "dark"
            except Exception:
                pass
        elif sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                dark = val == 0
            except Exception:
                pass
        set_dark(dark)


# ── Resources ─────────────────────────────────────────────────────────────────

def resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_fonts():
    fonts_dir = os.path.join(resource_dir(), "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for name in os.listdir(fonts_dir):
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))


def serif(size: int) -> QFont:
    f = QFont(SERIF_FAMILY, size)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def mono(size: int, medium: bool = False) -> QFont:
    f = QFont(MONO_FAMILY, size)
    if medium:
        f.setWeight(QFont.Medium)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f
