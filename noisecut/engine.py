"""Audio device discovery, ring buffer and realtime engine."""

import queue
import threading

import numpy as np
import sounddevice as sd
from soxr import ResampleStream

from . import dfn3
from .aec import EchoCanceller
from .denoiser import Denoiser
from .dfn3 import DFN3Denoiser
from .loopback import LoopbackCapture, LoopbackError
from .rnnoise import FRAME_SIZE, SAMPLE_RATE

BLOCK = FRAME_SIZE
MAX_BUFFER_BLOCKS = 10
TARGET_PREFILL_BLOCKS = 4


def _wasapi_index() -> int | None:
    try:
        for i, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                return i
    except Exception:
        pass
    return None


def _devices(kind: str) -> list[tuple[int, str]]:
    wasapi = _wasapi_index()
    try:
        all_devices = sd.query_devices()
    except Exception:
        return []
    result = []
    for idx, dev in enumerate(all_devices):
        if kind == "input" and dev["max_input_channels"] <= 0:
            continue
        if kind == "output" and dev["max_output_channels"] <= 0:
            continue
        if wasapi is not None and dev["hostapi"] != wasapi:
            continue
        result.append((idx, dev["name"]))
    if not result:
        for idx, dev in enumerate(all_devices):
            if kind == "input" and dev["max_input_channels"] > 0:
                result.append((idx, dev["name"]))
            elif kind == "output" and dev["max_output_channels"] > 0:
                result.append((idx, dev["name"]))
    return result


def list_input_devices() -> list[tuple[int, str]]:
    return _devices("input")


def list_output_devices() -> list[tuple[int, str]]:
    return _devices("output")


def find_cable_input() -> tuple[int, str] | None:
    for idx, name in list_output_devices():
        if "cable input" in name.lower():
            return idx, name
    return None


def cable_installed() -> bool:
    try:
        for dev in sd.query_devices():
            if "cable" in dev["name"].lower():
                return True
    except Exception:
        return False
    return False


def default_input() -> int | None:
    wasapi = _wasapi_index()
    if wasapi is not None:
        try:
            idx = sd.query_hostapis(wasapi)["default_input_device"]
            if idx is not None and idx >= 0:
                return int(idx)
        except Exception:
            pass
    try:
        idx = sd.default.device[0]
        if idx is not None and idx >= 0:
            return int(idx)
    except Exception:
        pass
    devices = list_input_devices()
    return devices[0][0] if devices else None


