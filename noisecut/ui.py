"""Custom rounded controls and dialogs for the Noise Cut interface."""

from __future__ import annotations

import ctypes
import os
import re
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Sequence

from PIL import Image, ImageDraw, ImageTk

BG = "#1e1f22"
CARD = "#25272c"
BORDER = "#36393f"
FG = "#f2f3f5"
MUTED = "#9aa0a6"
PANEL = "#2b2d31"
PANEL_ACTIVE = "#3a3d42"
ACCENT = "#3ba55d"
ACCENT_ACTIVE = "#2f8a4a"
DANGER = "#a33333"
DANGER_ACTIVE = "#8c2b2b"
DANGER_FG = "#e06c6c"
DANGER_HOVER = "#3a2a2d"
WARN = "#e0a33a"
WHITE = "#ffffff"

FONT = ("Segoe UI", 9)
FONT_SEMIBOLD = ("Segoe UI Semibold", 9)
FONT_TITLE = ("Segoe UI Semibold", 12)


def _round_photo(master, width: int, height: int, radius: int, fill: str,
                 outline: str | None = None, border: int = 0):
    width = max(1, int(width))
    height = max(1, int(height))
    scale = 4
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=max(0, radius) * scale,
        fill=fill,
        outline=outline,
        width=max(1, border * scale) if outline else 0,
    )
    image = image.resize((width, height), Image.LANCZOS)
    return ImageTk.PhotoImage(image, master=master)


def _font(master, spec) -> tkfont.Font:
    return tkfont.Font(root=master, font=spec)


def _truncate(font: tkfont.Font, text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if font.measure(text) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if font.measure(text[:middle] + ellipsis) <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ellipsis


def apply_dark_titlebar(window: tk.Misc) -> None:
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        enabled = ctypes.c_int(1)
        for attribute in (20, 19):
            if dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(enabled),
                    ctypes.sizeof(enabled)) == 0:
                break
        caption = ctypes.c_uint(0x00221F1E)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        text = ctypes.c_uint(0x00F5F3F2)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
        border = ctypes.c_uint(0x003F3936)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
    except Exception:
        pass


def apply_round_region(window: tk.Toplevel, radius: int = 12) -> None:
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        width = max(1, window.winfo_width())
        height = max(1, window.winfo_height())
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        region = gdi32.CreateRoundRectRgn(
            0, 0, width + 1, height + 1, radius * 2, radius * 2)
        if region:
            user32.SetWindowRgn(hwnd, region, True)
    except Exception:
        pass


