"""Minimal tkinter UI with a system-tray icon for noise-cut."""

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image

from . import config
from . import dfn3
from . import engine as eng
from . import hotkey
from . import vbcable
from .mini import MiniBar

APP_TITLE = "noise-cut"
DENOISER_CHOICES = (
    ("rnnoise", "RNNoise — nhẹ, mặc định"),
    ("dfn3", "DFN3 — chất lượng cao (+30 ms)"),
)
BG = "#1e1f22"
FG = "#e6e6e6"
ACCENT = "#3ba55d"
MUTED = "#9aa0a6"

HELP_TEXT = (
    "Cách dùng với Google Meet / Zoom / Teams:\n\n"
    "1. Bấm nút 'Cài mic ảo (VB-Cable)' trong app để cài mic ảo.\n"
    "   Cần quyền admin (UAC) và khởi động lại Windows 1 lần.\n"
    "   VB-CABLE là donationware của VB-Audio: www.vb-cable.com\n"
    "   (Có thể cài thủ công từ https://vb-audio.com/Cable/ nếu muốn.)\n\n"
    "2. Trong noise-cut chọn:\n"
    "   - Micro: mic thật của bạn\n"
    "   - Đầu ra: CABLE Input (VB-Audio Virtual Cable)\n\n"
    "3. App tự bật lọc khi mở (nếu đã có VB-Cable). Nếu chưa,\n"
    "   bấm Bắt đầu sau khi chọn thiết bị.\n"
    "   Bộ lọc RNNoise nhẹ và ổn định; DFN3 lọc mạnh hơn nhưng\n"
    "   trễ thêm ~30 ms và vẫn có thể lọt tiếng người xung quanh.\n\n"
    "4. Trong Meet/Zoom/Teams chọn micro là\n"
    "   'CABLE Output (VB-Audio Virtual Cable)'.\n\n"
    "5. Tắt khử ồn có sẵn của Meet/Zoom/Teams để tránh lọc 2 lần.\n\n"
    "6. Khi ho/hắt xì: GIỮ Ctrl+Shift+? (phím /) để tắt tiếng,\n"
    "   thả ra để nói tiếp. Cũng có thể giữ nút 'GIỮ ĐỂ TẮT TIẾNG'\n"
    "   trên cửa sổ chính hoặc thanh nhỏ luôn nổi.\n\n"
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
        self._cable_pending_reboot = False
        self._installing = False
        self._muted = False
        self._mini: MiniBar | None = None
        self._mini_visible = bool(self.config.get("mini_visible", True))
        self._dfn3_available = dfn3.available()
        self._hotkey = hotkey.MuteHotkey(self._on_hotkey_mute)

        root.title(APP_TITLE)
        root.configure(bg=BG)
        root.geometry("400x575")
        root.minsize(400, 575)
        root.resizable(False, False)

        self._build_style()
        self._build_widgets()
        self._preselect()
        self._update_cable_ui()
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
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI Semibold", 16))
        style.configure("TCombobox", fieldbackground="#2b2d31", background="#2b2d31",
                        foreground=FG, arrowcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", "#2b2d31")],
                  foreground=[("readonly", FG)])
        style.configure("TButton", background="#2b2d31", foreground=FG,
                        borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#3a3d42")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", "#2f8a4a")])
        style.configure("Horizontal.TScale", background=BG, troughcolor="#2b2d31")
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("active", FG)])

    def _build_widgets(self) -> None:
        pad = {"padx": 16}

        header = ttk.Frame(self.root)
        header.pack(fill="x", pady=(14, 6), **pad)
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="?", width=3, command=self.show_help).pack(side="right")

        form = ttk.Frame(self.root)
        form.pack(fill="x", **pad)

        ttk.Label(form, text="Micro", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar()
        self.input_box = ttk.Combobox(form, textvariable=self.input_var, state="readonly",
                                      width=36, values=[n for _, n in self.inputs])
        self.input_box.grid(row=1, column=0, sticky="we", pady=(2, 10), columnspan=2)

        ttk.Label(form, text="Đầu ra (mic ảo)", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w")
        ttk.Button(form, text="↻", width=3, command=self.refresh_devices).grid(
            row=2, column=1, sticky="e")
        self.output_box = ttk.Combobox(form, state="readonly", width=36,
                                       values=[n for _, n in self.outputs])
        self.output_box.grid(row=3, column=0, sticky="we", pady=(2, 10), columnspan=2)

        self.mix_label = ttk.Label(form, text="Độ lọc: 100%", style="Muted.TLabel")
        self.mix_label.grid(row=4, column=0, sticky="w")
        self.mix_var = tk.DoubleVar(value=float(self.config.get("mix", 100.0)))
        scale = ttk.Scale(form, from_=0, to=100, variable=self.mix_var,
                          command=self.on_mix_change)
        scale.grid(row=5, column=0, sticky="we", pady=(2, 10), columnspan=2)
        self.mix_label.configure(text=f"Độ lọc: {self.mix_var.get():.0f}%")

        ttk.Label(form, text="Bộ lọc", style="Muted.TLabel").grid(
            row=6, column=0, sticky="w")
        choices = [label for _, label in DENOISER_CHOICES
                   if self._dfn3_available or label.startswith("RNNoise")]
        self.denoiser_var = tk.StringVar()
        self.denoiser_box = ttk.Combobox(form, textvariable=self.denoiser_var,
                                         state="readonly", width=36, values=choices)
        self.denoiser_box.grid(row=7, column=0, sticky="we", pady=(2, 10), columnspan=2)
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

        form.columnconfigure(0, weight=1)

        self.meter = tk.Canvas(self.root, height=26, bg=BG, highlightthickness=0)
        self.meter.pack(fill="x", **pad)
        self._draw_meter(0.0, 0.0)

        mute_frame = ttk.Frame(self.root)
        mute_frame.pack(fill="x", **pad)
        ttk.Label(mute_frame, text="Tắt tiếng nhanh (khi ho/hắt xì)",
                  style="Muted.TLabel").pack(anchor="w")
        mute_row = ttk.Frame(mute_frame)
        mute_row.pack(fill="x", pady=(2, 6))
        toggle = bool(self.config.get("mute_toggle", False))
        self.hotkey_label = ttk.Label(
            mute_row,
            text="Ctrl+Shift+? (bấm để bật/tắt)" if toggle else hotkey.LABEL,
            style="Muted.TLabel")
        self.hotkey_label.pack(side="left")
        self.mute_toggle_var = tk.BooleanVar(value=toggle)
        ttk.Checkbutton(mute_row, text="Bấm 1 lần để bật/tắt",
                        variable=self.mute_toggle_var,
                        command=self.on_mute_toggle_change).pack(side="right")
        self.mute_hold_btn = ttk.Button(mute_frame, text="GIỮ ĐỂ TẮT TIẾNG")
        self.mute_hold_btn.pack(fill="x")
        self.mute_hold_btn.bind("<ButtonPress-1>", self._on_hold_press)
        self.mute_hold_btn.bind("<ButtonRelease-1>", self._on_hold_release)
        self.mute_banner = tk.Label(self.root, text="ĐANG TẮT TIẾNG",
                                    bg="#a33333", fg="white",
                                    font=("Segoe UI Semibold", 11))

        actions = ttk.Frame(self.root)
        actions.pack(fill="x", pady=(8, 4), **pad)
        self.toggle_btn = ttk.Button(actions, text="Bắt đầu", style="Accent.TButton",
                                     command=self.toggle)
        self.toggle_btn.pack(side="left", fill="x", expand=True)

        self.autorun_var = tk.BooleanVar(value=config.autorun_enabled())
        ttk.Checkbutton(self.root, text="Tự chạy cùng Windows",
                        variable=self.autorun_var,
                        command=self.on_autorun_toggle).pack(anchor="w", padx=16, pady=(6, 0))

        self.status = ttk.Label(self.root, text="", style="Muted.TLabel", anchor="w")
        self.status.pack(fill="x", pady=(4, 0), **pad)

        self.install_btn = ttk.Button(self.root, text="Cài mic ảo (VB-Cable)",
                                      command=self.on_install_cable)

    def _icon_image(self) -> Image.Image:
        path = config.resource_path("assets", "icon.ico")
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return Image.new("RGBA", (64, 64), (59, 165, 93, 255))

    def _setup_tray(self) -> None:
        try:
            import pystray
        except Exception:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Mở noise-cut", self._tray_show, default=True),
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
            self.status.configure(text="Đã tìm thấy VB-Cable.")
        else:
            self._select_by_name(self.output_box, self.outputs, stored_out)
            self.status.configure(
                text="Chưa có VB-Cable — bấm ? để xem hướng dẫn cài.")

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

    def _select_by_name(self, box: ttk.Combobox, devices, name: str) -> None:
        for i, (_, dev_name) in enumerate(devices):
            if dev_name == name:
                box.current(i)
                return

    def on_mix_change(self, _value=None) -> None:
        value = self.mix_var.get()
        self.mix_label.configure(text=f"Độ lọc: {value:.0f}%")
        if self.engine is not None:
            self.engine.set_mix(value / 100.0)

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
        self._refresh_tray_menu()

    def on_autorun_toggle(self) -> None:
        wanted = self.autorun_var.get()
        if config.set_autorun(wanted):
            self.status.configure(
                text="Đã bật tự chạy cùng Windows." if wanted
                else "Đã tắt tự chạy cùng Windows.")
        else:
            self.autorun_var.set(not wanted)
            self.status.configure(text="Không ghi được đăng ký tự chạy.")
        self._refresh_tray_menu()

    def _toggle_autorun(self) -> None:
        self.autorun_var.set(not config.autorun_enabled())
        self.on_autorun_toggle()

    # ---- instant mute (cough button) ----

    def _setup_hotkey(self) -> None:
        toggle = bool(self.config.get("mute_toggle", False))
        self.mute_toggle_var.set(toggle)
        self._hotkey.configure(toggle)
        self._hotkey.sync(self._muted)
        if not self._hotkey.start():
            self.status.configure(
                text="Không bật được phím tắt Ctrl+Shift+/? (thiếu pynput).")

    def on_mute_toggle_change(self) -> None:
        toggle = bool(self.mute_toggle_var.get())
        self.config["mute_toggle"] = toggle
        config.save(self.config)
        self.hotkey_label.configure(
            text="Ctrl+Shift+? (bấm để bật/tắt)" if toggle else hotkey.LABEL)
        self._hotkey.configure(toggle)
        self._hotkey.sync(self._muted)
        if not self._hotkey.start():
            self.status.configure(
                text="Không bật được phím tắt Ctrl+Shift+/? (thiếu pynput).")
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
        messagebox.showinfo("Hướng dẫn", HELP_TEXT, parent=self._mini)

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

    def _update_mute_ui(self) -> None:
        if self._muted:
            if self.mute_toggle_var.get():
                self.mute_hold_btn.configure(text="ĐANG TẮT TIẾNG — bấm để mở")
            else:
                self.mute_hold_btn.configure(text="ĐANG TẮT TIẾNG — thả ra để mở")
            if not self.mute_banner.winfo_manager():
                self.mute_banner.pack(fill="x", padx=16, pady=(6, 0),
                                       before=self.status)
        else:
            self.mute_hold_btn.configure(
                text="BẤM ĐỂ TẮT TIẾNG" if self.mute_toggle_var.get()
                else "GIỮ ĐỂ TẮT TIẾNG")
            self.mute_banner.pack_forget()
        if self._mini is not None:
            self._mini.set_muted(self._muted)
        self._refresh_tray_menu()

    def _refresh_tray_menu(self) -> None:
        if self._tray is not None:
            try:
                self._tray.update_menu()
            except Exception:
                pass

    def _update_cable_ui(self) -> None:
        if vbcable.installed():
            self.install_btn.pack_forget()
        else:
            if self._installing:
                self.install_btn.configure(state="disabled",
                                           text="Đang cài VB-Cable...")
            elif self._cable_pending_reboot:
                self.install_btn.configure(
                    state="disabled", text="Đã cài — cần khởi động lại Windows")
            else:
                self.install_btn.configure(state="normal",
                                           text="Cài mic ảo (VB-Cable)")
            if not self.install_btn.winfo_manager():
                self.install_btn.pack(fill="x", padx=16, pady=(6, 0), before=self.status)
        self._refresh_tray_menu()

    def on_install_cable(self) -> None:
        if self._installing:
            return
        if vbcable.installed():
            self._update_cable_ui()
            return
        if not messagebox.askyesno(APP_TITLE, INSTALL_CONFIRM):
            return
        self._installing = True
        self.install_btn.configure(state="disabled", text="Đang cài VB-Cable...")
        self.status.configure(text="Đang cài VB-Cable — bấm Yes ở hộp thoại UAC.")
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
            self.install_btn.configure(state="normal", text="Cài mic ảo (VB-Cable)")
        self.refresh_devices()
        self._show_window()
        if ok:
            messagebox.showinfo(
                APP_TITLE,
                "Đã cài VB-CABLE.\n\n"
                "Hãy khởi động lại Windows để hoàn tất.\n"
                "Sau khi khởi động lại, mở noise-cut — app sẽ tự nhận\n"
                "mic ảo và tự bật lọc.\n\n"
                "VB-CABLE là donationware của VB-Audio (www.vb-cable.com).",
            )
            self.status.configure(text="Đã cài VB-CABLE — cần khởi động lại Windows.")
        else:
            messagebox.showerror(APP_TITLE, message or "Cài đặt thất bại.")
            self.status.configure(text="Cài VB-Cable thất bại.")
        self._update_cable_ui()

    def refresh_devices(self) -> None:
        prev_in = self.input_box.get()
        prev_out = self.output_box.get()
        self.stop()
        self.inputs = eng.list_input_devices()
        self.outputs = eng.list_output_devices()
        self.input_box.configure(values=[n for _, n in self.inputs])
        self.output_box.configure(values=[n for _, n in self.outputs])
        self.input_box.set("")
        self.output_box.set("")
        self._select_by_name(self.input_box, self.inputs, prev_in)
        self._select_by_name(self.output_box, self.outputs, prev_out)
        if not self.input_box.get() or not self.output_box.get():
            self._preselect()
        if not self.input_box.get() and self.inputs:
            self.input_box.current(0)
        self._update_cable_ui()

    def _selected_index(self, box: ttk.Combobox, devices) -> int | None:
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
                messagebox.showwarning(APP_TITLE, "Hãy chọn micro và thiết bị đầu ra.")
            return False

        self.engine = eng.AudioEngine(
            in_dev, out_dev, self.mix_var.get() / 100.0,
            denoiser=self._selected_denoiser())
        self.engine.muted = self._muted
        try:
            self.engine.start()
        except Exception as exc:
            self.engine = None
            if not quiet:
                messagebox.showerror(APP_TITLE, f"Không mở được thiết bị âm thanh:\n{exc}")
            self.status.configure(text="Khởi động thất bại.")
            return False

        self.toggle_btn.configure(text="Dừng", style="TButton")
        if self.engine.denoiser_error:
            self.status.configure(text=self.engine.denoiser_error)
        else:
            self.status.configure(
                text=f"Đang chạy ({self.engine.denoiser_name.upper()}) → {self.output_box.get()}")
        if self._mini is not None:
            self._mini.set_running(True)
            self._mini.set_muted(self._muted)
        self._save_config()
        self._refresh_tray_menu()
        return True

    def stop(self) -> None:
        self.set_muted(False)
        if self.engine is not None:
            self.engine.stop()
            self.engine = None
        self.toggle_btn.configure(text="Bắt đầu", style="Accent.TButton")
        self._draw_meter(0.0, 0.0)
        if self._mini is not None:
            self._mini.set_running(False)
        if not self._closed:
            self.status.configure(text="Đã dừng.")

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
        self.config["mute_toggle"] = bool(self.mute_toggle_var.get())
        self.config["mini_visible"] = self._mini_visible
        if self._mini is not None and self._mini.winfo_ismapped():
            self.config["mini_x"] = self._mini.winfo_x()
            self.config["mini_y"] = self._mini.winfo_y()
        config.save(self.config)

    def _draw_meter(self, level: float, speech: float) -> None:
        self.meter.delete("all")
        width = self.meter.winfo_width()
        if width <= 1:
            width = 368
        height = 8
        top = 4
        self.meter.create_rectangle(0, top, width, top + height, fill="#2b2d31", width=0)
        shown = min(1.0, (level * 4.0) ** 0.5)
        if shown > 0.005:
            color = ACCENT if level < 0.5 else "#e0a33a"
            self.meter.create_rectangle(0, top, width * shown, top + height,
                                        fill=color, width=0)
        if self.engine and self.engine.denoiser_name == "dfn3":
            label = "Bộ lọc: DFN3 (chất lượng cao)"
        else:
            label = f"Giọng nói: {speech * 100:.0f}%" if self.engine else ""
        self.meter.create_text(0, top + 19, anchor="w", fill=MUTED, text=label,
                               font=("Segoe UI", 8))

    def _tick(self) -> None:
        if self._closed:
            return
        self.root.after(60, self._tick)
        if self._mini is not None:
            self._mini.set_running(self.engine is not None and self.engine.running)
        if self.engine is not None and self.engine.running:
            self._draw_meter(self.engine.level, self.engine.speech_prob)
            if self.engine.error:
                self.status.configure(text=f"Lỗi: {self.engine.error}")

    def show_help(self) -> None:
        messagebox.showinfo("Hướng dẫn", HELP_TEXT)

    def on_close(self) -> None:
        if self._tray is not None:
            self._hidden = True
            self.root.withdraw()
            try:
                self._tray.notify(
                    "noise-cut vẫn chạy; thanh nhỏ vẫn hiển thị trên màn hình.")
            except Exception:
                pass
        else:
            self.quit()

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
        raise SystemExit("noise-cut chỉ hỗ trợ Windows.")
    root = tk.Tk()
    App(root)
    root.mainloop()
