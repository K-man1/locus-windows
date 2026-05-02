"""Reusable Locus widgets — Card, Header, FieldLabel, SaveRow, list editor."""

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF, IconWidget,
    LineEdit, PrimaryPushButton, PushButton, StrongBodyLabel, SubtitleLabel,
    TitleLabel, TransparentToolButton,
)

from .theme import (
    ACCENT, ACCENT_MUTED, BORDER, CARD, INK, INK_MUTED, SURFACE, mono, serif,
)


class Header(QWidget):
    """Big serif title + muted caption used at the top of every pane."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        t = QLabel(title)
        t.setFont(serif(36))
        t.setStyleSheet(f"color: {INK};")
        v.addWidget(t)

        s = BodyLabel(subtitle)
        s.setStyleSheet(f"color: {INK_MUTED};")
        v.addWidget(s)


class FieldLabel(QLabel):
    """Mono uppercase field caption like 'APPEARANCE' / 'WHAT ARE YOU WORKING ON?'."""

    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        f = mono(9, medium=True)
        self.setFont(f)
        self.setStyleSheet(f"color: {INK_MUTED}; letter-spacing: 1.5px;")


class Card(QFrame):
    """Locus-styled card — cream fill, subtle border, generous interior padding.

    Plain QFrame (not qfluentwidgets.CardWidget) to avoid layout-install
    conflicts that caused infinite recursion when the framework's internal
    layout collided with one installed here.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("locusCard")
        self.setStyleSheet(
            f"#locusCard {{ background: {CARD}; border: 1px solid {BORDER}; "
            f"border-radius: 12px; }}"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(12)

    def add(self, widget: QWidget):
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self._layout.addLayout(layout)
        return layout

    def add_row(self, *widgets: QWidget, spacing: int = 10):
        h = QHBoxLayout()
        h.setSpacing(spacing)
        for w in widgets:
            h.addWidget(w)
        self._layout.addLayout(h)
        return h

    def add_spacing(self, px: int):
        self._layout.addSpacing(px)


class ResetButton(TransparentToolButton):
    """Tiny circular-arrow reset button that lives on the right of a field row."""

    def __init__(self, on_reset: Callable[[], None], parent=None):
        super().__init__(FIF.SYNC, parent)
        self.setToolTip("Reset to default")
        self.setFixedSize(24, 24)
        self.clicked.connect(on_reset)


class SaveRow(QWidget):
    """Save Changes / Reload row used at the bottom of every settings page."""

    saved = Signal()

    def __init__(self, on_save: Callable[[], None], on_reload: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._on_reload = on_reload
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 0)
        h.setSpacing(12)

        save_btn = PrimaryPushButton("Save Changes")
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._handle_save)
        h.addWidget(save_btn)

        if on_reload is not None:
            reload_btn = PushButton("Reload from Disk")
            reload_btn.setMinimumHeight(36)
            reload_btn.clicked.connect(on_reload)
            h.addWidget(reload_btn)

        self._saved_label = QLabel("✓ Saved")
        self._saved_label.setStyleSheet(f"color: {ACCENT}; font-weight: 600;")
        self._saved_label.hide()
        h.addWidget(self._saved_label)
        h.addStretch(1)

    def _handle_save(self):
        self._on_save()
        self._saved_label.show()
        QTimer.singleShot(2200, self._saved_label.hide)
        self.saved.emit()


class ListEditor(QWidget):
    """Editable list of strings — chip rows + add input + plus button."""

    changed = Signal()

    def __init__(self, items: List[str], placeholder: str, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.placeholder = placeholder
        self._build()

    def set_items(self, items: List[str]):
        self.items = list(items)
        self._refresh()

    def _build(self):
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(6)

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._v.addWidget(self._rows_host)

        # Add row
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._input = LineEdit()
        self._input.setPlaceholderText(self.placeholder)
        self._input.returnPressed.connect(self._add)
        add_row.addWidget(self._input, 1)

        plus = TransparentToolButton(FIF.ADD)
        plus.setFixedSize(32, 32)
        plus.clicked.connect(self._add)
        add_row.addWidget(plus)
        self._v.addLayout(add_row)

        self._refresh()

    def _refresh(self):
        # Clear existing rows
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not self.items:
            empty = CaptionLabel("No entries yet.")
            empty.setStyleSheet(f"color: {INK_MUTED}; padding: 4px 0;")
            self._rows_layout.addWidget(empty)
            return

        for i, item in enumerate(self.items):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(2, 6, 2, 6)
            h.setSpacing(8)
            label = QLabel(item)
            label.setFont(mono(10))
            label.setStyleSheet(f"color: {INK};")
            h.addWidget(label, 1)
            rm = TransparentToolButton(FIF.REMOVE)
            rm.setFixedSize(22, 22)
            rm.clicked.connect(lambda _=False, idx=i: self._remove(idx))
            h.addWidget(rm)
            self._rows_layout.addWidget(row)
            if i < len(self.items) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px;")
                self._rows_layout.addWidget(line)

    def _add(self):
        v = self._input.text().strip()
        if not v or v in self.items:
            return
        self.items.append(v)
        self._input.clear()
        self._refresh()
        self.changed.emit()

    def _remove(self, idx: int):
        if 0 <= idx < len(self.items):
            del self.items[idx]
            self._refresh()
            self.changed.emit()
