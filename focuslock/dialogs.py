"""User-facing prompts — Windows tkinter implementation.

All interactive dialogs run on a dedicated tkinter UI thread.  Other threads
schedule work via root.after(0, func) and use threading.Event to wait for
results.  This avoids the "main thread is not in main loop" crash that tkinter
raises when you call Tk methods from worker threads.
"""

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

# ── Brand colours ─────────────────────────────────────────────────────────────

BG           = "#1c1c1e"   # Dark background
FG           = "#ffffff"   # White text
ACCENT       = "#6b46c1"   # Purple (Locus brand)
ACCENT_HOVER = "#7c3aed"
BTN_BG       = "#2c2c2e"
DANGER       = "#ef4444"
SUCCESS      = "#22c55e"
SUBTEXT      = "#a1a1aa"

# ── Singleton Tk state ────────────────────────────────────────────────────────

_tk_root: Optional[tk.Tk] = None
_tk_thread: Optional[threading.Thread] = None
_tk_lock = threading.Lock()

# Serialize dialog calls — only one prompt at a time.
_prompt_lock = threading.Lock()
_PROMPT_TIMEOUT_SECONDS = 600


def _ensure_tk():
    """Start the tkinter event loop in a background thread if it isn't running."""
    global _tk_root, _tk_thread

    with _tk_lock:
        if _tk_root is not None:
            return
        ready = threading.Event()

        def _run():
            global _tk_root
            root = tk.Tk()
            root.withdraw()                         # Hidden main window
            root.title("Locus")
            root.configure(bg=BG)
            # Make the invisible root window non-interactive
            root.wm_attributes("-alpha", 0)
            _tk_root = root
            ready.set()
            root.mainloop()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _tk_thread = t
        ready.wait(timeout=5)


def _run_on_tk(func):
    """Schedule func on the tkinter thread and block until it returns a value."""
    _ensure_tk()
    result_holder = []
    done = threading.Event()

    def wrapper():
        try:
            result_holder.append(func())
        except Exception as e:
            result_holder.append(None)
            print(f"[Locus dialogs] Error on tk thread: {e}")
        finally:
            done.set()

    _tk_root.after(0, wrapper)
    done.wait(timeout=_PROMPT_TIMEOUT_SECONDS)
    return result_holder[0] if result_holder else None


# ── Common window helpers ─────────────────────────────────────────────────────

def _apply_dark(w: tk.Widget):
    """Recursively apply dark theme to a widget and all children."""
    try:
        cls = w.winfo_class()
        if cls in ("Frame", "Toplevel", "Label"):
            w.configure(bg=BG)
        elif cls == "Text":
            w.configure(bg=BTN_BG, fg=FG, insertbackground=FG,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=ACCENT, highlightcolor=ACCENT)
        elif cls == "Entry":
            w.configure(bg=BTN_BG, fg=FG, insertbackground=FG,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=ACCENT, highlightcolor=ACCENT)
        elif cls == "Button":
            w.configure(bg=BTN_BG, fg=FG, relief="flat", bd=0,
                        activebackground=ACCENT_HOVER, activeforeground=FG,
                        cursor="hand2")
        elif cls == "Listbox":
            w.configure(bg=BTN_BG, fg=FG, selectbackground=ACCENT,
                        selectforeground=FG, relief="flat", bd=0,
                        highlightthickness=0)
    except Exception:
        pass
    for child in w.winfo_children():
        _apply_dark(child)