class RingBuffer:
    def __init__(self, capacity: int, max_samples: int | None = None):
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._cap = capacity
        self._max = min(max_samples or capacity, capacity)
        self._read = 0
        self._write = 0
        self._size = 0
        self._lock = threading.Lock()

    def push(self, data: np.ndarray) -> None:
        n = data.size
        if n == 0:
            return
        if n > self._cap:
            data = data[-self._cap:]
            n = data.size
        with self._lock:
            free = self._cap - self._size
            if n > free:
                drop = min(n - free, self._size)
                self._read = (self._read + drop) % self._cap
                self._size -= drop
            first = min(n, self._cap - self._write)
            self._buf[self._write:self._write + first] = data[:first]
            if first < n:
                self._buf[:n - first] = data[first:]
            self._write = (self._write + n) % self._cap
            self._size += n
            # keep latency bounded when input/output clocks drift apart
            if self._size > self._max:
                drop = self._size - self._max
                self._read = (self._read + drop) % self._cap
                self._size -= drop

    def pop(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        with self._lock:
            if self._size == 0:
                return out
            take = min(n, self._size)
            first = min(take, self._cap - self._read)
            out[:first] = self._buf[self._read:self._read + first]
            if first < take:
                out[first:take] = self._buf[:take - first]
            self._read = (self._read + take) % self._cap
            self._size -= take
        return out

    def fill(self) -> float:
        with self._lock:
            return self._size / self._cap

    def size(self) -> int:
        with self._lock:
            return self._size

    def clear(self) -> None:
        with self._lock:
            self._read = 0
            self._write = 0
            self._size = 0
            self._buf[:] = 0.0


class AudioEngine:
    """Mic -> selected denoiser -> cable (or any output device)."""

    def __init__(self, input_device: int, output_device: int, mix: float = 1.0,
                 denoiser: str = "rnnoise", aec: bool = False):
        self.input_device = input_device
        self.output_device = output_device
        self.denoiser_name = "rnnoise"
        self.denoiser_error: str | None = None
        self.denoiser: Denoiser | None = None
        self.aec_enabled = bool(aec)
        self.aec_active = False
        self.aec_error: str | None = None
        self.aec_device = ""
        self._aec: EchoCanceller | None = None
        self._loopback: LoopbackCapture | None = None
        self._aec_lock = threading.Lock()
        self._dfn3_mix = float(np.clip(mix, 0.0, 1.0))
        self._dfn3_thread: threading.Thread | None = None
        self._dfn3_queue: queue.Queue | None = None
        self._dfn3_stop = threading.Event()
        self._dfn3_ready = threading.Event()
        if denoiser == "dfn3":
            if dfn3.available():
                self.denoiser_name = "dfn3"
            else:
                self.denoiser = Denoiser(mix)
                self.denoiser_error = "DFN3 không khả dụng, dùng RNNoise."
        else:
            self.denoiser = Denoiser(mix)
        self._input_stream = None
        self._output_stream = None
        self._ring = RingBuffer(SAMPLE_RATE * 2, MAX_BUFFER_BLOCKS * BLOCK)
        self._pending = np.zeros(0, dtype=np.float32)
        self._in_resampler = None
        self._out_resampler = None
        self._in_rate = SAMPLE_RATE
        self._out_rate = SAMPLE_RATE
        self._running = False
        self._level = 0.0
        self._input_level = 0.0
        self._speech = 0.0
        self.muted = False
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def level(self) -> float:
        return self._level

    @property
    def input_level(self) -> float:
        return self._input_level

    @property
    def speech_prob(self) -> float:
        return self._speech

    def set_mix(self, value: float) -> None:
        value = float(np.clip(value, 0.0, 1.0))
        if self.denoiser is not None:
            self.denoiser.mix = value
        else:
            self._dfn3_mix = value

    def _dfn3_loop(self) -> None:
        state = None
        try:
            state = DFN3Denoiser(self._dfn3_mix)
            self._dfn3_ready.set()
            while not self._dfn3_stop.is_set():
                try:
                    block = self._dfn3_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                state.mix = self._dfn3_mix
                try:
                    out = state.process(block)
                except BaseException as exc:
                    self.error = f"DFN3: {exc}"
                    break
                if self.muted:
                    out = np.zeros_like(out)
                    self._level = 0.0
                else:
                    self._level = state.level
                self._speech = 0.0
                self._ring.push(out)
        except BaseException as exc:
            self.denoiser_error = f"DFN3 không khả dụng: {exc}"
        finally:
            if state is not None:
                try:
                    state.close()
                except Exception:
                    pass
            self._dfn3_ready.set()

    def _start_dfn3_worker(self) -> None:
        self._dfn3_stop.clear()
        self._dfn3_ready.clear()
        self.denoiser_error = None
        self._dfn3_queue = queue.Queue(maxsize=32)
        self._dfn3_thread = threading.Thread(
            target=self._dfn3_loop, name="noisecut-dfn3", daemon=True)
        self._dfn3_thread.start()
        if not self._dfn3_ready.wait(10.0):
            self.stop()
            raise RuntimeError("DFN3 load timeout")
        if self.denoiser_error:
            message = self.denoiser_error
            self.stop()
            raise RuntimeError(message)

    def _stop_dfn3_worker(self) -> None:
        thread = self._dfn3_thread
        if thread is None:
            return
        self._dfn3_stop.set()
        thread.join(timeout=5.0)
        self._dfn3_thread = None
        self._dfn3_queue = None

    def _pick_rate(self, device: int, kind: str) -> int:
        default_rate = SAMPLE_RATE
        try:
            default_rate = int(round(sd.query_devices(device)["default_samplerate"]))
        except Exception:
            pass
        try:
            if kind == "input":
                sd.check_input_settings(device=device, samplerate=SAMPLE_RATE,
                                        channels=1, dtype="float32")
            else:
                info = sd.query_devices(device)
                channels = min(2, max(1, int(info["max_output_channels"])))
                sd.check_output_settings(device=device, samplerate=SAMPLE_RATE,
                                         channels=channels, dtype="float32")
            return SAMPLE_RATE
        except Exception:
            return default_rate

    def set_aec(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.aec_enabled = enabled
        if not enabled:
            self._cleanup_aec()
            self.aec_error = None
            return
        if not self._running:
            return
        if self._aec is not None and self._loopback is not None:
            self.aec_active = True
            self.aec_error = None
            return
        self._start_aec()
        if not self._running or not self.aec_enabled:
            self._cleanup_aec()
            return
        if self._loopback is not None:
            self._loopback.clear()

    def _start_aec(self) -> None:
        if not self.aec_enabled:
            self.aec_active = False
            self.aec_error = None
            self.aec_device = ""
            return
        loop = None
        try:
            loop = LoopbackCapture(BLOCK, SAMPLE_RATE)
            loop.start()
            source = (loop.source_name or "").replace("[Loopback]", "").strip()
            try:
                out_name = str(sd.query_devices(self.output_device)["name"]).strip()
            except Exception:
                out_name = ""
            if out_name and source and source.lower() == out_name.lower():
                raise LoopbackError(
                    "đầu ra của app trùng thiết bị phát mặc định")
            aec = EchoCanceller()
            with self._aec_lock:
                self._aec = aec
                self._loopback = loop
            self.aec_active = True
            self.aec_device = loop.source_name
            self.aec_error = None
        except Exception as exc:
            if loop is not None:
                loop.stop()
            self._aec = None
            self._loopback = None
            self.aec_active = False
            self.aec_error = f"Không bật khử vọng: {exc}"

    def _cleanup_aec(self) -> None:
        self.aec_active = False
        with self._aec_lock:
            loop = self._loopback
            self._loopback = None
            aec = self._aec
            self._aec = None
        if loop is not None:
            try:
                loop.stop()
            except Exception:
                pass
        if aec is not None:
            try:
                aec.close()
            except Exception:
                pass

    def _cancel_echo(self, block: np.ndarray) -> None:
        if not self.aec_active:
            return
        with self._aec_lock:
            loop = self._loopback
            aec = self._aec
            if loop is None or aec is None:
                return
            try:
                for i in range(0, block.size, BLOCK):
                    chunk = block[i:i + BLOCK]
                    if chunk.size != BLOCK:
                        break
                    chunk[:] = aec.cancel(chunk, loop.read(BLOCK))
            except Exception as exc:
                self.aec_error = f"Khử vọng: {exc}"
                self.aec_active = False

    def _input_callback(self, indata, frames, time_info, status):
        try:
            mono = indata[:, 0].astype(np.float32, copy=False)
            if self._in_resampler is not None:
                mono = self._in_resampler.resample_chunk(mono)
            if mono.size == 0:
                return
            self._input_level = float(np.sqrt(np.mean(mono * mono)))
            if self._pending.size:
                mono = np.concatenate((self._pending, mono))
            n_full = (mono.size // BLOCK) * BLOCK
            if n_full:
                block = mono[:n_full]
                self._pending = mono[n_full:].copy()
                if self.aec_active:
                    self._cancel_echo(block)
                worker = self._dfn3_thread
                if worker is not None and worker.is_alive() and self._dfn3_queue is not None:
                    if self.muted:
                        self._ring.push(np.zeros(n_full, dtype=np.float32))
                        self._level = 0.0
                        self._speech = 0.0
                    else:
                        for i in range(0, n_full, BLOCK):
                            try:
                                self._dfn3_queue.put_nowait(block[i:i + BLOCK].copy())
                            except queue.Full:
                                pass
                else:
                    if self.denoiser is None:
                        self._ring.push(np.zeros(n_full, dtype=np.float32))
                        self._level = 0.0
                        self._speech = 0.0
                    else:
                        out = np.empty(n_full, dtype=np.float32)
                        for i in range(0, n_full, BLOCK):
                            out[i:i + BLOCK] = self.denoiser.process(block[i:i + BLOCK])
                        if self.muted:
                            out[:] = 0.0
                            self._level = 0.0
                            self._speech = 0.0
                        else:
                            self._level = self.denoiser.level
                            self._speech = self.denoiser.speech_prob
                        self._ring.push(out)
            else:
                self._pending = mono.copy()
        except Exception as exc:  # keep callback alive
            self.error = f"input: {exc}"

    def _output_callback(self, outdata, frames, time_info, status):
        try:
            data = self._ring.pop(frames)
            if self._out_resampler is not None:
                data = self._out_resampler.resample_chunk(data)
                if data.size != frames:
                    data = np.resize(data, frames)
            outdata[:] = data[:, None]
        except Exception as exc:
            outdata.fill(0)
            self.error = f"output: {exc}"

    def start(self) -> None:
        if self._running:
            return
        self.error = None
        if self.denoiser_name == "dfn3":
            self._start_dfn3_worker()
        self._in_rate = self._pick_rate(self.input_device, "input")
        self._out_rate = self._pick_rate(self.output_device, "output")

        try:
            out_info = sd.query_devices(self.output_device)
            out_channels = min(2, max(1, int(out_info["max_output_channels"])))
        except Exception:
            out_channels = 2

        self._in_resampler = None
        if self._in_rate != SAMPLE_RATE:
            self._in_resampler = ResampleStream(
                self._in_rate, SAMPLE_RATE, 1, dtype="float32", quality="HQ")
        self._out_resampler = None
        if self._out_rate != SAMPLE_RATE:
            self._out_resampler = ResampleStream(
                SAMPLE_RATE, self._out_rate, 1, dtype="float32", quality="HQ")

        in_block = max(BLOCK, int(round(self._in_rate * 0.01)))
        out_block = max(BLOCK, int(round(self._out_rate * 0.01)))

        self._ring.clear()
        self._ring.push(np.zeros(BLOCK * TARGET_PREFILL_BLOCKS, dtype=np.float32))
        self._pending = np.zeros(0, dtype=np.float32)

        self._start_aec()

        try:
            self._input_stream = sd.InputStream(
                device=self.input_device,
                channels=1,
                samplerate=self._in_rate,
                blocksize=in_block,
                dtype="float32",
                callback=self._input_callback,
            )
            self._output_stream = sd.OutputStream(
                device=self.output_device,
                channels=out_channels,
                samplerate=self._out_rate,
                blocksize=out_block,
                dtype="float32",
                callback=self._output_callback,
            )
            self._input_stream.start()
            self._output_stream.start()
        except Exception:
            self.stop()
            raise
        if self._loopback is not None:
            self._loopback.clear()
        self._running = True

    def stop(self) -> None:
        self._running = False
        for stream in (self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._input_stream = None
        self._output_stream = None
        self._level = 0.0
        self._input_level = 0.0
        self._speech = 0.0
        self._ring.clear()
        self._cleanup_aec()
        self._stop_dfn3_worker()
        if self.denoiser is not None:
            self.denoiser.close()
