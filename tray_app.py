"""Locus tray application for Windows.

Uses pystray for the system tray icon and tkinter for dialogs.
Reads state.json (written by locusd) and writes command.json for IPC.
Launches locusd as a separate subprocess on startup.
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw, ImageFont

from focuslock.paths import STATE_PATH, COMMAND_PATH, CONFIG_PATH, APP_DATA_DIR


# ── Icon drawing ──────────────────────────────────────────────────────────────

def _make_icon(active: bool) -> Image.Image:
    """Draw a 64×64 PIL image: purple circle when active, gray when not."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    circle_color = "#6b46c1" if active else "#666666"
    draw.ellipse([4, 4, 60, 60], fill=circle_color)

    # Draw a white "L" in the center
    try:
        font = ImageFont.truetype("segoeui.ttf", 28)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()

    text = "L"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(text, font=font)
    x = (64 - tw) // 2
    y = (64 - th) // 2
    draw.text((x, y), text, fill="white", font=font)

    return img


# ── State / command helpers ───────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _send_command(cmd_type: str, data: dict = None):
    data = data or {}
    payload = {"type": cmd_type, "data": data}
    tmp = COMMAND_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, COMMAND_PATH)
    except Exception as e:
        print(f"[tray] send_command error: {e}")


# ── Session picker dialog ─────────────────────────────────────────────────────

_tk_root: tk.Tk = None
_tk_thread = None
_tk_ready = threading.Event()


def _ensure_tk():
    global _tk_root, _tk_thread
    if _tk_root is not None:
        return
    ready = threading.Event()

    def run():
        global _tk_root
        root = tk.Tk()
        root.withdraw()
        root.configure(bg="#1c1c1e")
        root.wm_attributes("-alpha", 0)
        _tk_root = root
        ready.set()
        root.mainloop()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    _tk_thread = t
    ready.wait(timeout=5)


def _show_session_picker():
    """Open a Tkinter window to pick an event or type a custom session name."""
    _ensure_tk()

    def build():
        state = _read_state()
        events = state.get("events", [])

        win = tk.Toplevel(_tk_root)
        win.title("Start Session — Locus")
        win.configure(bg="#1c1c1e")
        win.wm_attributes("-topmost", True)
        win.resizable(True, True)

        # Center window
        win.update_idletasks()
        w, h = 480, 400
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # ── Header ────────────────────────────────────────────────────────
        tk.Label(win, text="Start a Focus Session", fg="#6b46c1", bg="#1c1c1e",
                 font=("Segoe UI", 14, "bold")).pack(pady=(18, 6))

        # ── Event list ────────────────────────────────────────────────────
        if events:
            tk.Label(win, text="Upcoming events:", fg="#a1a1aa", bg="#1c1c1e",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=20)

            frame = tk.Frame(win, bg="#1c1c1e")
            frame.pack(fill="both", expand=True, padx=20, pady=(4, 0))

            scrollbar = tk.Scrollbar(frame)
            scrollbar.pack(side="right", fill="y")

            listbox = tk.Listbox(
                frame,
                yscrollcommand=scrollbar.set,
                font=("Segoe UI", 10),
                bg="#2c2c2e", fg="#ffffff",
                selectbackground="#6b46c1", selectforeground="#ffffff",
                relief="flat", bd=0, highlightthickness=0,
                activestyle="none",
            )
            for ev in events:
                date = ev.get("date", "")
                title = ev.get("title", "")
                class_name = ev.get("class_name", "")
                label = f"{date}  —  {title}"
                if class_name:
                    label += f"  ({class_name})"
                listbox.insert("end", label)
            listbox.pack(fill="both", expand=True)
            scrollbar.config(command=listbox.yview)
        else:
            listbox = None
            tk.Label(win, text="No upcoming events found.", fg="#a1a1aa", bg="#1c1c1e",
                     font=("Segoe UI", 10)).pack(pady=20)

        # ── Custom session ────────────────────────────────────────────────
        tk.Label(win, text="Or type a custom session name:", fg="#a1a1aa", bg="#1c1c1e",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(10, 2))

        custom_entry = tk.Entry(win, font=("Segoe UI", 10))
        custom_entry.configure(bg="#2c2c2e", fg="#ffffff", insertbackground="#ffffff",
                                relief="flat", bd=0, highlightthickness=1,
                                highlightbackground="#6b46c1", highlightcolor="#6b46c1")
        custom_entry.pack(fill="x", padx=20, pady=(0, 12))

        # ── Buttons ───────────────────────────────────────────────────────
        btn_frame = tk.Frame(win, bg="#1c1c1e")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        def on_start():
            custom = custom_entry.get().strip()
            if custom:
                _send_command("start_custom_session", {"title": custom})
                win.destroy()
                return
            if listbox:
                sel = listbox.curselection()
                if sel:
                    idx = sel[0]
                    ev = events[idx]
                    _send_command("start_session", {
                        "title": ev.get("title", ""),
                        "date": ev.get("date", ""),
                    })
                    win.destroy()
                    return
            # Nothing selected
            win.lift()

        def on_cancel():
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_cancel)

        start_btn = tk.Button(
            btn_frame, text="Start Session",
            bg="#6b46c1", fg="#ffffff",
            activebackground="#7c3aed", activeforeground="#ffffff",
            relief="flat", bd=0, padx=14, pady=8,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            command=on_start,
        )
        start_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        cancel_btn = tk.Button(
            btn_frame, text="Cancel",
            bg="#2c2c2e", fg="#ffffff",
            activebackground="#3c3c3e", activeforeground="#ffffff",
            relief="flat", bd=0, padx=14, pady=8,
            font=("Segoe UI", 10),
            cursor="hand2", command=on_cancel,
        )
        cancel_btn.pack(side="left", expand=True, fill="x")

        win.lift()
        win.focus_force()
        custom_entry.focus_set()

    _tk_root.after(0, build)


