"""Minimal tkinter UI with a system-tray icon for noise-cut."""

import os
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image

from . import config
from . import dfn3
from . import engine as eng
from . import hotkey
from . import ui
from . import vbcable
from .mini import MiniBar
from .toast import Toast

APP_TITLE = "Noise Cut"
DENOISER_CHOICES = (
    ("rnnoise", "RNNoise (nhẹ, ổn định)"),
    ("dfn3", "DFN3 (chất lượng cao, +30 ms)"),
)
BG = "#1e1f22"
CARD = "#25272c"
BORDER = "#36393f"
FG = "#f2f3f5"
MUTED = "#9aa0a6"
ACCENT = "#3ba55d"
ACCENT_ACTIVE = "#2f8a4a"
PANEL = "#2b2d31"
PANEL_ACTIVE = "#3a3d42"
DANGER = "#a33333"
WARN = "#e0a33a"
TRAY_COLORS = {
    "running": (59, 165, 93, 255),
    "muted": (224, 163, 58, 255),
    "error": (224, 90, 90, 255),
    "stopped": (154, 160, 166, 255),
}
WINDOW_WIDTH = 420
PAD = 18

HELP_TEXT = (
    "Cách dùng với Google Meet / Zoom / Teams:\n\n"
    "1. Bấm nút 'Cài mic ảo (VB-Cable)' trong app để cài mic ảo.\n"
    "   Cần quyền admin (UAC) và khởi động lại Windows 1 lần.\n"
    "   VB-CABLE là donationware của VB-Audio: www.vb-cable.com\n"
    "   (Có thể cài thủ công từ https://vb-audio.com/Cable/ nếu muốn.)\n\n"
    "2. Trong Noise Cut chọn:\n"
    "   - Micro: mic thật của bạn\n"
    "   - Đầu ra: CABLE Input (VB-Audio Virtual Cable)\n\n"
    "3. App tự bật lọc khi mở (nếu đã có VB-Cable). Nếu chưa,\n"
    "   bấm Bắt đầu sau khi chọn thiết bị.\n"
    "   Bộ lọc RNNoise nhẹ và ổn định; DFN3 lọc mạnh hơn nhưng\n"
    "   trễ thêm ~30 ms và vẫn có thể lọt tiếng người xung quanh.\n\n"
    "4. Trong Meet/Zoom/Teams chọn micro là\n"
    "   'CABLE Output (VB-Audio Virtual Cable)'.\n\n"
    "5. Tắt khử ồn có sẵn của Meet/Zoom/Teams để tránh lọc 2 lần.\n\n"
    "6. Khi ho/hắt xì: BẤM Ctrl+Shift+? (phím /) để bật/tắt tiếng.\n"
    "   Cũng có thể bấm nút 'BẤM ĐỂ TẮT TIẾNG' trên cửa sổ chính\n"
    "   hoặc thanh nhỏ luôn nổi.\n\n"
    "Thanh nhỏ luôn nổi có thể kéo bằng chuột; ẩn/hiện trong menu tray.\n"
    "Bấm X để thu nhỏ xuống khay hệ thống — thanh nhỏ và bộ lọc vẫn chạy.\n"
    "Thoát hẳn bằng menu chuột phải trên biểu tượng khay."
)

INSTALL_CONFIRM = (
    "Ứng dụng sẽ cài VB-CABLE (mic ảo) — donationware của VB-Audio.\n\n"
    "Nguồn: www.vb-cable.com\n"
    "VB-CABLE is a donationware, all participations are welcome.\n\n"
    "Cần quyền quản trị (hộp thoại UAC) và khởi động lại Windows\n"
    "sau khi cài. Tiếp tục?"
)


