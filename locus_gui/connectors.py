"""Connectors pane — Notion + iCal feed management."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF, IconWidget, LineEdit,
    PasswordLineEdit, PrimaryPushButton, PushButton, StrongBodyLabel, SwitchButton,
    TransparentToolButton,
)

from .config import ConfigStore, ICalFeed
from .theme import ACCENT, BORDER, CARD, INK, INK_MUTED, SURFACE, mono, serif
from .widgets import Card, FieldLabel, Header, SaveRow


def _scrollable(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setStyleSheet(f"QScrollArea {{ background: {SURFACE}; border: none; }}")
    sa.setWidget(inner)
    return sa


def _content_host():
    host = QWidget()
    host.setStyleSheet(f"background: {SURFACE};")
    v = QVBoxLayout(host)
    v.setContentsMargins(40, 36, 40, 40)
    v.setSpacing(22)
    v.setAlignment(Qt.AlignTop)
    return host, v


def extract_notion_id(raw: str) -> str | None:
    """Pull a 32-char hex Notion ID from a URL or raw paste."""
    s = raw.replace("-", "")
    m = re.search(r"[0-9a-fA-F]{32}", s)
    return m.group(0).lower() if m else None


# ── Notion page ───────────────────────────────────────────────────────────────

class NotionPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()
        self.config.changed.connect(self._sync_from_config)

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("Notion", "Connect your Notion planner to auto-populate focus sessions."))

        # Enable card
        enable = Card()
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(StrongBodyLabel("Enable Notion"))
        cap = CaptionLabel("When off, Locus works entirely from custom tasks.")
        cap.setStyleSheet(f"color: {INK_MUTED};")
        cap.setWordWrap(True)
        col.addWidget(cap)
        row.addLayout(col, 1)
        self.enable_switch = SwitchButton()
        self.enable_switch.setChecked(self.config.notion_enabled)
        self.enable_switch.checkedChanged.connect(lambda val: setattr(self.config, "notion_enabled", val))
        row.addWidget(self.enable_switch)
        enable.add_layout(row)
        v.addWidget(enable)

        # API key card (Windows uses paste-key flow; OAuth lives on macOS)
        key_card = Card()
        key_card.add(FieldLabel("Account"))
        cap2 = CaptionLabel(
            "Paste an internal-integration token from notion.so/profile/integrations. "
            "Share your planner database with the integration to grant access."
        )
        cap2.setWordWrap(True)
        cap2.setStyleSheet(f"color: {INK_MUTED};")
        key_card.add(cap2)
        self.key_input = PasswordLineEdit()
        self.key_input.setPlaceholderText("secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        self.key_input.setText(self.config.notion_api_key)
        self.key_input.textChanged.connect(lambda t: setattr(self.config, "notion_api_key", t))
        key_card.add(self.key_input)

        status_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {INK_MUTED};")
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        disconnect_btn = PushButton("Disconnect")
        disconnect_btn.clicked.connect(self._disconnect)
        status_row.addWidget(disconnect_btn)
        key_card.add_layout(status_row)
        v.addWidget(key_card)

        # Database
        db_card = Card()
        db_card.add(FieldLabel("Planner Database"))
        cap3 = CaptionLabel(
            "Open the database in Notion, copy the URL, and paste it here. "
            "Locus extracts the 32-character database ID automatically."
        )
        cap3.setWordWrap(True)
        cap3.setStyleSheet(f"color: {INK_MUTED};")
        db_card.add(cap3)

        db_row = QHBoxLayout()
        self.db_input = LineEdit()
        self.db_input.setPlaceholderText("paste database URL or ID")
        self.db_input.setText(self.config.notion_database_id)
        db_row.addWidget(self.db_input, 1)
        use_btn = PushButton("Use")
        use_btn.clicked.connect(self._apply_db)
        db_row.addWidget(use_btn)
        db_card.add_layout(db_row)

        self.db_status = QLabel()
        self.db_status.setFont(mono(9))
        self.db_status.setStyleSheet(f"color: {INK_MUTED};")
        db_card.add(self.db_status)
        v.addWidget(db_card)

        # Save row
        save = SaveRow(self._save, self.config.load)
        v.addWidget(save)
        v.addStretch(1)

        self._sync_from_config()

    def _sync_from_config(self):
        self.enable_switch.setChecked(self.config.notion_enabled)
        if self.config.notion_api_key:
            self.status_label.setText("✓ Token saved")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-weight: 600;")
        else:
            self.status_label.setText("Not connected")
            self.status_label.setStyleSheet(f"color: {INK_MUTED};")
        if self.config.notion_database_id:
            self.db_status.setText(self.config.notion_database_id)
        else:
            self.db_status.setText("No database selected.")

    def _apply_db(self):
        nid = extract_notion_id(self.db_input.text().strip())
        if nid:
            self.config.notion_database_id = nid
            self.db_input.setText(nid)
            self._sync_from_config()

    def _disconnect(self):
        self.config.notion_api_key = ""
        self.config.notion_enabled = False
        self.config.notion_database_id = ""
        self.key_input.setText("")
        self.db_input.setText("")
        self.config.save()
        self.config.notify_notion_changed()
        self._sync_from_config()

    def _save(self):
        # Final sweep — apply pending DB input value if user typed but didn't click Use
        nid = extract_notion_id(self.db_input.text().strip())
        if nid:
            self.config.notion_database_id = nid
        self.config.save()
        self.config.notify_notion_changed()


# ── iCal page ─────────────────────────────────────────────────────────────────

class ICalPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header(
            "Calendar (iCal)",
            "Subscribe to any iCal feed — Google, Apple, Outlook, school calendars.",
        ))

        # Help card
        help_card = Card()
        help_card.add(FieldLabel("Where to find your URL"))
        body = CaptionLabel(
            "• Google Calendar → Settings → your calendar → Integrate calendar → "
            "“Secret address in iCal format.”\n"
            "• Apple iCloud → calendar.icloud.com → click your calendar → Public Calendar → copy URL.\n"
            "• Outlook → Settings → Calendar → Shared calendars → Publish a calendar → ICS link."
        )
        body.setStyleSheet(f"color: {INK_MUTED};")
        body.setWordWrap(True)
        help_card.add(body)
        v.addWidget(help_card)

        # Subscribed feeds
        self.feeds_card = Card()
        self.feeds_card.add(FieldLabel("Subscribed feeds"))
        self.feeds_host = QWidget()
        self.feeds_layout = QVBoxLayout(self.feeds_host)
        self.feeds_layout.setContentsMargins(0, 0, 0, 0)
        self.feeds_layout.setSpacing(6)
        self.feeds_card.add(self.feeds_host)
        v.addWidget(self.feeds_card)

        # Add a feed
        add = Card()
        add.add(FieldLabel("Add a feed"))
        self.name_input = LineEdit()
        self.name_input.setPlaceholderText("Nickname (e.g. School)")
        add.add(self.name_input)
        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("https://… or webcal://… URL")
        add.add(self.url_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        add_btn = PrimaryPushButton(FIF.ADD, "  Add Feed")
        add_btn.clicked.connect(self._add_feed)
        btn_row.addWidget(add_btn)
        add.add_layout(btn_row)
        v.addWidget(add)

        v.addStretch(1)
        self._refresh_feeds()

    def _refresh_feeds(self):
        # clear
        while self.feeds_layout.count():
            it = self.feeds_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        if not self.config.ical_feeds:
            empty = CaptionLabel("No feeds yet. Add one below.")
            empty.setStyleSheet(f"color: {INK_MUTED};")
            self.feeds_layout.addWidget(empty)
            return

        for feed in self.config.ical_feeds:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(2, 4, 2, 4)
            h.setSpacing(10)

            icon = IconWidget(FIF.CALENDAR)
            icon.setFixedSize(16, 16)
            h.addWidget(icon)

            col = QVBoxLayout()
            col.setSpacing(2)
            t = StrongBodyLabel(feed.name or "Untitled feed")
            col.addWidget(t)
            u = QLabel(feed.url)
            u.setFont(mono(9))
            u.setStyleSheet(f"color: {INK_MUTED};")
            col.addWidget(u)
            h.addLayout(col, 1)

            del_btn = TransparentToolButton(FIF.DELETE)
            del_btn.setFixedSize(24, 24)
            del_btn.clicked.connect(lambda _=False, fid=feed.id: self._remove_feed(fid))
            h.addWidget(del_btn)
            self.feeds_layout.addWidget(row)

    def _add_feed(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.config.ical_feeds.append(ICalFeed(name=self.name_input.text().strip(), url=url))
        self.config.save()
        self.config.notify_ical_changed()
        self.name_input.clear()
        self.url_input.clear()
        self._refresh_feeds()

    def _remove_feed(self, fid: str):
        self.config.ical_feeds = [f for f in self.config.ical_feeds if f.id != fid]
        self.config.save()
        self.config.notify_ical_changed()
        self._refresh_feeds()


# ── Top-level Connectors interface ────────────────────────────────────────────

class ConnectorsInterface(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.setObjectName("connectorsInterface")
        self.config = config
        self._build()

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # Sub-sidebar
        side = QFrame()
        side.setFixedWidth(240)
        side.setStyleSheet(f"background: {SURFACE}; border-right: 1px solid {BORDER};")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 22, 14, 14)
        sv.setSpacing(4)

        title = QLabel("Connectors")
        title.setFont(serif(26))
        title.setStyleSheet(f"color: {INK}; padding-bottom: 8px;")
        sv.addWidget(title)

        self._rows = []
        items = [
            ("notion", "Notion",         "Pull assignments from your planner.",      FIF.DOCUMENT),
            ("ical",   "Calendar (iCal)", "Subscribe to any iCal feed.",              FIF.CALENDAR),
        ]
        for cid, name, sub, icon in items:
            row = _ConnectorRow(name, sub, icon, on_state=lambda c=cid: self._is_enabled(c))
            row.clicked.connect(lambda _=False, c=cid: self._select(c))
            self._rows.append((cid, row))
            sv.addWidget(row)
        sv.addStretch(1)
        h.addWidget(side)

        self.stack = QStackedWidget()
        self.notion_page = NotionPage(self.config)
        self.ical_page = ICalPage(self.config)
        self.stack.addWidget(self.notion_page)
        self.stack.addWidget(self.ical_page)
        h.addWidget(self.stack, 1)

        self.config.changed.connect(self._refresh_indicators)
        self._select("notion")

    def _is_enabled(self, cid: str) -> bool:
        if cid == "notion":
            return self.config.notion_enabled and bool(self.config.notion_api_key)
        if cid == "ical":
            return bool(self.config.ical_feeds)
        return False

    def _select(self, cid: str):
        idx = {"notion": 0, "ical": 1}.get(cid, 0)
        self.stack.setCurrentIndex(idx)
        for c, r in self._rows:
            r.set_selected(c == cid)
        self._refresh_indicators()

    def _refresh_indicators(self):
        for cid, row in self._rows:
            row.set_enabled(self._is_enabled(cid))


class _ConnectorRow(QWidget):
    clicked = Signal(bool)

    def __init__(self, name: str, sub: str, icon, on_state, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(56)
        self._on_state = on_state
        self._selected = False
        self._enabled = False
        self._name = name
        self._sub = sub
        self._icon = icon
        self._build()

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        self._iw = IconWidget(self._icon)
        self._iw.setFixedSize(16, 16)
        h.addWidget(self._iw)

        col = QVBoxLayout()
        col.setSpacing(1)
        self._name_label = QLabel(self._name)
        self._name_label.setStyleSheet(f"color: {INK};")
        col.addWidget(self._name_label)
        self._sub_label = QLabel("Not connected")
        self._sub_label.setStyleSheet(f"color: {INK_MUTED}; font-size: 11px;")
        col.addWidget(self._sub_label)
        h.addLayout(col, 1)

        self._dot = QFrame()
        self._dot.setFixedSize(8, 8)
        h.addWidget(self._dot, 0, Qt.AlignVCenter)

        self._refresh()

    def set_selected(self, sel: bool):
        if self._selected != sel:
            self._selected = sel
            self._refresh()

    def set_enabled(self, on: bool):
        if self._enabled != on:
            self._enabled = on
            self._refresh()

    def _refresh(self):
        if self._selected:
            self.setStyleSheet("background: #FDF3E0; border-radius: 8px;")
            self._name_label.setStyleSheet(f"color: {INK}; font-weight: 600;")
        else:
            self.setStyleSheet("background: transparent;")
            self._name_label.setStyleSheet(f"color: {INK};")

        if self._enabled:
            self._sub_label.setText("Connected")
            self._sub_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: 600;")
            self._dot.setStyleSheet("background: #2EA66B; border-radius: 4px;")
        else:
            self._sub_label.setText("Not connected")
            self._sub_label.setStyleSheet(f"color: {INK_MUTED}; font-size: 11px;")
            self._dot.setStyleSheet("background: #B5AA98; border-radius: 4px;")

    def mousePressEvent(self, e):
        self.clicked.emit(True)
        super().mousePressEvent(e)