class RoundButton(tk.Canvas):
    """Canvas button with antialiased rounded corners and hover states."""

    KINDS = {
        "primary": (ACCENT, ACCENT_ACTIVE, WHITE, WHITE, None),
        "secondary": (PANEL, PANEL_ACTIVE, FG, FG, BORDER),
        "danger": (DANGER, DANGER_ACTIVE, WHITE, WHITE, None),
        "ghost": (None, PANEL, MUTED, FG, None),
        "ghost_danger": (None, DANGER_HOVER, MUTED, DANGER_FG, None),
    }

    def __init__(self, master, text: str = "", command=None, kind: str = "secondary",
                 height: int = 38, padx: int = 14, font=FONT_SEMIBOLD,
                 bg: str = BG, radius: int | None = None, anchor: str = "center",
                 width: int | None = None, on_press=None, on_release=None):
        self._font_spec = font
        self._font = _font(master, font)
        self._auto_width = width is None
        self._padx = padx
        self._text = text
        self._command = command
        self._kind = kind
        self._bg = bg
        self._height = height
        self._radius = height // 2 if radius is None else radius
        self._anchor = anchor
        self._on_press = on_press
        self._on_release = on_release
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._photo = None
        if width is None:
            width = self._font.measure(text) + 2 * padx
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", self._key_invoke)
        self.bind("<space>", self._key_invoke)

    def _palette(self):
        fill, hover_fill, fg, hover_fg, outline = self.KINDS.get(
            self._kind, self.KINDS["secondary"])
        if fill is None:
            fill = self._bg
        if not self._enabled:
            return PANEL, PANEL, MUTED, MUTED, BORDER
        return fill, hover_fill, fg, hover_fg, outline

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        fill, hover_fill, fg, hover_fg, outline = self._palette()
        body = hover_fill if self._hover and self._enabled else fill
        label = hover_fg if self._hover and self._enabled else fg
        self.delete("all")
        self._photo = _round_photo(
            self, width, height, self._radius, body, outline,
            1 if outline else 0)
        self.create_image(0, 0, anchor="nw", image=self._photo)
        if self._text:
            if self._anchor == "w":
                x = self._padx
                anchor = "w"
            else:
                x = width / 2
                anchor = "center"
            self.create_text(x, height / 2, text=self._text, anchor=anchor,
                             fill=label, font=self._font)

    def _enter(self, _event=None) -> None:
        if self._enabled:
            self._hover = True
            self._draw()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._draw()

    def _press(self, _event=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self.focus_set()
        if self._on_press is not None:
            self._on_press()

    def _release(self, event=None) -> None:
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if self._on_release is not None:
            self._on_release()
        if not was_pressed or event is None:
            return
        inside = (0 <= event.x < self.winfo_width()
                  and 0 <= event.y < self.winfo_height())
        if inside and self._command is not None:
            self._command()

    def _key_invoke(self, _event=None) -> str:
        self.invoke()
        return "break"

    def invoke(self) -> None:
        if self._enabled and self._command is not None:
            self._command()

    def set_text(self, text: str) -> None:
        self._text = text
        if self._auto_width:
            self.configure(width=self._font.measure(text) + 2 * self._padx)
        self._draw()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._hover = False
        self._pressed = False
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


class RoundCheck(tk.Canvas):
    """Rounded checkbox with a custom check mark."""

    def __init__(self, master, text: str, variable: tk.BooleanVar, command=None,
                 bg: str = BG, font=FONT):
        self._var = variable
        self._command = command
        self._font = _font(master, font)
        self._text = text
        self._bg = bg
        self._hover = False
        self._box_photo = None
        width = 24 + self._font.measure(text) + 4
        super().__init__(master, width=width, height=24, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._hovering(True))
        self.bind("<Leave>", lambda _event: self._hovering(False))
        self.bind("<Button-1>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<Return>", self._toggle)
        self._var.trace_add("write", lambda *_args: self._draw())

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("all")
        checked = bool(self._var.get())
        top = (height - 16) // 2
        fill = ACCENT if checked else PANEL
        if self._hover:
            fill = ACCENT_ACTIVE if checked else PANEL_ACTIVE
        outline = ACCENT if checked else BORDER
        self._box_photo = _round_photo(
            self, 16, 16, 4, fill, outline, 1)
        self.create_image(1, top, anchor="nw", image=self._box_photo)
        if checked:
            self.create_line(4, top + 8, 7, top + 11, 12, top + 5,
                             fill=WHITE, width=2, capstyle="round",
                             joinstyle="round")
        self.create_text(24, height / 2, text=self._text, anchor="w",
                         fill=FG if self._hover else FG, font=self._font)

    def _hovering(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def _toggle(self, _event=None) -> str:
        self._var.set(not bool(self._var.get()))
        if self._command is not None:
            self._command()
        self._draw()
        return "break"


class RoundScale(tk.Canvas):
    """Rounded slider with a draggable thumb."""

    def __init__(self, master, variable: tk.DoubleVar, from_: float, to: float,
                 command=None, bg: str = BG):
        self._var = variable
        self._from = float(from_)
        self._to = float(to)
        self._command = command
        self._hover = False
        self._dragging = False
        super().__init__(master, height=24, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=1)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._hovering(True))
        self.bind("<Leave>", lambda _event: self._hovering(False))
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Left>", lambda _event: self._nudge(-1))
        self.bind("<Down>", lambda _event: self._nudge(-1))
        self.bind("<Right>", lambda _event: self._nudge(1))
        self.bind("<Up>", lambda _event: self._nudge(1))
        self.bind("<Home>", lambda _event: self._jump_to(self._from))
        self.bind("<End>", lambda _event: self._jump_to(self._to))
        self._var.trace_add("write", lambda *_args: self._draw())

    def _ratio(self) -> float:
        span = self._to - self._from
        if abs(span) < 1e-9:
            return 0.0
        return max(0.0, min(1.0, (float(self._var.get()) - self._from) / span))

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        if width <= 2:
            return
        x0, x1 = 9, max(10, width - 9)
        y = height / 2
        ratio = self._ratio()
        thumb_x = x0 + (x1 - x0) * ratio
        self.delete("all")
        self.create_line(x0, y, x1, y, fill=PANEL, width=6,
                         capstyle="round")
        if thumb_x > x0:
            self.create_line(x0, y, thumb_x, y, fill=ACCENT, width=6,
                             capstyle="round")
        outline = ACCENT if self._hover or self._dragging else BG
        self.create_oval(thumb_x - 8, y - 8, thumb_x + 8, y + 8,
                         fill=FG, outline=outline, width=2)

    def _set_from_event(self, event) -> None:
        width = max(1, self.winfo_width())
        x0, x1 = 9, max(10, width - 9)
        x = max(x0, min(x1, event.x))
        ratio = (x - x0) / max(1, x1 - x0)
        value = self._from + ratio * (self._to - self._from)
        self._var.set(value)
        if self._command is not None:
            self._command(value)
        self._draw()

    def _hovering(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def _press(self, event) -> None:
        self._dragging = True
        self._set_from_event(event)

    def _move(self, event) -> None:
        if self._dragging:
            self._set_from_event(event)

    def _release(self, _event=None) -> None:
        self._dragging = False
        self._draw()

    def _nudge(self, direction: int) -> str:
        span = self._to - self._from
        step = span / 20.0 if span else 0.0
        self._jump_to(float(self._var.get()) + direction * step)
        return "break"

    def _jump_to(self, value: float) -> str:
        value = max(min(self._from, self._to), min(value, max(self._from, self._to)))
        self._var.set(value)
        if self._command is not None:
            self._command(value)
        self._draw()
        return "break"


class RoundedCard(tk.Canvas):
    """Rounded panel whose body frame is managed by the canvas."""

    def __init__(self, master, bg: str = BG, fill: str = CARD,
                 outline: str = BORDER, radius: int = 14, padding: int = 10):
        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._padding = padding
        self._photo = None
        self._last_height = 0
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=1)
        self.body = tk.Frame(self, bg=fill)
        self._body_window = self.create_window(
            radius, padding, anchor="nw", window=self.body)
        self.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._body_changed)

    def _resize(self, event) -> None:
        self.itemconfigure(
            self._body_window, width=max(1, event.width - 2 * self._radius))
        if event.width <= 1 or event.height <= 1:
            return
        self._photo = _round_photo(
            self, event.width, event.height, self._radius,
            self._fill, self._outline, 1)
        self.delete("cardbg")
        self.create_image(0, 0, anchor="nw", image=self._photo, tags="cardbg")
        self.tag_lower("cardbg")

    def _body_changed(self, _event=None) -> None:
        needed = self.body.winfo_reqheight() + 2 * self._padding
        if needed > 1 and needed != self._last_height:
            self._last_height = needed
            self.configure(height=needed)


