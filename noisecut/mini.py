"""Small always-on-top mute bar that can be dragged around."""

import tkinter as tk

BG = "#1e1f22"
PANEL = "#2b2d31"
PANEL_ACTIVE = "#3a3d42"
BORDER = "#3a3d42"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
ACCENT = "#3ba55d"
DANGER = "#a33333"
DANGER_ACTIVE = "#8c2b2b"

MARGIN = 16
WIDTH = 236
HEIGHT = 88
HINT_TEXT = "Giữ Ctrl+Shift+? (phím /) để tắt tiếng"


class MiniBar(tk.Toplevel):
    """Compact always-on-top bar with a hold-to-mute button."""

    def __init__(self, master, on_mute_press, on_mute_release,
                 on_help, on_open, on_position):
        super().__init__(master)
        self._on_mute_press = on_mute_press
        self._on_mute_release = on_mute_release
        self._on_help = on_help
        self._on_open = on_open
        self._on_position = on_position
        self._muted = False
        self._toggle_mode = False
        self._running = False
        self._drag = None
        self._pressed = False

        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
            self.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.configure(bg=BORDER)

        self._build()
        self.geometry(f"{WIDTH}x{HEIGHT}")
        self.update_idletasks()

    # ---- layout -------------------------------------------------

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BORDER)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        top = tk.Frame(body, bg=BG)
        top.pack(fill="x", padx=8, pady=(5, 0))

        drag = tk.Label(top, text="⠿", bg=BG, fg=MUTED,
                        font=("Segoe UI", 8))
        drag.pack(side="left")

        self._dot = tk.Canvas(top, width=8, height=8, bg=BG,
                              highlightthickness=0)
        self._dot.pack(side="left", padx=(6, 4), pady=(1, 0))
        self._dot_id = self._dot.create_oval(1, 1, 7, 7, fill=MUTED, width=0)

        self._status = tk.Label(top, text="Đã dừng", bg=BG, fg=MUTED,
                                font=("Segoe UI", 8))
        self._status.pack(side="left")

        self._open_btn = tk.Button(
            top, text="⚙", command=self._on_open, bg=BG, fg=MUTED,
            activebackground=BG, activeforeground=FG, bd=0,
            highlightthickness=0, relief="flat", width=2, cursor="hand2",
            font=("Segoe UI", 9),
        )
        self._open_btn.pack(side="right")
        self._help_btn = tk.Button(
            top, text="?", command=self._on_help, bg=BG, fg=MUTED,
            activebackground=BG, activeforeground=FG, bd=0,
            highlightthickness=0, relief="flat", width=2, cursor="hand2",
            font=("Segoe UI", 9),
        )
        self._help_btn.pack(side="right")

        self._mute_btn = tk.Button(
            body, text="GIỮ ĐỂ TẮT TIẾNG", bg=PANEL, fg=FG,
            activebackground=PANEL_ACTIVE, activeforeground=FG,
            bd=0, highlightthickness=0, relief="flat", cursor="hand2",
            font=("Segoe UI Semibold", 9), padx=4, pady=4,
        )
        self._mute_btn.pack(fill="x", padx=8, pady=(5, 0))
        self._mute_btn.bind("<ButtonPress-1>", self._mute_press)
        self._mute_btn.bind("<ButtonRelease-1>", self._mute_release)

        self._hint = tk.Label(body, text=HINT_TEXT, bg=BG, fg=MUTED,
                              font=("Segoe UI", 7))
        self._hint.pack(fill="x", padx=8, pady=(3, 5))

        for widget in (top, drag, self._status):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
        top.bind("<Double-Button-1>", lambda _event: self._on_open())

    # ---- public state -------------------------------------------

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._refresh()

    def set_toggle_mode(self, toggle: bool) -> None:
        self._toggle_mode = bool(toggle)
        self._refresh()

    def set_running(self, running: bool) -> None:
        if self._running == bool(running):
            return
        self._running = bool(running)
        self._refresh()

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.deiconify()
            self.lift()
            try:
                self.attributes("-topmost", True)
            except tk.TclError:
                pass
        else:
            self.withdraw()

    def place_at(self, x, y) -> None:
        x, y = self._clamp(int(x), int(y))
        self.geometry(f"+{x}+{y}")

    def default_position(self) -> tuple[int, int]:
        vx, vy, vw, vh = self._screen_bounds()
        return vx + vw - WIDTH - MARGIN, vy + MARGIN

    # ---- internals ----------------------------------------------

    def _refresh(self) -> None:
        if self._muted:
            if self._toggle_mode:
                text = "ĐANG TẮT TIẾNG — bấm để mở"
            else:
                text = "ĐANG TẮT TIẾNG — thả để mở"
            self._mute_btn.configure(text=text, bg=DANGER,
                                     activebackground=DANGER_ACTIVE)
            self._status.configure(text="ĐANG TẮT TIẾNG", fg=FG)
            self._dot.itemconfigure(self._dot_id, fill=DANGER)
        else:
            text = "BẤM ĐỂ TẮT TIẾNG" if self._toggle_mode else "GIỮ ĐỂ TẮT TIẾNG"
            self._mute_btn.configure(text=text, bg=PANEL,
                                     activebackground=PANEL_ACTIVE)
            if self._running:
                self._status.configure(text="Đang lọc", fg=MUTED)
                self._dot.itemconfigure(self._dot_id, fill=ACCENT)
            else:
                self._status.configure(text="Đã dừng", fg=MUTED)
                self._dot.itemconfigure(self._dot_id, fill=MUTED)
        self._hint.configure(
            text=HINT_TEXT if not self._toggle_mode
            else "Ctrl+Shift+? để bật/tắt tiếng",
        )

    def _mute_press(self, _event=None) -> None:
        self._pressed = True
        self._mute_btn.configure(relief="flat")
        self._on_mute_press()

    def _mute_release(self, _event=None) -> None:
        if self._pressed:
            self._pressed = False
            self._on_mute_release()

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(),
                      event.y_root - self.winfo_y())
        self.lift()

    def _drag_move(self, event) -> None:
        if self._drag is None:
            return
        dx, dy = self._drag
        x, y = self._clamp(event.x_root - dx, event.y_root - dy)
        self.geometry(f"+{x}+{y}")

    def _drag_end(self, _event=None) -> None:
        if self._drag is None:
            return
        self._drag = None
        self._on_position(self.winfo_x(), self.winfo_y())

    def _screen_bounds(self) -> tuple[int, int, int, int]:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            x = int(user32.GetSystemMetrics(76))   # SM_XVIRTUALSCREEN
            y = int(user32.GetSystemMetrics(77))   # SM_YVIRTUALSCREEN
            w = int(user32.GetSystemMetrics(78))   # SM_CXVIRTUALSCREEN
            h = int(user32.GetSystemMetrics(79))   # SM_CYVIRTUALSCREEN
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        vx, vy, vw, vh = self._screen_bounds()
        x = max(vx, min(x, vx + vw - WIDTH))
        y = max(vy, min(y, vy + vh - HEIGHT))
        return x, y
