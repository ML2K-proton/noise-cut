"""WASAPI loopback capture of the default speaker (AEC far-end reference)."""

import threading

import numpy as np

SAMPLE_RATE = 48000
FRAME_SIZE = 480


class LoopbackError(RuntimeError):
    pass


class _Ring:
    def __init__(self, capacity: int, max_samples: int):
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._cap = capacity
        self._max = min(max_samples, capacity)
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
            if self._size > self._max:
                drop = self._size - self._max
                self._read = (self._read + drop) % self._cap
                self._size -= drop

    def read(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        with self._lock:
            take = min(n, self._size)
            if take == 0:
                return out
            first = min(take, self._cap - self._read)
            out[:first] = self._buf[self._read:self._read + first]
            if first < take:
                out[first:take] = self._buf[:take - first]
            self._read = (self._read + take) % self._cap
            self._size -= take
        return out

    def clear(self) -> None:
        with self._lock:
            self._read = 0
            self._write = 0
            self._size = 0
            self._buf[:] = 0.0


class LoopbackCapture:
    """Captures what the default Windows speaker is playing.

    PortAudio's WASAPI loopback produces no callbacks while the speaker is
    silent; the consumer simply reads zeros during those gaps, which is what
    AEC needs anyway.
    """

    def __init__(self, frame_size: int = FRAME_SIZE,
                 sample_rate: int = SAMPLE_RATE):
        self.frame_size = int(frame_size)
        self.sample_rate = int(sample_rate)
        self.error: str | None = None
        self._ring = _Ring(sample_rate * 2, sample_rate // 5)
        self._pa = None
        self._stream = None
        self._channels = 1
        self._rate = sample_rate
        self._resampler = None
        self.source_name = ""
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        try:
            import pyaudiowpatch as pa
        except Exception as exc:
            raise LoopbackError("thiếu PyAudioWPatch") from exc

        audio = pa.PyAudio()
        try:
            info = audio.get_default_wasapi_loopback()
        except Exception as exc:
            audio.terminate()
            raise LoopbackError(
                "không tìm thấy thiết bị phát mặc định (WASAPI)") from exc

        name = str(info.get("name", ""))
        if "cable" in name.lower():
            audio.terminate()
            raise LoopbackError(
                "thiết bị phát mặc định là CABLE; hãy chọn loa/tai nghe "
                "làm đầu ra mặc định của Windows")

        rate = int(round(float(info.get("defaultSampleRate") or self.sample_rate)))
        channels = max(1, int(info.get("maxInputChannels") or 1))
        resampler = None
        if rate != self.sample_rate:
            try:
                from soxr import ResampleStream
                resampler = ResampleStream(
                    rate, self.sample_rate, 1, dtype="float32", quality="HQ")
            except Exception as exc:
                audio.terminate()
                raise LoopbackError("không khởi tạo được resampler") from exc

        self._channels = channels
        self._rate = rate
        self._resampler = resampler
        self.source_name = name
        self.error = None

        frames = max(1, int(round(rate * 0.01)))
        try:
            stream = audio.open(
                format=pa.paFloat32,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=int(info["index"]),
                frames_per_buffer=frames,
                stream_callback=self._make_callback(pa),
            )
            stream.start_stream()
        except Exception as exc:
            audio.terminate()
            raise LoopbackError(f"không mở được loopback: {exc}") from exc

        self._pa = audio
        self._stream = stream
        self._running = True

    def _make_callback(self, pa):
        def callback(in_data, frame_count, time_info, status):
            try:
                data = np.frombuffer(in_data, dtype=np.float32)
                if self._channels > 1:
                    data = data.reshape(-1, self._channels).mean(axis=1)
                if self._resampler is not None:
                    data = self._resampler.resample_chunk(data)
                self._ring.push(data)
            except Exception as exc:
                self.error = str(exc)
            return (None, pa.paContinue)
        return callback

    def read(self, n: int) -> np.ndarray:
        return self._ring.read(n)

    def clear(self) -> None:
        self._ring.clear()

    def stop(self) -> None:
        self._running = False
        stream = self._stream
        audio = self._pa
        self._stream = None
        self._pa = None
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if audio is not None:
            try:
                audio.terminate()
            except Exception:
                pass
        self._ring.clear()
