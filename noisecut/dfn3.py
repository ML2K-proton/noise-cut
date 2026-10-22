"""Optional DeepFilterNet3 denoiser with the same 480-sample interface as RNNoise."""

import numpy as np

from .rnnoise import FRAME_SIZE, SAMPLE_RATE

DELAY_FRAMES = 3


def available() -> bool:
    try:
        from deepfilternet_rs import DeepFilterNetRealtime
        return bool(DeepFilterNetRealtime)
    except Exception:
        return False


class DFN3Denoiser:
    name = "dfn3"
    supports_speech_prob = False

    def __init__(self, mix: float = 1.0):
        from deepfilternet_rs import DeepFilterNetRealtime

        self._state = DeepFilterNetRealtime(
            atten_lim=100.0,
            log_level="error",
            compensate_delay=False,
            post_filter_beta=0.0,
        )
        if self._state.sample_rate != SAMPLE_RATE or self._state.frame_length != FRAME_SIZE:
            self._state.close()
            raise RuntimeError("DeepFilterNet3 frame format does not match RNNoise")
        self._target_mix = float(np.clip(mix, 0.0, 1.0))
        self._mix = self._target_mix
        self._dry = np.zeros((DELAY_FRAMES + 1, FRAME_SIZE), dtype=np.float32)
        self._dry_index = 0
        self.level = 0.0
        self.speech_prob = 0.0

    @property
    def mix(self) -> float:
        return self._target_mix

    @mix.setter
    def mix(self, value: float) -> None:
        self._target_mix = float(np.clip(value, 0.0, 1.0))

    def _frame(self, frame: np.ndarray) -> np.ndarray:
        if frame.dtype == np.int16:
            x = frame.astype(np.float32) / 32768.0
        else:
            x = np.asarray(frame, dtype=np.float32).reshape(-1)
        if x.size < FRAME_SIZE:
            x = np.pad(x, (0, FRAME_SIZE - x.size))
        elif x.size > FRAME_SIZE:
            x = x[:FRAME_SIZE]
        return x

    def process(self, frame: np.ndarray) -> np.ndarray:
        dry = self._frame(frame)
        self._dry[self._dry_index] = dry
        delayed = self._dry[(self._dry_index - DELAY_FRAMES) % (DELAY_FRAMES + 1)].copy()
        self._dry_index = (self._dry_index + 1) % (DELAY_FRAMES + 1)

        wet = np.asarray(self._state.process_chunk(dry), dtype=np.float32).reshape(-1)
        if wet.size < FRAME_SIZE:
            wet = np.pad(wet, (0, FRAME_SIZE - wet.size))
        elif wet.size > FRAME_SIZE:
            wet = wet[:FRAME_SIZE]

        if abs(self._mix - self._target_mix) > 1e-4:
            self._mix += 0.15 * (self._target_mix - self._mix)
        else:
            self._mix = self._target_mix

        mixed = self._mix * wet + (1.0 - self._mix) * delayed
        np.clip(mixed, -1.0, 1.0, out=mixed)
        self.level = float(np.sqrt(np.mean(mixed * mixed)))
        return mixed

    def close(self) -> None:
        state = getattr(self, "_state", None)
        if state is not None:
            self._state = None
            state.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