def _mix_quality(value: float) -> str:
    if value >= 90:
        return "Tối đa"
    if value >= 60:
        return "Mạnh"
    if value >= 30:
        return "Vừa"
    if value > 0:
        return "Nhẹ"
    return "Không lọc"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.engine: eng.AudioEngine | None = None
        self.config = config.load()
        self.inputs = eng.list_input_devices()
        self.outputs = eng.list_output_devices()
        self._closed = False
        self._hidden = False
        self._tray = None
        self._tray_state_cur: str | None = None
        self._toast: Toast | None = None
        self._cable_pending_reboot = False
        self._installing = False
        self._muted = False
        self._mini: MiniBar | None = None
        self._mini_visible = bool(self.config.get("mini_visible", True))
        self._dfn3_available = dfn3.available()
        self._hotkey = hotkey.MuteHotkey(self._on_hotkey_mute)
        self._aec_busy = False
        self._ui_ready = False
        self._disp_in = 0.0
        self._disp_out = 0.0
        self._notice_text = ""
        self._notice_tone = "info"

        root.title(APP_TITLE)
        try:
            root.iconbitmap(default=config.resource_path("assets", "icon.ico"))
        except tk.TclError:
            pass
        root.configure(bg=BG)
        ui.apply_dark_titlebar(root)
        root.geometry(f"{WINDOW_WIDTH}x600")
        root.minsize(WINDOW_WIDTH, 480)
        root.resizable(False, False)

        self._build_style()
        self._build_widgets()
        self._preselect()
        self._update_cable_ui()
        self._update_power_ui()
        self._update_mute_ui()
        self._ui_ready = True
        self._fit_window()
        self.root.after_idle(self._fit_window)
        self.root.after(100, self._fit_window)
        self._setup_tray()
        self._setup_hotkey()
        self._setup_mini()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(60, self._tick)
        root.after(350, self._maybe_autostart)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Hint.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 8))
        style.configure("Notice.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Warn.TLabel", background=BG, foreground=WARN,
                        font=("Segoe UI", 9))
        style.configure("Error.TLabel", background=BG, foreground="#e06c6c",
                        font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI Semibold", 9))
        style.configure("Value.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI Semibold", 9))
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI Semibold", 16))
        style.configure("Link.TButton", background=BG, foreground=MUTED,
                        borderwidth=0, padding=(6, 4), font=("Segoe UI", 9))
        style.map("Link.TButton",
                  background=[("active", BG), ("pressed", BG)],
                  foreground=[("active", FG)])
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=FG, arrowcolor=FG, padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", FG)],
                  background=[("readonly", PANEL)])
        style.configure("TButton", background=PANEL, foreground=FG,
                        borderwidth=0, padding=6, font=("Segoe UI", 9))
        style.map("TButton", background=[("active", PANEL_ACTIVE)])
        style.configure("Primary.TButton", background=ACCENT, foreground="white",
                        borderwidth=0, padding=(12, 11),
                        font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton",
                  background=[("active", ACCENT_ACTIVE), ("pressed", ACCENT_ACTIVE)])
        style.configure("Secondary.TButton", background=PANEL, foreground=FG,
                        borderwidth=0, padding=(12, 11),
                        font=("Segoe UI Semibold", 10))
        style.map("Secondary.TButton",
                  background=[("active", PANEL_ACTIVE), ("pressed", PANEL_ACTIVE)])
        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)
        style.configure("TCheckbutton", background=BG, foreground=FG,
                        font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("active", FG)])

    def _build_widgets(self) -> None:
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=PAD, pady=(16, 0))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ui.RoundButton(header, text="Hướng dẫn", kind="ghost", height=28,
                       padx=10, bg=BG, command=self.show_help).pack(side="right")

        self.hero = ui.RoundedCard(self.root, bg=BG, fill=CARD,
                                   outline=BORDER, radius=14, padding=14)
        self.hero.pack(fill="x", padx=PAD, pady=(12, 0))
        hero_body = tk.Frame(self.hero.body, bg=CARD)
        hero_body.pack(fill="x", padx=2)

        state_row = tk.Frame(hero_body, bg=CARD)
        state_row.pack(fill="x")
        self.state_dot = tk.Canvas(state_row, width=10, height=10, bg=CARD,
                                   highlightthickness=0)
        self.state_dot.pack(side="left", pady=(4, 0))
        self.state_dot_id = self.state_dot.create_oval(
            1, 1, 9, 9, fill=MUTED, width=0)
        self.state_label = tk.Label(state_row, text="", bg=CARD, fg=FG,
                                    font=("Segoe UI Semibold", 13), anchor="w")
        self.state_label.pack(side="left", padx=(8, 0))
        self.state_sub = tk.Label(hero_body, text="", bg=CARD, fg=MUTED,
                                  font=("Segoe UI", 9), anchor="w")
        self.state_sub.pack(fill="x", pady=(2, 0))
        self.toggle_btn = ui.RoundButton(
            hero_body, text="BẬT KHỬ ỒN", kind="secondary", height=42,
            bg=CARD, command=self.toggle)
        self.toggle_btn.pack(fill="x", pady=(12, 0))

        levels = ttk.Frame(self.root)
        levels.pack(fill="x", padx=PAD, pady=(10, 0))
        self.in_canvas = self._level_row(levels, "Vào")
        self.out_canvas = self._level_row(levels, "Ra")

        devices = ttk.Frame(self.root)
        devices.pack(fill="x", padx=PAD, pady=(14, 0))
        dev_head = ttk.Frame(devices)
        dev_head.pack(fill="x")
        ttk.Label(dev_head, text="THIẾT BỊ", style="Section.TLabel").pack(side="left")
        ui.RoundButton(dev_head, text="Làm mới", kind="ghost", height=28,
                       padx=10, bg=BG,
                       command=self.refresh_devices).pack(side="right")

        form = ttk.Frame(devices)
        form.pack(fill="x", pady=(4, 0))
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Micro", style="Muted.TLabel", width=6,
                  anchor="w").grid(row=0, column=0, sticky="w", pady=2)
        self.input_var = tk.StringVar()
        self.input_box = ui.RoundCombo(
            form, values=[n for _, n in self.inputs],
            textvariable=self.input_var, placeholder="Chọn micro",
            width=260, height=34, bg=BG)
        self.input_box.grid(row=0, column=1, sticky="we", pady=2)
        ttk.Label(form, text="Đầu ra", style="Muted.TLabel", width=6,
                  anchor="w").grid(row=1, column=0, sticky="w", pady=2)
        self.output_box = ui.RoundCombo(
            form, values=[n for _, n in self.outputs],
            placeholder="Chọn đầu ra", width=260, height=34, bg=BG)
        self.output_box.grid(row=1, column=1, sticky="we", pady=2)
        self.input_box.bind("<<ComboboxSelected>>", self._on_device_change)
        self.output_box.bind("<<ComboboxSelected>>", self._on_device_change)

        self.install_btn = ui.RoundButton(
            devices, text="Cài mic ảo (VB-Cable)", kind="secondary", height=38,
            bg=BG, command=self.on_install_cable)

        strength = ttk.Frame(self.root)
        strength.pack(fill="x", padx=PAD, pady=(14, 0))
        strength_head = ttk.Frame(strength)
        strength_head.pack(fill="x")
        ttk.Label(strength_head, text="MỨC KHỬ TIẾNG ỒN",
                  style="Section.TLabel").pack(side="left")
        self.mix_value_label = ttk.Label(strength_head, text="",
                                          style="Value.TLabel")
        self.mix_value_label.pack(side="right")
        self.mix_var = tk.DoubleVar(value=float(self.config.get("mix", 100.0)))
        self.mix_scale = ui.RoundScale(strength, self.mix_var, 0, 100,
                                       command=self.on_mix_change, bg=BG)
        self.mix_scale.pack(fill="x", pady=(6, 0))
        mix_ends = ttk.Frame(strength)
        mix_ends.pack(fill="x")
        ttk.Label(mix_ends, text="Nhẹ", style="Hint.TLabel").pack(side="left")
        ttk.Label(mix_ends, text="Mạnh", style="Hint.TLabel").pack(side="right")
        self.mix_value_label.configure(text=self._mix_caption(self.mix_var.get()))

        self.options = ttk.Frame(self.root)
        self.options.pack(fill="x", padx=PAD, pady=(14, 0))
        self._build_options(self.options)

        self.footer_sep = tk.Frame(self.root, bg=BORDER, height=1)
        self.footer_sep.pack(fill="x", padx=PAD, pady=(12, 0))
        self.notice = ttk.Label(self.root, text="", style="Notice.TLabel",
                                anchor="w", justify="left",
                                wraplength=WINDOW_WIDTH - 2 * PAD)
        self.status = ttk.Label(self.root, text="", style="Muted.TLabel",
                                anchor="w", justify="left",
                                wraplength=WINDOW_WIDTH - 2 * PAD)
        self.status.pack(fill="x", padx=PAD, pady=(8, 14))

    def _build_options(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="BỘ LỌC & KHỬ VỌNG",
                  style="Section.TLabel").pack(anchor="w")
        model = ttk.Frame(parent)
        model.pack(fill="x", pady=(4, 0))
        model.columnconfigure(1, weight=1)
        ttk.Label(model, text="Bộ lọc", style="Muted.TLabel", width=6,
                  anchor="w").grid(row=0, column=0, sticky="w")
        choices = [label for _, label in DENOISER_CHOICES
                   if self._dfn3_available or label.startswith("RNNoise")]
        self.denoiser_var = tk.StringVar()
        self.denoiser_box = ui.RoundCombo(
            model, values=choices, textvariable=self.denoiser_var,
            placeholder="Chọn bộ lọc", width=260, height=34, bg=BG)
        self.denoiser_box.grid(row=0, column=1, sticky="we")
        selected = str(self.config.get("denoiser", "rnnoise"))
        if selected == "dfn3" and not self._dfn3_available:
            selected = "rnnoise"
            self.config["denoiser"] = selected
            config.save(self.config)
        label = next((text for key, text in DENOISER_CHOICES if key == selected),
                     DENOISER_CHOICES[0][1])
        if label in choices:
            self.denoiser_box.set(label)
        else:
            self.denoiser_box.current(0)
        self.denoiser_box.bind("<<ComboboxSelected>>", self.on_denoiser_change)

        self.aec_var = tk.BooleanVar(value=bool(self.config.get("aec", True)))
        self.aec_check = ui.RoundCheck(
            model, text="Khử vọng loa (AEC)", variable=self.aec_var,
            bg=BG, command=self.on_aec_toggle)
        self.aec_check.grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            model,
            text="Giảm tiếng vọng khi dùng loa ngoài; đeo tai nghe vẫn tốt hơn.",
            style="Hint.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        mute = ttk.Frame(parent)
        mute.pack(fill="x", pady=(14, 0))
        mute_head = ttk.Frame(mute)
        mute_head.pack(fill="x")
        ttk.Label(mute_head, text="TẮT TIẾNG NHANH",
                  style="Section.TLabel").pack(side="left")
        toggle = bool(self.config.get("mute_toggle", True))
        self.mute_toggle_var = tk.BooleanVar(value=toggle)
        ui.RoundCheck(mute_head, text="Bấm để bật tắt",
                      variable=self.mute_toggle_var, bg=BG,
                      command=self.on_mute_toggle_change).pack(side="right")
        self.hotkey_label = ttk.Label(
            mute,
            text="Ctrl+Shift+? (bấm để bật tắt)" if toggle else hotkey.LABEL,
            style="Muted.TLabel")
        self.hotkey_label.pack(anchor="w", pady=(4, 0))
        self.mute_hold_btn = ui.RoundButton(
            mute, kind="secondary", height=42, bg=BG,
            command=self._on_hold_key,
            on_press=self._on_hold_press, on_release=self._on_hold_release)
        self.mute_hold_btn.pack(fill="x", pady=(6, 0))

        self.autorun_var = tk.BooleanVar(value=config.autorun_enabled())
        ui.RoundCheck(parent, text="Tự chạy cùng Windows",
                      variable=self.autorun_var, bg=BG,
                      command=self.on_autorun_toggle).pack(anchor="w", pady=(12, 0))

    def _level_row(self, parent: ttk.Frame, label: str) -> tk.Canvas:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=BG, fg=MUTED, width=4, anchor="w",
                 font=("Segoe UI", 8)).pack(side="left")
        canvas = tk.Canvas(row, height=6, bg=BG, highlightthickness=0)
        canvas.pack(side="left", fill="x", expand=True, padx=(4, 0))
        return canvas

    def _mix_caption(self, value: float) -> str:
        return f"{value:.0f}%  ·  {_mix_quality(value)}"

    def _device_summary(self) -> str:
        src = self.input_box.get().strip()
        dst = self.output_box.get().strip()
        if src and dst:
            return f"{src}  →  {dst}"
        if src:
            return src
        if dst:
            return f"→  {dst}"
        return "Chưa chọn thiết bị."

    def _refresh_status(self) -> None:
        text = self._device_summary()
        if self.status.cget("text") == text:
            return
        self.status.configure(text=text)
        if self._ui_ready:
            self.root.after_idle(self._fit_window)

    def _set_notice(self, text: str, tone: str = "info") -> None:
        text = text.strip()
        if text == self._notice_text and tone == self._notice_tone:
            return
        self._notice_text = text
        self._notice_tone = tone
        if text:
            style = {"warn": "Warn.TLabel", "error": "Error.TLabel"}.get(
                tone, "Notice.TLabel")
            self.notice.configure(text=text, style=style)
            if not self.notice.winfo_manager():
                self.notice.pack(fill="x", padx=PAD, pady=(8, 0),
                                 before=self.status)
        elif self.notice.winfo_manager():
            self.notice.pack_forget()
        if self._ui_ready:
            self.root.after_idle(self._fit_window)

    def _on_device_change(self, _event=None) -> None:
        self._refresh_status()

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
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _fit_window(self) -> None:
        if not self._ui_ready:
            return
        self.root.update_idletasks()
        height = max(400, self.root.winfo_reqheight())
        _, _, _, area_h = self._work_area()
        height = min(height, area_h - 16)
        self.root.geometry(f"{WINDOW_WIDTH}x{height}")

    def _icon_image(self, state: str = "stopped") -> Image.Image:
        path = config.resource_path("assets", "icon.ico")
        try:
            image = Image.open(path).convert("RGBA")
        except Exception:
            image = Image.new("RGBA", (64, 64), (30, 31, 34, 255))
        color = TRAY_COLORS.get(state, TRAY_COLORS["stopped"])
        try:
            pixels = image.load()
            for y in range(image.height):
                for x in range(image.width):
                    r, g, b, a = pixels[x, y]
                    if a and g > 80 and g > r + 30 and g > b + 20:
                        pixels[x, y] = (color[0], color[1], color[2], a)
        except Exception:
            pass
        try:
            from PIL import ImageDraw

            size = min(image.size)
            center = int(size * 0.78)
            outer = int(size * 0.20)
            inner = int(size * 0.15)
            draw = ImageDraw.Draw(image)
            draw.ellipse((center - outer, center - outer,
                          center + outer, center + outer),
                         fill=(30, 31, 34, 255))
            draw.ellipse((center - inner, center - inner,
                          center + inner, center + inner), fill=color)
        except Exception:
            pass
        return image

    def _setup_tray(self) -> None:
        try:
            import pystray
        except Exception:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Mở Noise Cut", self._tray_show, default=True),
            pystray.MenuItem("Bật/Tắt lọc", self._tray_toggle),
            pystray.MenuItem("Tắt tiếng", self._tray_mute,
                             checked=lambda _item: self._muted),
            pystray.MenuItem("Hiện/Ẩn thanh nhỏ", self._tray_mini,
                             checked=lambda _item: self._mini_visible),
            pystray.MenuItem("Cài mic ảo (VB-Cable)", self._tray_install,
                             enabled=lambda _item: not vbcable.installed()
                             and not self._cable_pending_reboot
                             and not self._installing),
            pystray.MenuItem("Tự chạy cùng Windows", self._tray_autorun,
                             checked=lambda _item: config.autorun_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Thoát", self._tray_quit),
        )
        try:
            self._tray = pystray.Icon(APP_TITLE, self._icon_image(), APP_TITLE, menu)
            self._tray.run_detached()
        except Exception:
            self._tray = None

    def _tray_show(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._show_window)

    def _tray_toggle(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._tray_toggle_shown)

    def _tray_toggle_shown(self) -> None:
        # dialogs need a visible parent; window may be hidden in tray
        self._show_window()
        self.toggle()

    def _tray_mute(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._tray_mute_shown)

    def _tray_mute_shown(self) -> None:
        self._show_window()
        self.set_muted(not self._muted)

    def _tray_mini(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._toggle_mini)

    def _tray_install(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._tray_install_shown)

    def _tray_install_shown(self) -> None:
        self._show_window()
        self.on_install_cable()

    def _tray_autorun(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._toggle_autorun)

    def _tray_quit(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.quit)

    def _show_window(self) -> None:
        if self._toast is not None:
            try:
                self._toast.dismiss()
            except tk.TclError:
                pass
        self._hidden = False
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(120, lambda: self.root.attributes("-topmost", False))
        if self._mini is not None:
            self._mini.lift()

    def _preselect(self) -> None:
        stored_in = self.config.get("input") or ""
        stored_out = self.config.get("output") or ""
        self._select_by_name(self.input_box, self.inputs, stored_in)

        cable = eng.find_cable_input()
        if cable is not None:
            self._select_by_name(self.output_box, self.outputs, stored_out)
            if "cable input" not in self.output_box.get().lower():
                self._select_by_name(self.output_box, self.outputs, cable[1])
            self._set_notice("Sẵn sàng — đã tìm thấy VB-Cable.")
        else:
            self._select_by_name(self.output_box, self.outputs, stored_out)
            self._set_notice(
                "Chưa có VB-Cable — bấm Hướng dẫn để xem cách cài.",
                tone="warn")

        if not self.input_box.get():
            default_in = eng.default_input()
            if default_in is not None:
                for i, (idx, _) in enumerate(self.inputs):
                    if idx == default_in:
                        self.input_box.current(i)
                        break
        if not self.input_box.get() and self.inputs:
            self.input_box.current(0)
        if not self.output_box.get() and self.outputs:
            self.output_box.current(0)
        self._refresh_status()

    def _select_by_name(self, box: ui.RoundCombo, devices, name: str) -> None:
        for i, (_, dev_name) in enumerate(devices):
            if dev_name == name:
                box.current(i)
                return

    def on_mix_change(self, _value=None) -> None:
        value = self.mix_var.get()
        self.mix_value_label.configure(text=self._mix_caption(value))
        if self.engine is not None:
            self.engine.set_mix(value / 100.0)
        self._update_power_ui()

    def _selected_denoiser(self) -> str:
        label = self.denoiser_box.get()
        for key, text in DENOISER_CHOICES:
            if text == label:
                return key
        return "rnnoise"

    def on_denoiser_change(self, _event=None) -> None:
        value = self._selected_denoiser()
        self.config["denoiser"] = value
        config.save(self.config)
        if self.engine is not None and self.engine.running:
            self.stop()
            self.start(quiet=True)
        self._update_power_ui()
        self._refresh_tray_menu()

    def on_aec_toggle(self) -> None:
        enabled = bool(self.aec_var.get())
        self.config["aec"] = enabled
        config.save(self.config)
        engine = self.engine
        if engine is None or not engine.running or self._aec_busy:
            self._update_power_ui()
            self._refresh_tray_menu()
            return
        self._aec_busy = True
        self.aec_check.set_enabled(False)
        self._set_notice("Đang bật khử vọng..." if enabled
                         else "Đang tắt khử vọng...")

        def work() -> None:
            engine.set_aec(enabled)
            try:
                self.root.after(0, lambda: self._aec_toggle_done(engine, enabled))
            except tk.TclError:
                pass

        threading.Thread(target=work, name="noisecut-aec-toggle",
                         daemon=True).start()

    def _aec_toggle_done(self, engine, enabled: bool) -> None:
        self._aec_busy = False
        try:
            self.aec_check.set_enabled(True)
        except tk.TclError:
            return
        if self.engine is not engine:
            return
        if engine.aec_error:
            self._set_notice(engine.aec_error, tone="warn")
        else:
            self._set_notice("Đã bật khử vọng." if enabled
                             else "Đã tắt khử vọng.")
        self._update_power_ui()
        self._refresh_tray_menu()

    def on_autorun_toggle(self) -> None:
        wanted = self.autorun_var.get()
        if config.set_autorun(wanted):
            self._set_notice(
                "Đã bật tự chạy cùng Windows." if wanted
                else "Đã tắt tự chạy cùng Windows.")
        else:
            self.autorun_var.set(not wanted)
            self._set_notice("Không ghi được đăng ký tự chạy.", tone="error")
        self._refresh_tray_menu()

    def _toggle_autorun(self) -> None:
        self.autorun_var.set(not config.autorun_enabled())
        self.on_autorun_toggle()

    # ---- instant mute (cough button) ----

    def _setup_hotkey(self) -> None:
        toggle = bool(self.config.get("mute_toggle", True))
        self.mute_toggle_var.set(toggle)
        self._hotkey.configure(toggle)
        self._hotkey.sync(self._muted)
        if not self._hotkey.start():
            self._set_notice(
                "Không bật được phím tắt Ctrl+Shift+/? (thiếu pynput).",
                tone="warn")

    def on_mute_toggle_change(self) -> None:
        toggle = bool(self.mute_toggle_var.get())
        self.config["mute_toggle"] = toggle
        config.save(self.config)
        self.hotkey_label.configure(
            text="Ctrl+Shift+? (bấm để bật tắt)" if toggle else hotkey.LABEL)
        self._hotkey.configure(toggle)
        self._hotkey.sync(self._muted)
        if not self._hotkey.start():
            self._set_notice(
                "Không bật được phím tắt Ctrl+Shift+/? (thiếu pynput).",
                tone="warn")
        if self._mini is not None:
            self._mini.set_toggle_mode(toggle)
        self._update_mute_ui()

    def _setup_mini(self) -> None:
        self._mini = MiniBar(
            self.root,
            on_mute_press=self._on_hold_press,
            on_mute_release=self._on_hold_release,
            on_help=self._mini_help,
            on_open=self._show_window,
            on_position=self._save_mini_position,
        )
        x = self.config.get("mini_x")
        y = self.config.get("mini_y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            self._mini.place_at(int(x), int(y))
        else:
            self._mini.place_at(*self._mini.default_position())
        self._mini.set_toggle_mode(bool(self.mute_toggle_var.get()))
        self._mini.set_muted(self._muted)
        self._mini.set_running(self.engine is not None and self.engine.running)
        self._mini.set_visible(self._mini_visible)
        self._refresh_tray_menu()

    def _mini_help(self) -> None:
        ui.show_help(self._mini, HELP_TEXT, topmost=True)

    def _save_mini_position(self, x: int, y: int) -> None:
        self.config["mini_x"] = int(x)
        self.config["mini_y"] = int(y)
        config.save(self.config)

    def _toggle_mini(self) -> None:
        self._mini_visible = not self._mini_visible
        self.config["mini_visible"] = self._mini_visible
        config.save(self.config)
        if self._mini is not None:
            self._mini.set_visible(self._mini_visible)
        self._refresh_tray_menu()

    def _on_hotkey_mute(self, muted: bool) -> None:
        self.set_muted(muted)
    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._hotkey is not None:
            self._hotkey.sync(self._muted)
        if self.engine is not None:
            self.engine.muted = self._muted
        if self._closed:
            return
        try:
            self.root.after(0, self._update_mute_ui)
        except tk.TclError:
            pass

    def _on_hold_press(self, _event=None) -> None:
        if self.mute_toggle_var.get():
            self.set_muted(not self._muted)
        else:
            self.set_muted(True)

    def _on_hold_release(self, _event=None) -> None:
        if not self.mute_toggle_var.get():
            self.set_muted(False)

    def _on_hold_key(self) -> None:
        # Keyboard activation (Enter/Space): single toggle in both modes,
        # since a momentary hold is not expressible via keyboard.
        self.set_muted(not self._muted)

    def _update_mute_ui(self) -> None:
        if self._muted:
            if self.mute_toggle_var.get():
                self.mute_hold_btn.set_text("ĐANG TẮT TIẾNG — bấm để mở")
            else:
                self.mute_hold_btn.set_text("ĐANG TẮT TIẾNG — thả ra để mở")
            self.mute_hold_btn.set_kind("danger")
        else:
            self.mute_hold_btn.set_text(
                "BẤM ĐỂ TẮT TIẾNG" if self.mute_toggle_var.get()
                else "GIỮ ĐỂ TẮT TIẾNG")
            self.mute_hold_btn.set_kind("secondary")
        self._update_power_ui()
        if self._mini is not None:
            self._mini.set_muted(self._muted)
        self._refresh_tray_menu()

    def _tray_state(self) -> tuple[str, str]:
        if self.engine is not None and self.engine.running:
            if self.engine.error:
                return "error", "Noise Cut — Bộ lọc gặp lỗi"
            if self._muted:
                return "muted", "Noise Cut — Đang tắt tiếng"
            return "running", "Noise Cut — Đang hoạt động"
        return "stopped", "Noise Cut — Đã dừng"

    def _refresh_tray_menu(self) -> None:
        if self._tray is None:
            return
        state, title = self._tray_state()
        try:
            self._tray.update_menu()
            if state != self._tray_state_cur:
                self._tray.icon = self._icon_image(state)
                self._tray.title = title
                self._tray_state_cur = state
        except Exception:
            pass

    def _update_cable_ui(self) -> None:
        if vbcable.installed():
            if self.install_btn.winfo_manager():
                self.install_btn.pack_forget()
        else:
            if self._installing:
                self.install_btn.set_enabled(False)
                self.install_btn.set_text("Đang cài VB-Cable...")
            elif self._cable_pending_reboot:
                self.install_btn.set_enabled(False)
                self.install_btn.set_text("Đã cài — cần khởi động lại Windows")
            else:
                self.install_btn.set_enabled(True)
                self.install_btn.set_text("Cài mic ảo (VB-Cable)")
            if not self.install_btn.winfo_manager():
                self.install_btn.pack(fill="x", pady=(8, 0))
        self._fit_window()
        self._refresh_tray_menu()

    def on_install_cable(self) -> None:
        if self._installing:
            return
        if vbcable.installed():
            self._update_cable_ui()
            return
        if not ui.ask_yes_no(self.root, APP_TITLE, INSTALL_CONFIRM):
            return
        self._installing = True
        self.install_btn.set_enabled(False)
        self.install_btn.set_text("Đang cài VB-Cable...")
        self._set_notice("Đang cài VB-Cable — bấm Yes ở hộp thoại UAC.")
        self._refresh_tray_menu()
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self) -> None:
        ok, message = vbcable.install()
        if self._closed:
            return
        try:
            self.root.after(0, lambda: self._install_finished(ok, message))
        except Exception:
            # UI gone or loop not running: release the lock so a retry is possible.
            self._installing = False

    def _install_finished(self, ok: bool, message: str) -> None:
        self._installing = False
        if self._closed:
            return
        if ok:
            self._cable_pending_reboot = True
        else:
            self.install_btn.set_enabled(True)
            self.install_btn.set_text("Cài mic ảo (VB-Cable)")
        self.refresh_devices()
        self._show_window()
        if ok:
            ui.show_info(
                self.root,
                APP_TITLE,
                "Đã cài VB-CABLE.\n\n"
                "Hãy khởi động lại Windows để hoàn tất.\n"
                "Sau khi khởi động lại, mở Noise Cut — ứng dụng sẽ tự nhận\n"
                "mic ảo và tự bật lọc.\n\n"
                "VB-CABLE là donationware của VB-Audio (www.vb-cable.com).",
            )
            self._set_notice(
                "Đã cài VB-CABLE — cần khởi động lại Windows.", tone="warn")
        else:
            ui.show_error(self.root, APP_TITLE, message or "Cài đặt thất bại.")
            self._set_notice("Cài VB-Cable thất bại.", tone="error")
        self._update_cable_ui()

    def refresh_devices(self) -> None:
        prev_in = self.input_box.get()
        prev_out = self.output_box.get()
        self.stop()
        self.inputs = eng.list_input_devices()
        self.outputs = eng.list_output_devices()
        self.input_box.set_values([n for _, n in self.inputs])
        self.output_box.set_values([n for _, n in self.outputs])
        self.input_box.set("")
        self.output_box.set("")
        self._select_by_name(self.input_box, self.inputs, prev_in)
        self._select_by_name(self.output_box, self.outputs, prev_out)
        if not self.input_box.get() or not self.output_box.get():
            self._preselect()
        if not self.input_box.get() and self.inputs:
            self.input_box.current(0)
        if not self.output_box.get() and self.outputs:
            self.output_box.current(0)
        self._refresh_status()
        self._update_cable_ui()

    def _selected_index(self, box: ui.RoundCombo, devices) -> int | None:
        pos = box.current()
        if pos < 0 or pos >= len(devices):
            return None
        return devices[pos][0]

    def toggle(self) -> None:
        if self.engine is not None and self.engine.running:
            self.stop()
        else:
            self.start()

    def start(self, quiet: bool = False) -> bool:
        if self.engine is not None and self.engine.running:
            return True
        in_dev = self._selected_index(self.input_box, self.inputs)
        out_dev = self._selected_index(self.output_box, self.outputs)
        if in_dev is None or out_dev is None:
            if not quiet:
                ui.show_warning(
                    self.root, APP_TITLE, "Hãy chọn micro và thiết bị đầu ra.")
            return False

        self.engine = eng.AudioEngine(
            in_dev, out_dev, self.mix_var.get() / 100.0,
            denoiser=self._selected_denoiser(),
            aec=bool(self.aec_var.get()))
        self.engine.muted = self._muted
        try:
            self.engine.start()
        except Exception as exc:
            self.engine = None
            if not quiet:
                ui.show_error(
                    self.root, APP_TITLE,
                    f"Không mở được thiết bị âm thanh:\n{exc}")
            self._set_notice("Khởi động thất bại.", tone="error")
            self._update_power_ui()
            return False

        self._update_power_ui()
        if self.engine.denoiser_error:
            self._set_notice(self.engine.denoiser_error, tone="warn")
        elif self.engine.aec_error:
            self._set_notice(self.engine.aec_error, tone="warn")
        else:
            self._set_notice("")
        self._refresh_status()
        if self._mini is not None:
            self._mini.set_running(True)
            self._mini.set_muted(self._muted)
        self._save_config()
        self._refresh_tray_menu()
        return True

    def stop(self) -> None:
        had_engine = self.engine is not None
        self.set_muted(False)
        if self.engine is not None:
            self.engine.stop()
            self.engine = None
        self._update_power_ui()
        if self._mini is not None:
            self._mini.set_running(False)
        if not self._closed and had_engine:
            self._set_notice("Đã dừng khử ồn.")

    def _update_power_ui(self) -> None:
        if not hasattr(self, "state_label"):
            return
        running = self.engine is not None and self.engine.running
        if running and self._muted:
            dot = DANGER
            title = "ĐANG TẮT TIẾNG"
            title_fg = "#ff8a8a"
            sub = "Âm thanh đang được giữ yên tạm thời."
        elif running:
            dot = ACCENT
            title = "ĐANG KHỬ ỒN"
            title_fg = FG
            model = "DFN3" if self.engine.denoiser_name == "dfn3" else "RNNoise"
            parts = [model, f"Mức {self.mix_var.get():.0f}%"]
            if self.engine.aec_active:
                parts.append("AEC")
            sub = "  ·  ".join(parts)
        else:
            dot = MUTED
            title = "KHỬ ỒN ĐANG TẮT"
            title_fg = FG
            sub = "Chọn micro rồi bấm bật để bắt đầu."

        self.state_dot.itemconfigure(self.state_dot_id, fill=dot)
        self.state_label.configure(text=title, fg=title_fg)
        self.state_sub.configure(text=sub)
        if running:
            self.toggle_btn.set_text("TẮT KHỬ ỒN")
            self.toggle_btn.set_kind("primary")
        else:
            self.toggle_btn.set_text("BẬT KHỬ ỒN")
            self.toggle_btn.set_kind("secondary")
        if self._tray is not None:
            state, _ = self._tray_state()
            if state != self._tray_state_cur:
                self._refresh_tray_menu()
        if self._ui_ready:
            self.root.after_idle(self._fit_window)

    def _maybe_autostart(self) -> None:
        if self._closed or not self.config.get("auto_start", True):
            return
        if self.engine is not None:
            return
        selected = self.output_box.get().lower()
        if "cable input" not in selected:
            return
        self.start(quiet=True)

    def _save_config(self) -> None:
        self.config["input"] = self.input_box.get()
        self.config["output"] = self.output_box.get()
        self.config["mix"] = float(self.mix_var.get())
        self.config["denoiser"] = self._selected_denoiser()
        self.config["aec"] = bool(self.aec_var.get())
        self.config["mute_toggle"] = bool(self.mute_toggle_var.get())
        self.config["mini_visible"] = self._mini_visible
        if self._mini is not None and self._mini.winfo_ismapped():
            self.config["mini_x"] = self._mini.winfo_x()
            self.config["mini_y"] = self._mini.winfo_y()
        config.save(self.config)

    def _ease_level(self, current: float, target: float) -> float:
        if target > current:
            return current + (target - current) * 0.6
        return current * 0.78

    def _draw_level(self, canvas: tk.Canvas, value: float) -> None:
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 1:
            width = WINDOW_WIDTH - 2 * PAD - 40
        height = 6
        canvas.create_rectangle(0, 0, width, height, fill=PANEL, width=0)
        shown = min(1.0, (max(0.0, value) * 4.0) ** 0.5)
        if shown > 0.005:
            color = ACCENT if shown < 0.85 else WARN
            canvas.create_rectangle(0, 0, max(2, width * shown), height,
                                    fill=color, width=0)

    def _update_meters(self) -> None:
        active = self.engine is not None and self.engine.running
        in_target = self.engine.input_level if active else 0.0
        out_target = self.engine.level if active and not self._muted else 0.0
        self._disp_in = self._ease_level(self._disp_in, in_target)
        self._disp_out = self._ease_level(self._disp_out, out_target)
        self._draw_level(self.in_canvas, self._disp_in)
        self._draw_level(self.out_canvas, self._disp_out)

    def _tick(self) -> None:
        if self._closed:
            return
        self.root.after(60, self._tick)
        if self._mini is not None:
            self._mini.set_running(self.engine is not None and self.engine.running)
        self._update_meters()
        if self.engine is not None and self.engine.running:
            if self.engine.error:
                self._set_notice(f"Lỗi: {self.engine.error}", tone="error")
            elif self.engine.aec_error:
                self._set_notice(self.engine.aec_error, tone="warn")
        if self._tray is not None:
            state, _ = self._tray_state()
            if state != self._tray_state_cur:
                self._refresh_tray_menu()

    def show_help(self) -> None:
        ui.show_help(self.root, HELP_TEXT)

    def on_close(self) -> None:
        if self._tray is not None:
            self._hidden = True
            try:
                self._notify_minimized()
            finally:
                self.root.withdraw()
        else:
            self.quit()

    def _notify_minimized(self) -> None:
        if self._toast is not None:
            try:
                self._toast.dismiss()
            except tk.TclError:
                pass
            self._toast = None

        running = self.engine is not None and self.engine.running
        if running and self.engine.error:
            tone = "error"
            title = "Noise Cut gặp lỗi"
            body = ("Bộ lọc đang gặp lỗi khi xử lý âm thanh.\n"
                    "Mở lại ứng dụng để kiểm tra.")
        elif running and self._muted:
            tone = "muted"
            title = "Noise Cut đang tắt tiếng"
            body = ("Ứng dụng đã được thu nhỏ xuống khay hệ thống.\n"
                    "Micro đang tắt — mở lại để bật tiếng.")
        elif running:
            tone = "running"
            title = "Noise Cut đang hoạt động"
            body = ("Ứng dụng đã được thu nhỏ xuống khay hệ thống.\n"
                    "Khử tiếng ồn vẫn tiếp tục hoạt động bình thường.")
        else:
            tone = "stopped"
            title = "Noise Cut đang chạy nền"
            body = ("Ứng dụng đã được thu nhỏ xuống khay hệ thống.\n"
                    "Bộ lọc đang tắt — mở lại để bật.")

        try:
            self._toast = Toast(
                self.root, title=title, body=body, tone=tone,
                on_open=self._show_window, on_quit=self.quit)
        except Exception:
            self._toast = None
            try:
                self._tray.notify(
                    "Ứng dụng đã được thu nhỏ xuống khay hệ thống.\n"
                    "Nhấn biểu tượng mic để mở lại.", title)
            except Exception:
                pass

    def quit(self) -> None:
        self._closed = True
        self._save_config()
        self.stop()
        self._hotkey.stop()
        if self._mini is not None:
            try:
                self._mini.destroy()
            except Exception:
                pass
            self._mini = None
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        self.root.destroy()


def run() -> None:
    if os.name != "nt":
        raise SystemExit("Noise Cut chỉ hỗ trợ Windows.")
    root = tk.Tk()
    App(root)
    root.mainloop()