def _center(win: tk.Toplevel, width: int, height: int):
    """Center win on the screen."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")


def _make_button(parent, text: str, color: str, command):
    """Create a styled button."""
    btn = tk.Button(
        parent, text=text, bg=color, fg=FG,
        activebackground=ACCENT_HOVER, activeforeground=FG,
        relief="flat", bd=0, padx=14, pady=7,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2", command=command,
    )
    return btn


# ── ask_reason ────────────────────────────────────────────────────────────────

def ask_reason(blocked_name: str, blocked_type: str, session_name: str) -> Tuple[str, str]:
    """Show the reason-entry dialog. Returns (action, reason).

    action ∈ {"submit", "override", "cancel"}
    """
    result = [("cancel", "")]

    def build():
        win = tk.Toplevel(_tk_root)
        win.title("Locus")
        win.configure(bg=BG)
        win.wm_attributes("-topmost", True)
        win.resizable(False, False)
        _center(win, 440, 310)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Label(win, text="Locus", fg=ACCENT, bg=BG,
                       font=("Segoe UI", 16, "bold"))
        hdr.pack(pady=(18, 4))

        # ── Body text ────────────────────────────────────────────────────────
        btype_label = "app" if blocked_type == "app" else "website"
        msg = tk.Label(
            win,
            text=f"You tried to open \"{blocked_name}\"",
            fg=FG, bg=BG,
            font=("Segoe UI", 11),
        )
        msg.pack()

        sess_label = tk.Label(
            win,
            text=f"Session: {session_name}",
            fg=SUBTEXT, bg=BG,
            font=("Segoe UI", 9),
        )
        sess_label.pack(pady=(2, 10))

        # ── Reason text box ──────────────────────────────────────────────────
        txt = tk.Text(win, height=3, font=("Segoe UI", 10), wrap="word")
        txt.configure(bg=BTN_BG, fg=SUBTEXT, insertbackground=FG,
                      relief="flat", bd=0, highlightthickness=1,
                      highlightbackground=ACCENT, highlightcolor=ACCENT,
                      padx=8, pady=6)
        placeholder = "Why do you need access?"
        txt.insert("1.0", placeholder)
        txt.pack(fill="x", padx=20, pady=(0, 14))

        def on_focus_in(event):
            if txt.get("1.0", "end-1c") == placeholder:
                txt.delete("1.0", "end")
                txt.configure(fg=FG)

        def on_focus_out(event):
            if not txt.get("1.0", "end-1c").strip():
                txt.delete("1.0", "end")
                txt.insert("1.0", placeholder)
                txt.configure(fg=SUBTEXT)

        txt.bind("<FocusIn>", on_focus_in)
        txt.bind("<FocusOut>", on_focus_out)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        done = threading.Event()

        def on_submit():
            reason = txt.get("1.0", "end-1c").strip()
            if reason == placeholder:
                reason = ""
            result[0] = ("submit", reason)
            win.destroy()
            done.set()

        def on_override():
            result[0] = ("override", "")
            win.destroy()
            done.set()

        def on_cancel():
            result[0] = ("cancel", "")
            win.destroy()
            done.set()

        win.protocol("WM_DELETE_WINDOW", on_cancel)

        _make_button(btn_frame, "Submit", ACCENT, on_submit).pack(
            side="left", expand=True, fill="x", padx=(0, 6))
        _make_button(btn_frame, "Override", BTN_BG, on_override).pack(
            side="left", expand=True, fill="x", padx=(0, 6))
        cancel_btn = tk.Button(
            btn_frame, text="Cancel",
            bg=BG, fg=DANGER,
            relief="flat", bd=1,
            highlightthickness=1, highlightbackground=DANGER,
            highlightcolor=DANGER,
            padx=14, pady=7,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2", command=on_cancel,
        )
        cancel_btn.pack(side="left", expand=True, fill="x")

        win.lift()
        win.focus_force()
        return done

    with _prompt_lock:
        done_event = _run_on_tk(build)
        if done_event:
            done_event.wait(timeout=_PROMPT_TIMEOUT_SECONDS)
    return result[0]


# ── ask_override_code ─────────────────────────────────────────────────────────

def ask_override_code(expected: str) -> bool:
    """Prompt for the override code. Returns True if correct."""
    if not expected or not expected.strip():
        show_override_wrong()
        return False

    result = [False]

    def build():
        win = tk.Toplevel(_tk_root)
        win.title("Locus — Override")
        win.configure(bg=BG)
        win.wm_attributes("-topmost", True)
        win.resizable(False, False)
        _center(win, 340, 200)

        tk.Label(win, text="Locus", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 14, "bold")).pack(pady=(16, 6))

        hint = "Pi override" if expected.startswith("3141592653589") else "Enter override code"
        tk.Label(win, text=hint, fg=FG, bg=BG,
                 font=("Segoe UI", 10)).pack()

        entry = tk.Entry(win, show="*", font=("Segoe UI", 11))
        entry.configure(bg=BTN_BG, fg=FG, insertbackground=FG,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=ACCENT, highlightcolor=ACCENT)
        entry.pack(fill="x", padx=24, pady=(10, 12))
        entry.focus_set()

        done = threading.Event()

        def on_submit():
            entered = entry.get().strip()
            if expected.startswith("3141592653589") or expected.isdigit():
                cleaned = "".join(c for c in entered if c.isdigit())
                result[0] = (cleaned == expected)
            else:
                result[0] = (entered == expected.strip())
            win.destroy()
            done.set()

        def on_cancel():
            result[0] = False
            win.destroy()
            done.set()

        win.protocol("WM_DELETE_WINDOW", on_cancel)
        entry.bind("<Return>", lambda e: on_submit())

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=24)
        _make_button(btn_frame, "Submit", ACCENT, on_submit).pack(
            side="left", expand=True, fill="x", padx=(0, 8))
        _make_button(btn_frame, "Cancel", DANGER, on_cancel).pack(
            side="left", expand=True, fill="x")

        win.lift()
        return done

    with _prompt_lock:
        done_event = _run_on_tk(build)
        if done_event:
            done_event.wait(timeout=60)
    return result[0]


# ── show_result ───────────────────────────────────────────────────────────────

def show_result(approved: bool, explanation: str, target_name: str, minutes: int = 15):
    """Non-blocking result panel. Auto-closes after 6 seconds."""

    def build():
        win = tk.Toplevel(_tk_root)
        win.title("Locus")
        win.configure(bg=BG)
        win.wm_attributes("-topmost", True)
        win.resizable(False, False)
        _center(win, 380, 220)

        icon = "✓" if approved else "✗"
        color = SUCCESS if approved else DANGER
        verdict = "Approved" if approved else "Denied"
        mins_text = f"Allowed for {minutes} min" if approved else ""

        tk.Label(win, text=icon, fg=color, bg=BG,
                 font=("Segoe UI", 32, "bold")).pack(pady=(20, 4))

        tk.Label(win, text=verdict, fg=color, bg=BG,
                 font=("Segoe UI", 13, "bold")).pack()

        if mins_text:
            tk.Label(win, text=mins_text, fg=SUBTEXT, bg=BG,
                     font=("Segoe UI", 9)).pack(pady=(2, 0))

        tk.Label(win, text=explanation, fg=FG, bg=BG,
                 font=("Segoe UI", 10), wraplength=340,
                 justify="center").pack(pady=(8, 14))

        def dismiss():
            try:
                win.destroy()
            except Exception:
                pass

        _make_button(win, "Dismiss", BTN_BG, dismiss).pack(pady=(0, 14))
        win.protocol("WM_DELETE_WINDOW", dismiss)
        win.lift()

        # Auto-close after 6 seconds
        win.after(6000, dismiss)

    # Non-blocking — don't hold prompt_lock here, just fire and forget
    _ensure_tk()
    _tk_root.after(0, build)


# ── ask_off_topic_reason ──────────────────────────────────────────────────────

def ask_off_topic_reason(
    domain: str,
    tab_title: str,
    session_name: str,
    ai_reason: str,
) -> Tuple[str, str]:
    """Show the off-topic dialog. Returns (action, reason)."""
    result = [("cancel", "")]

    def build():
        win = tk.Toplevel(_tk_root)
        win.title("Locus — Off-topic detected")
        win.configure(bg=BG)
        win.wm_attributes("-topmost", True)
        win.resizable(False, False)
        _center(win, 440, 340)

        tk.Label(win, text="Locus", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 14, "bold")).pack(pady=(16, 4))

        tk.Label(win, text=f"Off-topic content on {domain}",
                 fg=FG, bg=BG, font=("Segoe UI", 11)).pack()

        tk.Label(win, text=f"Page: \"{tab_title}\"",
                 fg=SUBTEXT, bg=BG, font=("Segoe UI", 9),
                 wraplength=380).pack(pady=(2, 0))

        tk.Label(win, text=f"AI reason: {ai_reason}",
                 fg=SUBTEXT, bg=BG, font=("Segoe UI", 9, "italic"),
                 wraplength=380).pack(pady=(2, 6))

        tk.Label(win, text=f"Session: {session_name}",
                 fg=SUBTEXT, bg=BG, font=("Segoe UI", 9)).pack(pady=(0, 8))

        txt = tk.Text(win, height=3, font=("Segoe UI", 10), wrap="word")
        txt.configure(bg=BTN_BG, fg=SUBTEXT, insertbackground=FG,
                      relief="flat", bd=0, highlightthickness=1,
                      highlightbackground=ACCENT, highlightcolor=ACCENT,
                      padx=8, pady=6)
        placeholder = "Why is this relevant to your session?"
        txt.insert("1.0", placeholder)
        txt.pack(fill="x", padx=20, pady=(0, 12))

        def on_focus_in(event):
            if txt.get("1.0", "end-1c") == placeholder:
                txt.delete("1.0", "end")
                txt.configure(fg=FG)

        def on_focus_out(event):
            if not txt.get("1.0", "end-1c").strip():
                txt.delete("1.0", "end")
                txt.insert("1.0", placeholder)
                txt.configure(fg=SUBTEXT)

        txt.bind("<FocusIn>", on_focus_in)
        txt.bind("<FocusOut>", on_focus_out)

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=20)
        done = threading.Event()

        def on_submit():
            reason = txt.get("1.0", "end-1c").strip()
            if reason == placeholder:
                reason = ""
            result[0] = ("submit", reason)
            win.destroy()
            done.set()

        def on_cancel():
            result[0] = ("cancel", "")
            win.destroy()
            done.set()

        win.protocol("WM_DELETE_WINDOW", on_cancel)

        _make_button(btn_frame, "Submit", ACCENT, on_submit).pack(
            side="left", expand=True, fill="x", padx=(0, 8))
        _make_button(btn_frame, "Cancel", DANGER, on_cancel).pack(
            side="left", expand=True, fill="x")

        win.lift()
        win.focus_force()
        return done

    with _prompt_lock:
        done_event = _run_on_tk(build)
        if done_event:
            done_event.wait(timeout=_PROMPT_TIMEOUT_SECONDS)
    return result[0]


# ── show_override_wrong ───────────────────────────────────────────────────────

def show_override_wrong():
    show_notification("Locus", "Incorrect override code.")


# ── show_notification ─────────────────────────────────────────────────────────

def show_notification(title: str, message: str):
    """Small auto-dismissing dark tooltip in the bottom-right corner.

    Non-blocking — schedules on the tk thread and returns immediately.
    """
    _ensure_tk()

    def build():
        win = tk.Toplevel(_tk_root)
        win.configure(bg=BG)
        win.overrideredirect(True)          # No title bar / frame
        win.wm_attributes("-topmost", True)

        # Measure content
        pad = 14
        lbl_title = tk.Label(win, text=title, fg=ACCENT, bg=BG,
                              font=("Segoe UI", 10, "bold"))
        lbl_title.pack(anchor="w", padx=pad, pady=(pad, 2))
        lbl_msg = tk.Label(win, text=message, fg=FG, bg=BG,
                           font=("Segoe UI", 9), wraplength=260)
        lbl_msg.pack(anchor="w", padx=pad, pady=(0, pad))

        win.update_idletasks()
        w = win.winfo_reqwidth() + 10
        h = win.winfo_reqheight() + 6

        # Position bottom-right (20px margin)
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = sw - w - 20
        y = sh - h - 60   # 60px above taskbar
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.lift()

        def dismiss():
            try:
                win.destroy()
            except Exception:
                pass

        win.after(3000, dismiss)

    _tk_root.after(0, build)