class RoundCombo(tk.Canvas):
    """Read-only rounded dropdown with a custom popup list."""

    def __init__(self, master, values: Sequence[str] = (), textvariable=None,
                 placeholder: str = "", width: int = 260, height: int = 34,
                 bg: str = BG, font=FONT):
        self._values = list(values)
        self._var = textvariable
        self._placeholder = placeholder
        self._bg = bg
        self._font = _font(master, font)
        self._value = str(textvariable.get()) if textvariable is not None else ""
        self._index = self._values.index(self._value) if self._value in self._values else -1
        self._hover = False
        self._open = False
        self._photo = None
        self._popup = None
        self._root_bind = None
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._hovering(True))
        self.bind("<Leave>", lambda _event: self._hovering(False))
        self.bind("<Button-1>", self._clicked)
        self.bind("<Return>", self._clicked)
        self.bind("<space>", self._clicked)
        self.bind("<Unmap>", lambda _event: self._close_dropdown())
        self.bind("<Destroy>", lambda _event: self._close_dropdown())

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        body = PANEL_ACTIVE if self._hover or self._open else PANEL
        outline = ACCENT if self._open else BORDER
        self.delete("all")
        self._photo = _round_photo(self, width, height, 9, body, outline, 1)
        self.create_image(0, 0, anchor="nw", image=self._photo)
        text = self._value if self._value else self._placeholder
        color = FG if self._value else MUTED
        if text:
            available = width - 38
            self.create_text(12, height / 2, anchor="w",
                             text=_truncate(self._font, text, available),
                             fill=color, font=self._font)
        cx = width - 16
        cy = height / 2
        if self._open:
            self.create_line(cx - 4, cy + 2, cx, cy - 2, cx + 4, cy + 2,
                             fill=MUTED, width=2, capstyle="round",
                             joinstyle="round")
        else:
            self.create_line(cx - 4, cy - 2, cx, cy + 2, cx + 4, cy - 2,
                             fill=MUTED, width=2, capstyle="round",
                             joinstyle="round")

    def _hovering(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def _clicked(self, _event=None) -> str:
        if self._open:
            self._close_dropdown()
        else:
            self._open_dropdown()
        return "break"

    def _open_dropdown(self) -> None:
        self._close_dropdown()
        self.focus_set()
        self._open = True
        self._draw()
        try:
            self._popup = _ComboPopup(
                self, self._values, self._index, self._pick, self._popup_closed)
            self._root_bind = self.winfo_toplevel().bind(
                "<Configure>", self._root_moved, add="+")
        except Exception:
            self._open = False
            self._popup = None
            self._draw()

    def _root_moved(self, _event=None) -> None:
        self._close_dropdown()

    def _pick(self, index: int) -> None:
        if not 0 <= index < len(self._values):
            self._close_dropdown()
            return
        self._index = index
        self._value = self._values[index]
        if self._var is not None:
            self._var.set(self._value)
        self._close_dropdown()
        self.event_generate("<<ComboboxSelected>>")

    def _popup_closed(self) -> None:
        self._popup = None
        self._unbind_root()
        self._open = False
        self._draw()

    def _unbind_root(self) -> None:
        if self._root_bind is None:
            return
        try:
            self.winfo_toplevel().unbind("<Configure>", self._root_bind)
        except tk.TclError:
            pass
        self._root_bind = None

    def _close_dropdown(self) -> None:
        popup = self._popup
        self._popup = None
        self._unbind_root()
        if popup is not None:
            try:
                popup.close(notify=False)
            except tk.TclError:
                pass
        self._open = False
        try:
            self._draw()
        except tk.TclError:
            pass

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = str(value)
        self._index = self._values.index(self._value) if self._value in self._values else -1
        if self._var is not None:
            self._var.set(self._value)
        self._draw()

    def current(self, index: int | None = None):
        if index is None:
            return self._index
        if 0 <= index < len(self._values):
            self._index = index
            self._value = self._values[index]
        else:
            self._index = -1
            self._value = ""
        if self._var is not None:
            self._var.set(self._value)
        self._draw()

    def set_values(self, values: Sequence[str]) -> None:
        if self._open:
            self._close_dropdown()
        self._values = list(values)
        if self._value in self._values:
            self._index = self._values.index(self._value)
        else:
            # Drop stale selection instead of showing a value
            # that can no longer be picked.
            self._index = -1
            self._value = ""
            if self._var is not None:
                self._var.set("")
        self._draw()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self._draw()


class _ComboPopup(tk.Toplevel):
    ROW_HEIGHT = 32
    PADDING = 5
    MAX_ROWS = 9

    def __init__(self, combo: RoundCombo, values: Sequence[str], selected: int,
                 on_pick: Callable[[int], None], on_close: Callable[[], None]):
        super().__init__(combo)
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
            self.attributes("-toolwindow", True)
            self.transient(combo.winfo_toplevel())
        except tk.TclError:
            pass
        self.configure(bg=BORDER)
        self._combo = combo
        self._values = list(values)
        self._selected = selected
        self._on_pick = on_pick
        self._on_close = on_close
        self._font = _font(self, FONT)
        self._width = max(240, combo.winfo_width())
        self._visible = min(max(1, len(self._values)), self.MAX_ROWS)
        self._height = self.PADDING * 2 + self._visible * self.ROW_HEIGHT
        self._offset = 0
        if selected >= 0:
            self._offset = min(
                max(0, selected - self._visible // 2),
                max(0, len(self._values) - self._visible))
        self._highlight = selected if 0 <= selected < len(self._values) else (
            0 if self._values else -1)
        self._closed = False
        self._photos = []
        self._canvas = tk.Canvas(self, bg=BORDER, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Motion>", self._motion)
        self._canvas.bind("<Leave>", lambda _event: self._set_hover(-1))
        self._canvas.bind("<Button-1>", self._click)
        self._canvas.bind("<MouseWheel>", self._wheel)
        self.bind("<Escape>", lambda _event: self._dismiss())
        self.bind("<Down>", self._down)
        self.bind("<Up>", self._up)
        self.bind("<Return>", self._choose)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-1>", self._outside_click, add="+")
        self._draw()
        self._place()
        self.deiconify()
        self.lift()
        self.update_idletasks()
        apply_round_region(self, 10)
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _scroll_width(self) -> int:
        return 10 if len(self._values) > self._visible else 0

    def _draw(self) -> None:
        self._photos = []
        self._canvas.delete("all")
        self._canvas.create_rectangle(
            1, 1, self._width - 1, self._height - 1,
            fill=PANEL, width=0)
        if not self._values:
            self._canvas.create_text(
                self.PADDING + 8, self._height / 2,
                text="Không có lựa chọn", anchor="w", fill=MUTED,
                font=self._font)
            return
        text_width = (self._width - 2 * self.PADDING - 24
                      - self._scroll_width())
        for row in range(self._visible):
            index = self._offset + row
            if index >= len(self._values):
                break
            top = self.PADDING + row * self.ROW_HEIGHT
            if index == self._highlight:
                photo = _round_photo(
                    self, self._width - 8, self.ROW_HEIGHT - 2, 7,
                    PANEL_ACTIVE)
                self._photos.append(photo)
                self._canvas.create_image(
                    4, top + 1, anchor="nw", image=photo)
            label = _truncate(
                self._font, self._values[index], text_width)
            self._canvas.create_text(
                self.PADDING + 8, top + self.ROW_HEIGHT / 2,
                text=label, anchor="w", fill=FG, font=self._font)
            if index == self._selected:
                self._canvas.create_text(
                    self._width - self.PADDING - 10,
                    top + self.ROW_HEIGHT / 2,
                    text="✓", anchor="e", fill=ACCENT, font=self._font)
        if len(self._values) > self._visible:
            x = self._width - 9
            self._canvas.create_line(
                x, self.PADDING + 2, x, self._height - self.PADDING - 2,
                fill=PANEL_ACTIVE, width=3, capstyle="round")
            track = self._height - 2 * self.PADDING - 4
            thumb = max(18, track * self._visible / len(self._values))
            span = max(0, len(self._values) - self._visible)
            progress = self._offset / span if span else 0
            y1 = self.PADDING + 2 + progress * (track - thumb)
            self._canvas.create_line(
                x, y1, x, y1 + thumb, fill=MUTED, width=3,
                capstyle="round")

    def _place(self) -> None:
        x = self._combo.winfo_rootx()
        y = self._combo.winfo_rooty() + self._combo.winfo_height() + 4
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if y + self._height > screen_h - 8:
            y = self._combo.winfo_rooty() - self._height - 4
        x = max(8, min(x, screen_w - self._width - 8))
        y = max(8, min(y, screen_h - self._height - 8))
        self.geometry(f"{self._width}x{self._height}+{int(x)}+{int(y)}")

    def _row_at(self, y: int) -> int:
        local = y - self.PADDING
        if local < 0 or local >= self._visible * self.ROW_HEIGHT:
            return -1
        index = self._offset + local // self.ROW_HEIGHT
        return index if 0 <= index < len(self._values) else -1

    def _set_hover(self, index: int) -> None:
        if index == self._highlight:
            return
        self._highlight = index
        self._draw()

    def _motion(self, event) -> None:
        self._set_hover(self._row_at(event.y))

    def _click(self, event) -> str:
        index = self._row_at(event.y)
        if index >= 0:
            self._on_pick(index)
        else:
            self._dismiss()
        return "break"

    def _outside_click(self, event) -> None:
        if event.widget is not self._canvas:
            self._dismiss()

    def _wheel(self, event) -> str:
        if len(self._values) <= self._visible:
            return "break"
        step = -1 if event.delta > 0 else 1
        self._offset = max(
            0, min(self._offset + step,
                   len(self._values) - self._visible))
        self._draw()
        return "break"

    def _down(self, _event=None) -> str:
        if not self._values:
            return "break"
        self._highlight = min(len(self._values) - 1, self._highlight + 1)
        self._ensure_visible()
        self._draw()
        return "break"

    def _up(self, _event=None) -> str:
        if not self._values:
            return "break"
        self._highlight = max(0, self._highlight - 1)
        self._ensure_visible()
        self._draw()
        return "break"

    def _ensure_visible(self) -> None:
        if self._highlight < self._offset:
            self._offset = self._highlight
        elif self._highlight >= self._offset + self._visible:
            self._offset = self._highlight - self._visible + 1

    def _choose(self, _event=None) -> str:
        if 0 <= self._highlight < len(self._values):
            self._on_pick(self._highlight)
        return "break"

    def _dismiss(self) -> None:
        self.close(notify=True)

    def close(self, notify: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
        if notify:
            try:
                self._on_close()
            except tk.TclError:
                pass


class _RoundedDialog(tk.Toplevel):
    def __init__(self, parent, title: str, width: int = 420,
                 topmost: bool = False):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-toolwindow", True)
            if topmost:
                self.attributes("-topmost", True)
            self.transient(parent)
        except tk.TclError:
            pass
        self.configure(bg=BORDER)
        self._parent = parent
        self._width = width
        self._height = 0
        self._closed = False
        self._drag = None
        self.outer = tk.Frame(self, bg=BORDER)
        self.outer.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.outer, bg=BG)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.header = tk.Frame(self.inner, bg=BG)
        self.header.pack(fill="x", padx=18, pady=(14, 0))
        self.title_label = tk.Label(
            self.header, text=title, bg=BG, fg=FG, font=FONT_TITLE,
            anchor="w")
        self.title_label.pack(side="left")
        self.close_btn = RoundButton(
            self.header, text="×", kind="ghost", height=26, width=28,
            padx=0, bg=BG, font=("Segoe UI", 12), command=self.close)
        self.close_btn.pack(side="right")
        self.header.bind("<ButtonPress-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)
        self.title_label.bind("<ButtonPress-1>", self._drag_start)
        self.title_label.bind("<B1-Motion>", self._drag_move)
        self.bind("<Escape>", lambda _event: self.close())

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(),
                      event.y_root - self.winfo_y())

    def _drag_move(self, event) -> None:
        if self._drag is None:
            return
        dx, dy = self._drag
        self.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _center(self) -> None:
        width = self._width
        height = self._height or self.winfo_height()
        try:
            x = self._parent.winfo_rootx() + (self._parent.winfo_width() - width) // 2
            y = self._parent.winfo_rooty() + (self._parent.winfo_height() - height) // 2
        except tk.TclError:
            x = (self.winfo_screenwidth() - width) // 2
            y = (self.winfo_screenheight() - height) // 2
        x = max(8, min(x, self.winfo_screenwidth() - width - 8))
        y = max(8, min(y, self.winfo_screenheight() - height - 8))
        self.geometry(f"+{x}+{y}")

    def _finish(self, height: int | None = None) -> None:
        self.update_idletasks()
        if height is None:
            height = max(140, self.inner.winfo_reqheight() + 2)
        self._height = height
        self.geometry(f"{self._width}x{height}")
        self.update_idletasks()
        self._center()
        self.update_idletasks()

    def show_modal(self) -> None:
        self.deiconify()
        self.lift()
        self.update_idletasks()
        apply_round_region(self, 14)
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass
        self.wait_window(self)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class MessageDialog(_RoundedDialog):
    def __init__(self, parent, title: str, message: str, kind: str = "info",
                 confirm: bool = False, yes: str = "Tiếp tục",
                 no: str = "Hủy"):
        super().__init__(parent, title, width=420)
        self._confirm = confirm
        self.result = False
        body = tk.Frame(self.inner, bg=BG)
        body.pack(fill="x", padx=18, pady=(14, 0))
        icon = tk.Canvas(body, width=26, height=26, bg=BG,
                         highlightthickness=0)
        icon.pack(side="left", anchor="n", pady=(1, 0))
        colors = {
            "info": (ACCENT, "i"),
            "question": (ACCENT, "?"),
            "warning": (WARN, "!"),
            "error": (DANGER, "×"),
        }
        color, glyph = colors.get(kind, colors["info"])
        icon.create_oval(1, 1, 25, 25, fill=color, width=0)
        icon.create_text(13, 13, text=glyph, fill=WHITE,
                         font=("Segoe UI Semibold", 11))
        label = tk.Label(
            body, text=message, bg=BG, fg=FG, justify="left", anchor="w",
            wraplength=330, font=FONT)
        label.pack(side="left", fill="x", expand=True, padx=(10, 0))
        footer = tk.Frame(self.inner, bg=BG)
        footer.pack(fill="x", padx=18, pady=(18, 16))
        if confirm:
            yes_btn = RoundButton(
                footer, text=yes, kind="primary", height=34, padx=16,
                bg=BG, font=FONT_SEMIBOLD, command=self._accept)
            yes_btn.pack(side="right")
            no_btn = RoundButton(
                footer, text=no, kind="secondary", height=34, padx=16,
                bg=BG, font=FONT_SEMIBOLD, command=self.close)
            no_btn.pack(side="right", padx=(0, 8))
        else:
            close_btn = RoundButton(
                footer, text="Đóng", kind="secondary", height=34, padx=16,
                bg=BG, font=FONT_SEMIBOLD, command=self.close)
            close_btn.pack(side="right")
        self._finish()

    def _accept(self) -> None:
        self.result = True
        self.close()


class SlimScrollbar(tk.Canvas):
    def __init__(self, master, command, bg: str = BG):
        self._command = command
        self._first = 0.0
        self._last = 1.0
        self._drag = None
        super().__init__(master, width=7, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first, last) -> None:
        self._first = float(first)
        self._last = float(last)
        self._draw()

    def _draw(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("all")
        x = width / 2
        self.create_line(x, 2, x, height - 2, fill=PANEL, width=3,
                         capstyle="round")
        top = max(2, int(height * self._first))
        bottom = min(height - 2, int(height * self._last))
        if bottom - top < 16:
            top = max(2, min(top, height - 18))
            bottom = min(height - 2, top + 16)
        self.create_line(x, top, x, bottom, fill=MUTED, width=3,
                         capstyle="round")

    def _press(self, event) -> None:
        self._drag = (event.y, self._first)
        self._jump(event.y)

    def _jump(self, y: int) -> None:
        height = max(1, self.winfo_height())
        fraction = max(0.0, min(1.0, y / height))
        span = max(0.0, self._last - self._first)
        self._command("moveto", max(0.0, min(1.0 - span, fraction - span / 2)))

    def _drag_move(self, event) -> None:
        if self._drag is None:
            return
        start_y, start_first = self._drag
        height = max(1, self.winfo_height())
        span = max(0.0, self._last - self._first)
        target = start_first + (event.y - start_y) / height
        self._command("moveto", max(0.0, min(1.0 - span, target)))

    def _release(self, _event=None) -> None:
        self._drag = None


class HelpDialog(_RoundedDialog):
    def __init__(self, parent, text: str, title: str = "Hướng dẫn sử dụng",
                 topmost: bool = False):
        super().__init__(parent, title, width=460, topmost=topmost)
        height = min(600, max(420, self.winfo_screenheight() - 120))
        body = tk.Frame(self.inner, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(12, 0))
        self.scrollbar = SlimScrollbar(body, lambda *args: self._text.yview(*args))
        self.scrollbar.pack(side="right", fill="y", padx=(8, 0))
        self._text = tk.Text(
            body, bg=BG, fg=FG, bd=0, highlightthickness=0, wrap="word",
            padx=0, pady=0, font=FONT, insertbackground=BG,
            selectbackground=PANEL_ACTIVE, selectforeground=FG,
            cursor="arrow", spacing1=1, spacing2=2, spacing3=6,
            yscrollcommand=self.scrollbar.set)
        self._text.pack(side="left", fill="both", expand=True)
        self._text.tag_configure("heading", font=("Segoe UI Semibold", 10),
                                 foreground=FG, spacing1=4, spacing3=8)
        self._text.tag_configure("step", foreground=FG, spacing1=5)
        self._text.tag_configure("note", foreground=MUTED, spacing1=6)
        for line in text.splitlines():
            stripped = line.rstrip()
            if not stripped:
                self._text.insert("end", "\n")
                continue
            if stripped.startswith(("Cách dùng", "Lưu ý", "Cả RNNoise")):
                tag = "heading" if stripped.startswith(("Cách dùng", "Lưu ý")) else "note"
            elif re.match(r"^\d+\.", stripped):
                tag = "step"
            elif stripped.startswith(("Thanh nhỏ", "Bấm X", "Thoát")):
                tag = "note"
            else:
                tag = ""
            self._text.insert("end", stripped + "\n", tag)
        self._text.configure(state="disabled")
        self.bind("<MouseWheel>", self._wheel)
        self._text.bind("<MouseWheel>", self._wheel)
        body.bind("<MouseWheel>", self._wheel)
        self.scrollbar.bind("<MouseWheel>", self._wheel)
        footer = tk.Frame(self.inner, bg=BG)
        footer.pack(fill="x", padx=18, pady=(14, 16))
        close_btn = RoundButton(
            footer, text="Đóng", kind="primary", height=34, padx=18,
            bg=BG, font=FONT_SEMIBOLD, command=self.close)
        close_btn.pack(side="right")
        self._finish(height)

    def _wheel(self, event) -> str:
        self._text.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"


def show_message(parent, title: str, message: str, kind: str = "info",
                 confirm: bool = False, yes: str = "Tiếp tục",
                 no: str = "Hủy") -> bool:
    dialog = MessageDialog(parent, title, message, kind, confirm, yes, no)
    dialog.show_modal()
    return dialog.result


def show_info(parent, title: str, message: str) -> None:
    show_message(parent, title, message, kind="info")


def show_warning(parent, title: str, message: str) -> None:
    show_message(parent, title, message, kind="warning")


def show_error(parent, title: str, message: str) -> None:
    show_message(parent, title, message, kind="error")


def ask_yes_no(parent, title: str, message: str, yes: str = "Tiếp tục",
               no: str = "Hủy") -> bool:
    return show_message(parent, title, message, kind="question",
                        confirm=True, yes=yes, no=no)


def show_help(parent, text: str, topmost: bool = False) -> None:
    dialog = HelpDialog(parent, text, topmost=topmost)
    dialog.show_modal()
