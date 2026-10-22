"""Global Ctrl+Shift+/? hotkey for instant mute.

Works even when the window is hidden in the tray. Uses a Windows
low-level keyboard hook (no driver, no admin needed).

Safety: the listener NEVER uses suppress=True (that would swallow all
input system-wide). Keys pass through untouched.
"""

import threading

HOTKEY_CTRL_SHIFT_SLASH = "ctrl_shift_slash"
LABEL = "Ctrl+Shift+/? (giữ để tắt tiếng)"

SLASH_VK = 0xBF  # VK_OEM_2, the physical /? key on a US-style layout


class MuteHotkey:
    """Listens for Ctrl+Shift+/? globally. Thread-safe via a lock.

    on_change(muted: bool) is called from the listener thread;
    the caller must marshal UI updates to the main thread.
    """

    def __init__(self, on_change):
        self._on_change = on_change
        self._toggle_mode = False
        self._latched = False
        self._ctrl = False
        self._shift = False
        self._slash = False
        self._chord = False
        self._lock = threading.Lock()
        self._keyboard_listener = None
        self._keyboard = None

    @property
    def kind(self) -> str:
        return HOTKEY_CTRL_SHIFT_SLASH

    def configure(self, toggle_mode: bool = False) -> None:
        self.stop()
        with self._lock:
            self._toggle_mode = bool(toggle_mode)

    def sync(self, muted: bool) -> None:
        """Keep the toggle latch in step with the app's actual mute state."""
        with self._lock:
            self._latched = bool(muted)

    def start(self) -> bool:
        """Start listening. Returns False if the backend is unavailable."""
        try:
            from pynput import keyboard
        except Exception:
            return False
        self.stop()
        self._keyboard = keyboard
        try:
            self._keyboard_listener = keyboard.Listener(
                on_press=self._key_press,
                on_release=self._key_release,
                suppress=False,
            )
            self._keyboard_listener.start()
        except Exception:
            self._keyboard_listener = None
            return False
        return True

    def stop(self) -> None:
        listener = self._keyboard_listener
        self._keyboard_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        with self._lock:
            was_active = self._chord
            self._latched = False
            self._ctrl = False
            self._shift = False
            self._slash = False
            self._chord = False
        if was_active:
            self._apply_hold(False)

    def _emit(self, muted: bool) -> None:
        try:
            self._on_change(muted)
        except Exception:
            pass

    def _apply_hold(self, held: bool) -> None:
        with self._lock:
            if self._toggle_mode:
                if not held:
                    return
                self._latched = not self._latched
                muted = self._latched
            else:
                muted = held
        self._emit(muted)

    def _key_name(self, key) -> str | None:
        keyboard = self._keyboard
        if keyboard is not None:
            try:
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    return "ctrl"
                if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    return "shift"
            except Exception:
                pass
        try:
            if getattr(key, "vk", None) == SLASH_VK:
                return "slash"
        except Exception:
            pass
        if getattr(key, "char", None) in ("/", "?"):
            return "slash"
        return None

    def _key_press(self, key) -> None:
        name = self._key_name(key)
        if name is None:
            return
        with self._lock:
            if name == "ctrl":
                self._ctrl = True
            elif name == "shift":
                self._shift = True
            elif name == "slash":
                if self._slash:  # ignore auto-repeat
                    return
                self._slash = True
            trigger = (
                self._slash and self._ctrl and self._shift and not self._chord
            )
            if trigger:
                self._chord = True
        if trigger:
            self._apply_hold(True)

    def _key_release(self, key) -> None:
        name = self._key_name(key)
        if name is None:
            return
        with self._lock:
            if name == "ctrl":
                self._ctrl = False
            elif name == "shift":
                self._shift = False
            elif name == "slash":
                self._slash = False
            was_chord = self._chord
            if name in ("ctrl", "shift", "slash"):
                self._chord = False
        if was_chord:
            self._apply_hold(False)
