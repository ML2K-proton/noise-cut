"""RNNoise-based denoiser with high-pass filter and dry/wet mix."""

import ctypes
import math

import numpy as np

from .rnnoise import SAMPLE_RATE, create, destroy, process_frame

HIGHPASS_HZ = 80.0


class Highpass:
    """Streaming 1st-order high-pass, vectorised with NumPy only.

    Recurrence: y[n] = a * (y[n-1] + x[n] - x[n-1])
    Closed form: y[n] = a^(n+1) * y[-1] + a^n * sum_k a^-k * d[k]
    where d[k] = a * (x[k] - x[k-1]).  Keeping it in float64 is stable for
    the 480-sample frames used here.
    """

    def __init__(self, cutoff_hz: float = HIGHPASS_HZ, sample_rate: int = SAMPLE_RATE):
        self._a = float(1.0 / (1.0 + 2.0 * math.pi * cutoff_hz / sample_rate))
        self._prev_x = 0.0
        self._prev_y = 0.0

    def reset(self) -> None:
        self._prev_x = 0.0
        self._prev_y = 0.0

    def process(self, frame: np.ndarray) -> np.ndarray:
        x = np.asarray(frame, dtype=np.float64)
        n = x.size
        if n == 0:
            return np.zeros(0, dtype=np.float32)
        a = self._a
        powers = np.power(a, np.arange(n, dtype=np.float64))
        d = a * x
        d[1:] -= a * x[:-1]
        d[0] -= a * self._prev_x
        s = np.cumsum(d / powers)
        y = powers * (a * self._prev_y + s)
        self._prev_x = float(x[-1])
        self._prev_y = float(y[-1])
        np.clip(y, -1.0, 1.0, out=y)
        return y.astype(np.float32)


class Denoiser:
    """Processes 480-sample mono frames at 48 kHz."""

    def __init__(self, mix: float = 1.0):
        self._state: ctypes.c_void_p | None = create()
        self._target_mix = float(np.clip(mix, 0.0, 1.0))
        self._mix = self._target_mix
        self._highpass = Highpass()
        self.level = 0.0
        self.speech_prob = 0.0

    @property
    def mix(self) -> float:
        return self._target_mix

    @mix.setter
    def mix(self, value: float) -> None:
        self._target_mix = float(np.clip(value, 0.0, 1.0))

    def process(self, frame: np.ndarray) -> np.ndarray:
        """frame: mono float32/int16 ([-1, 1] or int16 range).

        Returns a float32 frame in [-1, 1].
        """
        if frame.dtype == np.int16:
            dry = frame.astype(np.float32) / 32768.0
        else:
            dry = np.asarray(frame, dtype=np.float32)

        dry = self._highpass.process(dry)

        if self._state is not None:
            wet, prob = process_frame(self._state, dry)
            self.speech_prob = prob
        else:
            wet = dry
            self.speech_prob = 1.0

        # smooth mix changes to avoid zipper noise
        if abs(self._mix - self._target_mix) > 1e-4:
            self._mix += 0.15 * (self._target_mix - self._mix)
        else:
            self._mix = self._target_mix

        mixed = self._mix * wet + (1.0 - self._mix) * dry
        np.clip(mixed, -1.0, 1.0, out=mixed)
        self.level = float(np.sqrt(np.mean(mixed * mixed)))
        return mixed

    def close(self) -> None:
        if self._state is not None:
            destroy(self._state)
            self._state = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