# ── Menu builder ──────────────────────────────────────────────────────────────

def _get_menu(icon, active_session):
    """Build the pystray context menu."""
    items = []

    if active_session:
        name = active_session.get("display_name") or active_session.get("title", "Session")
        items.append(pystray.MenuItem(f"● {name}", None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("End Session", lambda: _send_command("end_session")))
        items.append(pystray.Menu.SEPARATOR)
    else:
        items.append(pystray.MenuItem("Start Session...", lambda: _show_session_picker()))
        items.append(pystray.Menu.SEPARATOR)

    items.append(pystray.MenuItem("Refresh", lambda: _send_command("refresh")))
    items.append(pystray.MenuItem("Open Config Folder", lambda: os.startfile(APP_DATA_DIR)))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("Exit", lambda: _on_exit(icon)))

    return pystray.Menu(*items)


def _on_exit(icon):
    """Clean up and exit."""
    icon.stop()
    # Give pystray a moment to shut down, then terminate
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()


# ── Daemon launcher ───────────────────────────────────────────────────────────

_daemon_proc = None


def _start_daemon():
    """Launch locusd_entry.py as a separate subprocess."""
    global _daemon_proc
    try:
        entry = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locusd_entry.py")
        _daemon_proc = subprocess.Popen(
            [sys.executable, entry],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        print(f"[tray] Daemon started (pid {_daemon_proc.pid})")
    except Exception as e:
        print(f"[tray] Failed to start daemon: {e}")


# ── Main entry point ──────────────────────────────────────────────────────────

def main():
    _ensure_tk()
    _start_daemon()

    # Start with inactive icon
    icon_img = _make_icon(False)
    icon = pystray.Icon("Locus", icon_img, "Locus", menu=_get_menu(None, None))

    # Background thread: poll state and update icon/menu every 2s
    def updater():
        while True:
            try:
                state = _read_state()
                session = state.get("session")
                active = session is not None
                icon.icon = _make_icon(active)
                icon.menu = _get_menu(icon, session)
                tooltip = f"Locus — {session.get('display_name', 'Active')}" if active else "Locus — Idle"
                icon.title = tooltip
            except Exception:
                pass
            time.sleep(2)

    t = threading.Thread(target=updater, daemon=True)
    t.start()

    icon.run()


if __name__ == "__main__":
    main()
