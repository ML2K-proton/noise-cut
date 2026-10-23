"""Synthetic acoustic echo cancellation benchmark for noisecut.aec."""

import os
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from noisecut.aec import EchoCanceller, FILTER_LENGTH  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEECH = os.path.join(ROOT, "bench", "speech", "david_01.wav")
NEAR = os.path.join(ROOT, "bench", "speech", "zira_01.wav")
SR = 48000
FRAME = 480


def load_audio(path: str, repeat: int = 1) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        import soxr
        audio = soxr.resample(audio, sr, SR)
    audio = audio / (float(np.max(np.abs(audio))) + 1e-9) * 0.5
    return np.tile(audio, repeat)


def load_speech() -> np.ndarray:
    return load_audio(SPEECH, 2)


def make_echo(clean: np.ndarray, delay_ms: float) -> np.ndarray:
    delay = int(SR * delay_ms / 1000.0)
    echo = np.zeros_like(clean)
    echo[delay:] = clean[:-delay] * 0.35
    if delay + 240 < clean.size:
        echo[delay + 240:] += clean[:-delay - 240] * 0.12
    return echo


def run(delay_ms: float, filter_length: int = FILTER_LENGTH) -> dict:
    clean = load_speech()
    echo = make_echo(clean, delay_ms)
    rng = np.random.default_rng(0)
    mic = echo + rng.normal(0, 0.002, size=clean.size).astype(np.float32)

    aec = EchoCanceller(filter_length=filter_length)
    out = np.zeros_like(mic)
    start = time.perf_counter()
    try:
        for i in range(0, mic.size - FRAME + 1, FRAME):
            out[i:i + FRAME] = aec.cancel(mic[i:i + FRAME], clean[i:i + FRAME])
    finally:
        aec.close()
    elapsed = time.perf_counter() - start

    lo = int(6.0 * SR)
    hi = min(int(8.0 * SR), mic.size)
    erle = 10.0 * np.log10(
        (float(np.mean(mic[lo:hi] ** 2)) + 1e-12)
        / (float(np.mean(out[lo:hi] ** 2)) + 1e-12))
    return {
        "delay_ms": delay_ms,
        "filter_ms": filter_length * 1000.0 / SR,
        "erle_db": erle,
        "rtf": elapsed / (mic.size / SR),
    }


def run_double_talk(delay_ms: float = 80.0,
                    filter_length: int = FILTER_LENGTH) -> dict:
    seg = 3 * SR
    n = 3 * seg
    far = np.resize(load_audio(SPEECH, 3), n)
    near = np.resize(load_audio(NEAR, 2), n)
    echo = make_echo(far, delay_ms)
    ref = np.zeros(n, dtype=np.float32)
    mic = np.zeros(n, dtype=np.float32)
    ref[:seg] = far[:seg]
    mic[:seg] = echo[:seg]
    mic[seg:2 * seg] = near[seg:2 * seg]
    ref[2 * seg:] = far[2 * seg:]
    mic[2 * seg:] = echo[2 * seg:] + near[2 * seg:] * 0.7

    aec = EchoCanceller(filter_length=filter_length)
    out = np.zeros_like(mic)
    try:
        for i in range(0, mic.size - FRAME + 1, FRAME):
            out[i:i + FRAME] = aec.cancel(mic[i:i + FRAME], ref[i:i + FRAME])
    finally:
        aec.close()

    far_seg = slice(seg - 2 * SR, seg)
    near_seg = slice(seg, 2 * seg)
    dt_seg = slice(2 * seg, n)
    erle = 10.0 * np.log10(
        (float(np.mean(mic[far_seg] ** 2)) + 1e-12)
        / (float(np.mean(out[far_seg] ** 2)) + 1e-12))
    near_ratio = float(
        np.sqrt(np.mean(out[near_seg] ** 2))
        / (np.sqrt(np.mean(mic[near_seg] ** 2)) + 1e-12))
    dt_ratio = float(
        np.sqrt(np.mean(out[dt_seg] ** 2))
        / (np.sqrt(np.mean(mic[dt_seg] ** 2)) + 1e-12))
    return {
        "delay_ms": delay_ms,
        "erle_db": erle,
        "near_ratio": near_ratio,
        "dt_ratio": dt_ratio,
    }


def main() -> None:
    rows = [run(delay) for delay in (40, 80, 150)]
    print("| Echo delay | Filter | ERLE | RTF |")
    print("|---:|---:|---:|---:|")
    for row in rows:
        print(f"| {row['delay_ms']:.0f} ms | {row['filter_ms']:.0f} ms "
              f"| {row['erle_db']:.1f} dB | {row['rtf']:.3f} |")

    talk = run_double_talk()
    print("\n| Case | Metric | Value |")
    print("|---|---|---:|")
    print(f"| far-only ({talk['delay_ms']:.0f} ms) | ERLE "
          f"| {talk['erle_db']:.1f} dB |")
    print(f"| near-only | RMS ratio | {talk['near_ratio']:.2f} |")
    print(f"| double-talk | RMS ratio | {talk['dt_ratio']:.2f} |")


if __name__ == "__main__":
    main()
