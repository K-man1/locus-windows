"""Connectors pane — Notion + iCal feed management."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF, IconWidget, LineEdit,
    PrimaryPushButton, PushButton, StrongBodyLabel, SwitchButton,
    TransparentToolButton,
)

from .config import ConfigStore, ICalFeed
from .theme import (
    ACCENT, BORDER, CARD, INK, INK_MUTED, SURFACE, mono, serif,
    is_dark, register_for_theme,
    CARD_D, BORDER_D, INK_D, INK_L, INK_MUTED_D, INK_MUTED_L,
    SURFACE_D, SURFACE_L,
)
from .widgets import Card, FieldLabel, Header, SaveRow

NOTION_OAUTH_URL = (
    "https://www.notion.so/install-integration"
    "?response_type=code"
    "&client_id=34ad872b-594c-81a3-be0a-00376b27f521"
    "&redirect_uri=https%3A%2F%2Flocus-proxy.locus-proxy.workers.dev%2Foauth%2Fnotion"
    "&owner=user"
)


def _scrollable(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    sa.setWidget(inner)
    return sa


def _content_host():
    host = QWidget()
    host.setObjectName("contentHost")
    v = QVBoxLayout(host)
    v.setContentsMargins(40, 36, 40, 40)
    v.setSpacing(22)
    v.setAlignment(Qt.AlignTop)
    return host, v


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
        cap.setWordWrap(True)
        col.addWidget(cap)
        row.addLayout(col, 1)
        self.enable_switch = SwitchButton()
        self.enable_switch.setChecked(self.config.notion_enabled)
        self.enable_switch.checkedChanged.connect(lambda val: setattr(self.config, "notion_enabled", val))
        row.addWidget(self.enable_switch)
        enable.add_layout(row)
        v.addWidget(enable)

        # Account card — OAuth button
        acct_card = Card()
        acct_card.add(FieldLabel("Account"))

        sign_in_btn = PrimaryPushButton(FIF.LINK, "  Sign in with Notion")
        sign_in_btn.setMinimumHeight(40)
        sign_in_btn.setMinimumWidth(200)
        sign_in_btn.setStyleSheet(
            f"PrimaryPushButton {{ background: {ACCENT}; border-radius: 8px; "
            f"color: white; font-weight: 600; font-size: 13px; }}"
            f"PrimaryPushButton:hover {{ background: #F0AC2F; }}"
            f"PrimaryPushButton:pressed {{ background: #C98D1B; }}"
        )
        sign_in_btn.clicked.connect(self._open_oauth)
        acct_card.add(sign_in_btn)

        hint = CaptionLabel("Opens Notion in your browser. After authorizing, you'll bounce back to Locus.")
        hint.setWordWrap(True)
        acct_card.add(hint)

        status_row = QHBoxLayout()
        self.status_label = QLabel()
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        disconnect_btn = PushButton("Disconnect")
        disconnect_btn.clicked.connect(self._disconnect)
        status_row.addWidget(disconnect_btn)
        acct_card.add_layout(status_row)
        v.addWidget(acct_card)

        # Database card
        db_card = Card()
        db_card.add(FieldLabel("Planner Database"))
        cap3 = CaptionLabel(
            "Open the database in Notion, copy the URL, and paste it here. "
            "Locus extracts the 32-character database ID automatically."
        )
        cap3.setWordWrap(True)
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

        save = SaveRow(self._save, self.config.load)
        v.addWidget(save)
        v.addStretch(1)

        self._sync_from_config()

    def _open_oauth(self):
        webbrowser.open(NOTION_OAUTH_URL)

    def _sync_from_config(self):
        self.enable_switch.setChecked(self.config.notion_enabled)
        if self.config.notion_api_key:
            self.status_label.setText("✓ Connected")
            self.status_label.setStyleSheet(f"color: #2EA66B; font-weight: 600;")
        else:
            self.status_label.setText("Not connected")
            self.status_label.setStyleSheet(f"color: {INK_MUTED};")
        if self.config.notion_database_id:
            self.db_status.setText(self.config.notion_database_id)
        else:
            self.db_status.setText("No database selected.")

    def _apply_db(self):
        import re
        raw = self.db_input.text().strip()
        s = raw.replace("-", "")
        m = re.search(r"[0-9a-fA-F]{32}", s)
        nid = m.group(0).lower() if m else None
        if nid:
            self.config.notion_database_id = nid
            self.db_input.setText(nid)
            self._sync_from_config()

    def _disconnect(self):
        self.config.notion_api_key = ""
        self.config.notion_enabled = False
        self.config.notion_database_id = ""
        self.db_input.setText("")
        self.config.save()
        self.config.notify_notion_changed()
        self._sync_from_config()

    def _save(self):
        import re
        raw = self.db_input.text().strip()
        s = raw.replace("-", "")
        m = re.search(r"[0-9a-fA-F]{32}", s)
        nid = m.group(0).lower() if m else None
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

        help_card = Card()
        help_card.add(FieldLabel("Where to find your URL"))
        body = CaptionLabel(
            "• Google Calendar → Settings → your calendar → Integrate calendar → "
            "“Secret address in iCal format.”\n"
            "• Apple iCloud → calendar.icloud.com → click your calendar → Public Calendar → copy URL.\n"
            "• Outlook → Settings → Calendar → Shared calendars → Publish a calendar → ICS link."
        )
        body.setWordWrap(True)
        help_card.add(body)
        v.addWidget(help_card)

        self.feeds_card = Card()
        self.feeds_card.add(FieldLabel("Subscribed feeds"))
        self.feeds_host = QWidget()
        self.feeds_layout = QVBoxLayout(self.feeds_host)
        self.feeds_layout.setContentsMargins(0, 0, 0, 0)
        self.feeds_layout.setSpacing(6)
        self.feeds_card.add(self.feeds_host)
        v.addWidget(self.feeds_card)

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
        while self.feeds_layout.count():
            it = self.feeds_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        if not self.config.ical_feeds:
            empty = CaptionLabel("No feeds yet. Add one below.")
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

        self._side = QFrame()
        self._side.setObjectName("connectorsSide")
        self._side.setFixedWidth(240)
        sv = QVBoxLayout(self._side)
        sv.setContentsMargins(14, 22, 14, 14)
        sv.setSpacing(4)

        self._title_label = QLabel("Connectors")
        self._title_label.setFont(serif(26))
        sv.addWidget(self._title_label)

        self._rows = []
        items = [
            ("notion", "Notion",          "Pull assignments from your planner.", FIF.DOCUMENT),
            ("ical",   "Calendar (iCal)", "Subscribe to any iCal feed.",         FIF.CALENDAR),
        ]
        for cid, name, sub, icon in items:
            row = _ConnectorRow(name, sub, icon, on_state=lambda c=cid: self._is_enabled(c))
            row.clicked.connect(lambda _=False, c=cid: self._select(c))
            self._rows.append((cid, row))
            sv.addWidget(row)
        sv.addStretch(1)
        h.addWidget(self._side)

        self.stack = QStackedWidget()
        self.notion_page = NotionPage(self.config)
        self.ical_page = ICalPage(self.config)
        self.stack.addWidget(self.notion_page)
        self.stack.addWidget(self.ical_page)
        h.addWidget(self.stack, 1)

        self.config.changed.connect(self._refresh_indicators)
        self._apply_side_theme(is_dark())
        register_for_theme(self._apply_side_theme)
        self._select("notion")

    def _apply_side_theme(self, dark: bool):
        ink = INK_D if dark else INK_L
        border = BORDER_D if dark else BORDER
        self._side.setStyleSheet(
            f"#connectorsSide {{ border-right: 1px solid {border}; }}"
        )
        self._title_label.setStyleSheet(f"color: {ink}; padding-bottom: 8px;")

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
        register_for_theme(lambda _: self._refresh())

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
        col.addWidget(self._name_label)
        self._sub_label = QLabel("Not connected")
        self._sub_label.setStyleSheet("font-size: 11px;")
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
        dark = is_dark()
        ink = INK_D if dark else INK_L
        sel_bg = "#3A3020" if dark else "#FDF3E0"

        if self._selected:
            self.setStyleSheet(f"background: {sel_bg}; border-radius: 8px;")
            self._name_label.setStyleSheet(f"color: {ink}; font-weight: 600;")
        else:
            self.setStyleSheet("background: transparent;")
            self._name_label.setStyleSheet(f"color: {ink};")

        if self._enabled:
            self._sub_label.setText("Connected")
            self._sub_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: 600;")
            self._dot.setStyleSheet("background: #2EA66B; border-radius: 4px;")
        else:
            muted = INK_MUTED_D if dark else INK_MUTED_L
            self._sub_label.setText("Not connected")
            self._sub_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
            self._dot.setStyleSheet("background: #B5AA98; border-radius: 4px;")

    def mousePressEvent(self, e):
        self.clicked.emit(True)
        super().mousePressEvent(e)
