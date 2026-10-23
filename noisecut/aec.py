"""ctypes binding for the bundled SpeexDSP acoustic echo canceller."""

import ctypes
import os
import sys

import numpy as np

SAMPLE_RATE = 48000
FRAME_SIZE = 480
FILTER_MS = 200
FILTER_LENGTH = int(SAMPLE_RATE * FILTER_MS / 1000)
DLL_NAME = "libspeexdsp-1.dll"

_SPEEX_ECHO_SET_SAMPLING_RATE = 24
_SPEEX_PREPROCESS_SET_DENOISE = 0
_SPEEX_PREPROCESS_SET_AGC = 2
_SPEEX_PREPROCESS_SET_DEREVERB = 8
_SPEEX_PREPROCESS_SET_NOISE_SUPPRESS = 18
_SPEEX_PREPROCESS_SET_ECHO_STATE = 24


def _dll_path() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return os.path.join(base, "noisecut", DLL_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DLL_NAME)


_lib = None


def _load_lib():
    global _lib
    if _lib is not None:
        return _lib
    path = _dll_path()
    if not os.path.isfile(path):
        raise OSError(f"{DLL_NAME} not found: {path}")
    lib = ctypes.CDLL(path)
    lib.speex_echo_state_init.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.speex_echo_state_init.restype = ctypes.c_void_p
    lib.speex_echo_ctl.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lib.speex_echo_ctl.restype = ctypes.c_int
    lib.speex_echo_cancellation.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.POINTER(ctypes.c_int16),
        ctypes.POINTER(ctypes.c_int16),
    ]
    lib.speex_echo_cancellation.restype = None
    lib.speex_echo_state_destroy.argtypes = [ctypes.c_void_p]
    lib.speex_echo_state_destroy.restype = None
    lib.speex_preprocess_state_init.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.speex_preprocess_state_init.restype = ctypes.c_void_p
    lib.speex_preprocess_ctl.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lib.speex_preprocess_ctl.restype = ctypes.c_int
    lib.speex_preprocess_run.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16)]
    lib.speex_preprocess_run.restype = ctypes.c_int
    lib.speex_preprocess_state_destroy.argtypes = [ctypes.c_void_p]
    lib.speex_preprocess_state_destroy.restype = None
    _lib = lib
    return lib


def available() -> bool:
    try:
        _load_lib()
        return True
    except Exception:
        return False


class EchoCanceller:
    """Cancels speaker echo from the mic using a loopback reference.

    Frames are mono float32 in [-1, 1] at 48 kHz.  ``reference`` must be
    time-aligned with the mic frame; the adaptive filter models the delay
    (up to FILTER_MS) and the room path.  ``residual`` enables SpeexDSP's
    residual echo suppressor; it is off by default to preserve near-end
    speech during double-talk.
    """

    def __init__(self, frame_size: int = FRAME_SIZE,
                 filter_length: int = FILTER_LENGTH,
                 sample_rate: int = SAMPLE_RATE,
                 residual: bool = False):
        lib = _load_lib()
        self._lib = lib
        self._size = int(frame_size)
        self._echo = lib.speex_echo_state_init(
            self._size, int(filter_length))
        if not self._echo:
            raise RuntimeError("speex_echo_state_init() failed")
        rate = ctypes.c_int(int(sample_rate))
        if lib.speex_echo_ctl(
                self._echo, _SPEEX_ECHO_SET_SAMPLING_RATE,
                ctypes.byref(rate)) != 0:
            lib.speex_echo_state_destroy(self._echo)
            self._echo = None
            raise RuntimeError("speex_echo_ctl(SET_SAMPLING_RATE) failed")
        self._pre = None
        if residual:
            pre = lib.speex_preprocess_state_init(
                self._size, int(sample_rate))
            if pre:
                if lib.speex_preprocess_ctl(
                        pre, _SPEEX_PREPROCESS_SET_ECHO_STATE,
                        self._echo) != 0:
                    lib.speex_preprocess_state_destroy(pre)
                else:
                    self._set_pre_int(pre, _SPEEX_PREPROCESS_SET_DENOISE, 1)
                    self._set_pre_int(pre, _SPEEX_PREPROCESS_SET_AGC, 0)
                    self._set_pre_int(pre, _SPEEX_PREPROCESS_SET_DEREVERB, 0)
                    self._set_pre_int(
                        pre, _SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, 0)
                    self._pre = pre
        self._mic_i16 = np.zeros(self._size, dtype=np.int16)
        self._ref_i16 = np.zeros(self._size, dtype=np.int16)
        self._out_i16 = np.zeros(self._size, dtype=np.int16)
        self._mic_f32 = np.zeros(self._size, dtype=np.float32)
        self._ref_f32 = np.zeros(self._size, dtype=np.float32)

    def _set_pre_int(self, state, request: int, value: int) -> None:
        data = ctypes.c_int(int(value))
        self._lib.speex_preprocess_ctl(
            state, request, ctypes.byref(data))

    def cancel(self, mic: np.ndarray, reference: np.ndarray) -> np.ndarray:
        mic = np.ascontiguousarray(mic, dtype=np.float32)
        reference = np.ascontiguousarray(reference, dtype=np.float32)
        if mic.size != self._size or reference.size != self._size:
            raise ValueError(
                f"expected {self._size} samples, got {mic.size}/{reference.size}")

        np.multiply(mic, 32767.0, out=self._mic_f32)
        np.clip(self._mic_f32, -32768.0, 32767.0, out=self._mic_f32)
        np.copyto(self._mic_i16, self._mic_f32, casting="unsafe")

        np.multiply(reference, 32767.0, out=self._ref_f32)
        np.clip(self._ref_f32, -32768.0, 32767.0, out=self._ref_f32)
        np.copyto(self._ref_i16, self._ref_f32, casting="unsafe")

        out_ptr = self._out_i16.ctypes.data_as(
            ctypes.POINTER(ctypes.c_int16))
        self._lib.speex_echo_cancellation(
            self._echo,
            self._mic_i16.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            self._ref_i16.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            out_ptr,
        )
        if self._pre is not None:
            self._lib.speex_preprocess_run(self._pre, out_ptr)
        return self._out_i16.astype(np.float32) * (1.0 / 32768.0)

    def close(self) -> None:
        pre = self._pre
        self._pre = None
        if pre:
            self._lib.speex_preprocess_state_destroy(pre)
        echo = self._echo
        self._echo = None
        if echo:
            self._lib.speex_echo_state_destroy(echo)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
