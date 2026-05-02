"""Analytics pane — KPIs + bar / list charts driven by analytics.json."""

from __future__ import annotations

import json
from typing import List, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from qfluentwidgets import BodyLabel, CaptionLabel, StrongBodyLabel

from focuslock.paths import ANALYTICS_PATH

from .theme import ACCENT, BORDER, CARD, DANGER, INK, INK_MUTED, SURFACE, mono, serif
from .widgets import Card, FieldLabel, Header


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_seconds(secs: int) -> str:
    if secs <= 0:
        return "0m"
    h = secs // 3600
    m = (secs % 3600) // 60
    if h == 0:
        return f"{m}m"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def _short_date(iso: str) -> str:
    try:
        y, mo, d = iso.split("-")
        return f"{int(mo)}/{int(d)}"
    except Exception:
        return iso


def _pairs(raw) -> List[Tuple[str, int]]:
    out = []
    for entry in raw or []:
        if isinstance(entry, list) and len(entry) >= 2:
            name = entry[0] if isinstance(entry[0], str) else str(entry[0])
            try:
                count = int(entry[1])
            except Exception:
                continue
            out.append((name, count))
    return out


# ── Custom drawn charts ───────────────────────────────────────────────────────

class BarChart(QWidget):
    """Vertical bar chart — daily focus minutes, hour-of-day etc."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: List[str] = []
        self._values: List[float] = []
        self._suffix = ""
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, labels: List[str], values: List[float], suffix: str = ""):
        self._labels = labels
        self._values = values
        self._suffix = suffix
        self.update()

    def paintEvent(self, _):
        if not self._values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        margin_l, margin_r = 36, 8
        margin_t, margin_b = 8, 22
        w = self.width() - margin_l - margin_r
        h = self.height() - margin_t - margin_b

        max_v = max(self._values) or 1
        # round up to nice number
        steps = [1, 2, 5, 10, 25, 50, 100, 150, 200, 300, 500, 1000]
        nice_max = next((s for s in steps if s >= max_v), max_v)
        # Y axis labels (3 ticks)
        p.setPen(QColor(BORDER))
        for i in range(4):
            y = margin_t + h - (h * i / 3)
            p.drawLine(margin_l, int(y), margin_l + w, int(y))
            val = nice_max * i / 3
            label = f"{int(val)}{self._suffix}"
            p.setPen(QColor(INK_MUTED))
            p.setFont(mono(8))
            p.drawText(2, int(y) + 4, label)
            p.setPen(QColor(BORDER))

        # Bars
        n = len(self._values)
        bar_w = max(2, (w / n) * 0.6)
        gap = (w / n) - bar_w
        for i, v in enumerate(self._values):
            x = margin_l + i * (bar_w + gap) + gap / 2
            bh = (v / nice_max) * h if nice_max > 0 else 0
            y = margin_t + h - bh
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(int(x), int(y), int(bar_w), int(bh), 3, 3)

        # X labels — show every 2nd
        p.setPen(QColor(INK_MUTED))
        p.setFont(mono(8))
        for i, lab in enumerate(self._labels):
            if i % max(1, n // 7) != 0:
                continue
            x = margin_l + i * (bar_w + gap) + bar_w / 2 + gap / 2
            p.drawText(int(x) - 14, self.height() - 4, lab)


class HorizontalBarList(QWidget):
    """Compact list of name + thin bar + value, used for top-apps/domains."""

    def __init__(self, color: str = ACCENT, parent=None):
        super().__init__(parent)
        self._rows: List[Tuple[str, float, str]] = []
        self._max = 1.0
        self._color = color
        self.setMinimumHeight(40)

    def set_rows(self, rows: List[Tuple[str, float, str]]):
        self._rows = rows
        self._max = max((r[1] for r in rows), default=1.0) or 1.0
        self.setMinimumHeight(36 * max(1, len(rows)))
        self.update()

    def paintEvent(self, _):
        if not self._rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        row_h = self.height() / max(1, len(self._rows))
        name_col = 150
        value_col = 70
        bar_x = name_col + 8
        bar_w_total = self.width() - bar_x - value_col - 4

        for i, (name, value, formatted) in enumerate(self._rows):
            y = i * row_h + row_h / 2

            p.setPen(QColor(INK))
            p.setFont(mono(9, medium=True))
            p.drawText(0, int(y + 4), name[:24])

            # bar bg
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(BORDER))
            p.drawRoundedRect(bar_x, int(y - 3), bar_w_total, 6, 3, 3)
            # bar fg
            frac = value / self._max if self._max else 0
            p.setBrush(QColor(self._color))
            p.drawRoundedRect(bar_x, int(y - 3), int(bar_w_total * frac), 6, 3, 3)

            # value
            p.setPen(QColor(INK_MUTED))
            p.setFont(mono(9))
            p.drawText(self.width() - value_col, int(y + 4), formatted)


# ── KPI card ──────────────────────────────────────────────────────────────────

class KPICard(Card):
    def __init__(self, label: str, value: str, sub: str, parent=None):
        super().__init__(parent)
        self.add(FieldLabel(label))
        v = QLabel(value)
        v.setFont(serif(28))
        v.setStyleSheet(f"color: {ACCENT};")
        self.add(v)
        s = CaptionLabel(sub)
        s.setStyleSheet(f"color: {INK_MUTED};")
        self.add(s)


# ── Pane ──────────────────────────────────────────────────────────────────────

class AnalyticsInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("analyticsInterface")
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._reload)
        self._timer.start()
        self._reload()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        host = QWidget()
        host.setStyleSheet(f"background: {SURFACE};")
        v = QVBoxLayout(host)
        v.setContentsMargins(40, 36, 40, 40)
        v.setSpacing(20)
        v.setAlignment(Qt.AlignTop)

        v.addWidget(Header("Analytics", "Your focus activity and blocking patterns."))

        # KPI row
        self.kpi_grid = QGridLayout()
        self.kpi_grid.setHorizontalSpacing(14)
        self.kpi_grid.setVerticalSpacing(14)
        self.kpi_today = KPICard("Focus Today", "0m", "today")
        self.kpi_sessions = KPICard("Sessions Today", "0", "today")
        self.kpi_streak = KPICard("Streak", "0d", "consecutive days")
        self.kpi_blocks = KPICard("Blocks Denied", "0", "all-time")
        for i, c in enumerate([self.kpi_today, self.kpi_sessions, self.kpi_streak, self.kpi_blocks]):
            self.kpi_grid.addWidget(c, 0, i)
        v.addLayout(self.kpi_grid)

        # Daily focus chart
        self.daily_card = Card()
        self.daily_card.add(FieldLabel("Daily Focus Time — Last 14 Days"))
        self.daily_chart = BarChart()
        self.daily_chart.setMinimumHeight(160)
        self.daily_card.add(self.daily_chart)
        self.daily_empty = CaptionLabel("No data recorded yet.")
        self.daily_empty.setStyleSheet(f"color: {INK_MUTED};")
        self.daily_card.add(self.daily_empty)
        v.addWidget(self.daily_card)

        # Top apps
        self.apps_card = Card()
        self.apps_card.add(FieldLabel("Top Apps by Screen Time (In-Session)"))
        self.apps_list = HorizontalBarList(color=ACCENT)
        self.apps_card.add(self.apps_list)
        self.apps_empty = CaptionLabel("No data recorded yet.")
        self.apps_empty.setStyleSheet(f"color: {INK_MUTED};")
        self.apps_card.add(self.apps_empty)
        v.addWidget(self.apps_card)

        # Top domains
        self.domains_card = Card()
        self.domains_card.add(FieldLabel("Top Domains Visited During Sessions"))
        self.domains_list = HorizontalBarList(color=ACCENT)
        self.domains_card.add(self.domains_list)
        self.domains_empty = CaptionLabel("No data recorded yet.")
        self.domains_empty.setStyleSheet(f"color: {INK_MUTED};")
        self.domains_card.add(self.domains_empty)
        v.addWidget(self.domains_card)

        # Impulse leaderboard
        self.impulse_card = Card()
        self.impulse_card.add(FieldLabel("Impulse Leaderboard — blocks you couldn't justify"))
        self.impulse_list = HorizontalBarList(color=DANGER)
        self.impulse_card.add(self.impulse_list)
        self.impulse_empty = CaptionLabel("No data recorded yet.")
        self.impulse_empty.setStyleSheet(f"color: {INK_MUTED};")
        self.impulse_card.add(self.impulse_empty)
        v.addWidget(self.impulse_card)

        # All-time totals
        self.totals_card = Card()
        self.totals_card.add(FieldLabel("All-Time Totals"))
        self.totals_row = QHBoxLayout()
        self.totals_row.setSpacing(28)
        self.totals_card.add_layout(self.totals_row)
        v.addWidget(self.totals_card)

        v.addStretch(1)

        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setStyleSheet(f"QScrollArea {{ background: {SURFACE}; border: none; }}")
        sa.setWidget(host)
        outer.addWidget(sa)

    def _reload(self):
        try:
            with open(ANALYTICS_PATH, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception:
            return
        self._apply(summary)

    def _apply(self, s: dict):
        # KPIs
        self.kpi_today._layout.itemAt(1).widget().setText(_format_seconds(int(s.get("focus_today", 0))))
        self.kpi_sessions._layout.itemAt(1).widget().setText(str(int(s.get("sessions_today", 0))))
        self.kpi_streak._layout.itemAt(1).widget().setText(f'{int(s.get("streak_days", 0))}d')
        denied = int(s.get("block_denied", 0)) + int(s.get("block_canceled", 0))
        self.kpi_blocks._layout.itemAt(1).widget().setText(str(denied))

        # Daily focus
        series = s.get("daily_focus_series") or {}
        keys = sorted(series.keys())
        values = [series[k] / 60.0 for k in keys]   # minutes
        if any(v > 0 for v in values):
            self.daily_chart.set_data([_short_date(k) for k in keys], values, "m")
            self.daily_empty.hide()
            self.daily_chart.show()
        else:
            self.daily_chart.hide()
            self.daily_empty.show()

        # Top apps
        rows = []
        for name, secs in _pairs(s.get("app_focus_all"))[:8]:
            rows.append((name, float(secs), _format_seconds(int(secs))))
        if rows:
            self.apps_list.set_rows(rows)
            self.apps_empty.hide()
            self.apps_list.show()
        else:
            self.apps_list.hide()
            self.apps_empty.show()

        # Top domains
        rows = []
        for name, count in _pairs(s.get("domain_visits"))[:8]:
            rows.append((name, float(count), str(count)))
        if rows:
            self.domains_list.set_rows(rows)
            self.domains_empty.hide()
            self.domains_list.show()
        else:
            self.domains_list.hide()
            self.domains_empty.show()

        # Impulse
        rows = []
        for name, count in _pairs(s.get("impulse_blocks"))[:8]:
            rows.append((name, float(count), str(count)))
        if rows:
            self.impulse_list.set_rows(rows)
            self.impulse_empty.hide()
            self.impulse_list.show()
        else:
            self.impulse_list.hide()
            self.impulse_empty.show()

        # Totals
        while self.totals_row.count():
            it = self.totals_row.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        totals = [
            ("Focus Time", _format_seconds(int(s.get("focus_all", 0)))),
            ("Sessions",    str(int(s.get("sessions_all", 0)))),
            ("Avg Session", _format_seconds(int(s.get("avg_session_seconds", 0)))),
            ("Blocks",      str(int(s.get("block_approved", 0)) + int(s.get("block_denied", 0)) + int(s.get("block_canceled", 0)))),
            ("Off-Topic",   str(int(s.get("off_topic_all", 0)))),
        ]
        for label, value in totals:
            block = QWidget()
            col = QVBoxLayout(block)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            col.addWidget(FieldLabel(label))
            v = QLabel(value)
            v.setFont(serif(24))
            v.setStyleSheet(f"color: {ACCENT};")
            col.addWidget(v)
            self.totals_row.addWidget(block)
        self.totals_row.addStretch(1)
