"""Theme tokens + font helpers shared by every pane."""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont, QFontDatabase

ACCENT       = "#E8A020"
ACCENT_HOVER = "#F0AC2F"
ACCENT_PRESS = "#C98D1B"
ACCENT_MUTED = "#FDF3E0"
SURFACE      = "#FDFAF5"
CARD         = "#F7F2E8"
BORDER       = "#E8DFC8"
INK          = "#1A1410"
INK_MUTED    = "#7A6F60"
DANGER       = "#D6453A"

SERIF_FAMILY = "Instrument Serif"
MONO_FAMILY  = "DM Mono"


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
