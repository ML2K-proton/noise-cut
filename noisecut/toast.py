"""Frameless in-app notification shown when the app hides to the tray."""

import time
import tkinter as tk

BG = "#1e1f22"
PANEL = "#2b2d31"
PANEL_ACTIVE = "#3a3d42"
BORDER = "#3a3d42"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
ACCENT = "#3ba55d"
ACCENT_ACTIVE = "#2f8a4a"
DANGER_FG = "#e06c6c"
DANGER_HOVER = "#3a2a2d"

TONE_COLORS = {
    "running": ACCENT,
    "muted": "#e0a33a",
    "error": "#e05a5a",
    "stopped": MUTED,
}

WIDTH = 380
MARGIN = 16
VISIBLE_SECONDS = 9.0
HOVER_GRACE_SECONDS = 2.5
FADE_INTERVAL_MS = 16
FADE_STEP = 0.12


class Toast(tk.Toplevel):
    """Bottom-right notification card with a status dot and actions."""

    def __init__(self, master, title: str, body: str, tone: str = "running",
                 on_open=None, on_quit=None):
        super().__init__(master)
        self._on_open = on_open
        self._on_quit = on_quit
        self._closing = False
        self._alpha = 0.0
        self._deadline = 0.0
        self._timer = None

        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
            self.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.configure(bg=BORDER)

        self._build(title, body, tone)
        self.update_idletasks()
        height = self.winfo_reqheight()
        x, y = self._placement(WIDTH, height)
        self.geometry(f"{WIDTH}x{height}+{x}+{y}")

        self._set_alpha(0.0)
        self.deiconify()
        self.lift()
        self._fade(0.97)
        self._deadline = time.monotonic() + VISIBLE_SECONDS
        self._timer = self.after(250, self._timer_tick)

    def _build(self, title: str, body: str, tone: str) -> None:
        outer = tk.Frame(self, bg=BORDER)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=BG)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        top = tk.Frame(card, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 0))

        dot = tk.Canvas(top, width=10, height=10, bg=BG, highlightthickness=0)
        dot.pack(side="left", pady=(5, 0))
        dot.create_oval(1, 1, 9, 9, fill=TONE_COLORS.get(tone, ACCENT), width=0)

        heading = tk.Label(top, text=title, bg=BG, fg=FG,
                           font=("Segoe UI Semibold", 10))
        heading.pack(side="left", padx=(8, 0))

        close = tk.Button(top, text="×", command=self.dismiss, bg=BG, fg=MUTED,
                          activebackground=PANEL, activeforeground=FG, bd=0,
                          highlightthickness=0, relief="flat", width=2,
                          cursor="hand2", font=("Segoe UI", 11))
        close.pack(side="right")
        self._hover(close, BG, PANEL)

        text = tk.Label(card, text=body, bg=BG, fg=MUTED, justify="left",
                        anchor="w", wraplength=WIDTH - 32,
                        font=("Segoe UI", 9))
        text.pack(fill="x", padx=16, pady=(6, 0))

        actions = tk.Frame(card, bg=BG)
        actions.pack(fill="x", padx=14, pady=(12, 12))

        quit_btn = tk.Button(actions, text="Tắt ứng dụng", command=self._quit,
                             bg=BG, fg=MUTED, activebackground=DANGER_HOVER,
                             activeforeground=DANGER_FG, bd=0,
                             highlightthickness=0, relief="flat", cursor="hand2",
                             padx=10, pady=4, font=("Segoe UI", 9))
        quit_btn.pack(side="right")
        self._hover(quit_btn, BG, DANGER_HOVER, fg=MUTED, hover_fg=DANGER_FG)

        open_btn = tk.Button(actions, text="Mở lại", command=self._open,
                             bg=ACCENT, fg="white", activebackground=ACCENT_ACTIVE,
                             activeforeground="white", bd=0, highlightthickness=0,
                             relief="flat", cursor="hand2", padx=16, pady=4,
                             font=("Segoe UI Semibold", 9))
        open_btn.pack(side="right", padx=(0, 8))
        self._hover(open_btn, ACCENT, ACCENT_ACTIVE)

    def _hover(self, widget, bg: str, hover_bg: str,
               fg: str | None = None, hover_fg: str | None = None) -> None:
        def enter(_event):
            widget.configure(bg=hover_bg)
            if hover_fg:
                widget.configure(fg=hover_fg)

        def leave(_event):
            widget.configure(bg=bg)
            if fg:
                widget.configure(fg=fg)

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _open(self) -> None:
        callback = self._on_open
        self.dismiss()
        if callback is not None:
            callback()

    def _quit(self) -> None:
        callback = self._on_quit
        self._closing = True
        self._cancel_timer()
        try:
            self.destroy()
        except tk.TclError:
            pass
        if callback is not None:
            callback()

    def dismiss(self) -> None:
        if self._closing:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._closing = True
        self._cancel_timer()
        self._fade(0.0, destroy=True)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            try:
                self.after_cancel(self._timer)
            except tk.TclError:
                pass
            self._timer = None

    def _timer_tick(self) -> None:
        if self._closing:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._pointer_inside():
            self._deadline = time.monotonic() + HOVER_GRACE_SECONDS
        elif time.monotonic() >= self._deadline:
            self.dismiss()
            return
        self._timer = self.after(250, self._timer_tick)

    def _pointer_inside(self) -> bool:
        try:
            px, py = self.winfo_pointerxy()
            x = self.winfo_rootx()
            y = self.winfo_rooty()
            return (x <= px < x + self.winfo_width()
                    and y <= py < y + self.winfo_height())
        except tk.TclError:
            return False

    def _set_alpha(self, value: float) -> None:
        self._alpha = value
        try:
            self.attributes("-alpha", value)
        except tk.TclError:
            pass

    def _fade(self, target: float, destroy: bool = False) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if target > self._alpha:
            value = min(target, self._alpha + FADE_STEP)
        else:
            value = max(target, self._alpha - FADE_STEP)
        self._set_alpha(value)
        if abs(value - target) < 0.01:
            if destroy:
                try:
                    self.destroy()
                except tk.TclError:
                    pass
            return
        try:
            self.after(FADE_INTERVAL_MS, lambda: self._fade(target, destroy))
        except tk.TclError:
            pass

    def _placement(self, width: int, height: int) -> tuple[int, int]:
        left, top, area_w, area_h = self._work_area()
        x = max(left, left + area_w - width - MARGIN)
        y = max(top, top + area_h - height - MARGIN)
        return x, y

    def _work_area(self) -> tuple[int, int, int, int]:
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                    0x0030, 0, ctypes.byref(rect), 0):
                return (rect.left, rect.top,
                        rect.right - rect.left, rect.bottom - rect.top)
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
