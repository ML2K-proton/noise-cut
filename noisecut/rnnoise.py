"""Minimal ctypes binding for the bundled RNNoise library.

RNNoise is Copyright (c) Xiph.Org Foundation and contributors,
licensed under the BSD 3-Clause license. See RNNOISE_LICENSE.txt.
"""

import ctypes
import os
import sys

import numpy as np

SAMPLE_RATE = 48000
DTYPE = np.float32


def _dll_path() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return os.path.join(base, "noisecut", "rnnoise.dll")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rnnoise.dll")


_DLL_PATH = _dll_path()
if not os.path.isfile(_DLL_PATH):
    raise OSError(f"rnnoise.dll not found: {_DLL_PATH}")

_lib = ctypes.CDLL(_DLL_PATH)
_lib.rnnoise_create.argtypes = [ctypes.c_void_p]
_lib.rnnoise_create.restype = ctypes.c_void_p
_lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
_lib.rnnoise_destroy.restype = None
_lib.rnnoise_get_frame_size.restype = ctypes.c_int
_lib.rnnoise_process_frame.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
]
_lib.rnnoise_process_frame.restype = ctypes.c_float

FRAME_SIZE = int(_lib.rnnoise_get_frame_size())


def create():
    """Create a new RNNoise state (returns an opaque pointer)."""
    state = _lib.rnnoise_create(None)
    if not state:
        raise RuntimeError("rnnoise_create() failed")
    return state


def destroy(state) -> None:
    if state:
        _lib.rnnoise_destroy(state)


def process_frame(state, frame: np.ndarray) -> tuple[np.ndarray, float]:
    """Denoise one mono frame of FRAME_SIZE samples in [-1, 1].

    Returns (denoised float32 frame, speech probability 0..1).
    """
    frame = np.asarray(frame, dtype=np.float32)
    size = frame.size
    if size != FRAME_SIZE:
        raise ValueError(f"expected {FRAME_SIZE} samples, got {size}")

    work = np.array(frame, dtype=np.float32, copy=True)
    work *= 32767.0
    ptr = work.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    prob = _lib.rnnoise_process_frame(state, ptr, ptr)
    np.multiply(work, 1.0 / 32767.0, out=work)
    return work, float(prob)
