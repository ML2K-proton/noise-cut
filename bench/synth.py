import math

import numpy as np
from scipy import signal

SR = 48000
DURATION = 5.0


def rms(x):
    x = np.asarray(x, dtype=np.float32)
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def normalize(x, level=0.05, peak=0.95):
    x = np.asarray(x, dtype=np.float32)
    x = x - float(np.mean(x))
    current = rms(x)
    if current > 1e-8:
        x = x * (level / current)
    top = float(np.max(np.abs(x))) if x.size else 0.0
    if top > peak:
        x = x * (peak / top)
    return x.astype(np.float32)


def _sos(low, high, order=4):
    if low and high:
        return signal.butter(order, [low, high], btype="bandpass", fs=SR, output="sos")
    if low:
        return signal.butter(order, low, btype="highpass", fs=SR, output="sos")
    return signal.butter(order, high, btype="lowpass", fs=SR, output="sos")


def filtered_noise(n, low=None, high=None, rng=None, order=4):
    rng = rng or np.random.default_rng(0)
    x = rng.standard_normal(n).astype(np.float32)
    return signal.sosfilt(_sos(low, high, order), x).astype(np.float32)


def pink_noise(n, rng=None):
    rng = rng or np.random.default_rng(0)
    size = 1 << int(math.ceil(math.log2(max(n, 2))))
    spec = np.fft.rfft(rng.standard_normal(size))
    freqs = np.fft.rfftfreq(size, 1.0 / SR)
    spec[0] = 0
    spec[1:] /= np.sqrt(freqs[1:])
    y = np.fft.irfft(spec, size)[:n]
    return normalize(y, 1.0)


def brown_noise(n, rng=None):
    rng = rng or np.random.default_rng(0)
    y = np.cumsum(rng.standard_normal(n))
    y = signal.sosfilt(_sos(20, 900), y)
    return normalize(y, 1.0)


def hum(n, base=50.0, rng=None):
    rng = rng or np.random.default_rng(0)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for h, amp in ((1, 1.0), (2, 0.45), (3, 0.25), (5, 0.12)):
        y += amp * np.sin(2 * np.pi * base * h * t + rng.uniform(0, 2 * np.pi))
    return normalize(y, 0.05)


def _env_click(n, start, length, decay, rng):
    t = np.arange(n) / SR
    rel = t - start
    mask = (rel >= 0) & (rel < length)
    if not np.any(mask):
        return np.zeros(n, dtype=np.float32)
    local = rel[mask]
    env = (1 - np.exp(-local / 0.002)) * np.exp(-local / decay)
    click = filtered_noise(int(mask.sum()), 1200, 7000, rng) * env
    out = np.zeros(n, dtype=np.float32)
    out[mask] = click.astype(np.float32)
    return out


def fan_noise(n, rng=None):
    rng = rng or np.random.default_rng(1)
    t = np.arange(n) / SR
    base = 0.75 * pink_noise(n, rng) + 0.25 * filtered_noise(n, 40, 1200, rng)
    base *= 1.0 + 0.12 * np.sin(2 * np.pi * 23 * t + 0.3)
    base += 0.35 * hum(n, 50, rng)
    return normalize(base, 0.08)


def keyboard_noise(n, rng=None):
    rng = rng or np.random.default_rng(2)
    y = np.zeros(n, dtype=np.float32)
    start = 0.2
    while start < n / SR - 0.1:
        length = 0.06 + rng.uniform(0, 0.03)
        y += _env_click(n, start, length, 0.012 + rng.uniform(0, 0.012), rng)
        if rng.random() < 0.8:
            y += 0.6 * _env_click(n, min(start + length, n / SR - 0.1), 0.03, 0.01, rng)
        start += rng.uniform(0.12, 0.55)
    return normalize(y, 0.08)


def mouse_noise(n, rng=None):
    rng = rng or np.random.default_rng(3)
    y = np.zeros(n, dtype=np.float32)
    for start in (0.7, 2.3, 4.1):
        y += _env_click(n, start, 0.035, 0.006, rng)
    return normalize(y, 0.08)


def traffic_noise(n, rng=None):
    rng = rng or np.random.default_rng(4)
    t = np.arange(n) / SR
    base = 0.8 * brown_noise(n, rng) + 0.35 * filtered_noise(n, 80, 700, rng)
    passing = filtered_noise(n, 100, 1400, rng)
    env = np.exp(-((t - 2.4) / 0.55) ** 2) + 0.7 * np.exp(-((t - 4.2) / 0.35) ** 2)
    base += 0.6 * passing * env
    return normalize(base, 0.08)


def rain_noise(n, rng=None):
    rng = rng or np.random.default_rng(5)
    y = 0.55 * filtered_noise(n, 700, None, rng) + 0.3 * pink_noise(n, rng)
    for start in rng.uniform(0.1, n / SR - 0.1, 80):
        y += 0.5 * _env_click(n, float(start), 0.02, 0.004, rng)
    return normalize(y, 0.08)


def wind_noise(n, rng=None):
    rng = rng or np.random.default_rng(6)
    t = np.arange(n) / SR
    y = filtered_noise(n, 30, 650, rng)
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 0.16 * t + 0.8) ** 2
    return normalize(y * env, 0.08)


def babble_noise(speech, n, rng=None):
    rng = rng or np.random.default_rng(7)
    y = np.zeros(n, dtype=np.float32)
    picks = rng.choice(len(speech), size=min(3, len(speech)), replace=False)
    for idx, pick in enumerate(picks):
        src = np.asarray(speech[int(pick)], dtype=np.float32)
        if src.size < n:
            src = np.tile(src, int(np.ceil(n / src.size)))
        offset = int(rng.integers(0, max(1, src.size - 1)))
        src = np.roll(src, offset)[:n]
        factor = (0.9, 1.0, 1.1)[idx % 3]
        src = signal.resample_poly(src, int(round(factor * 100)), 100)[:n]
        if src.size < n:
            src = np.pad(src, (0, n - src.size))
        y += src * (0.9 / (idx + 1))
    y += 0.12 * pink_noise(n, rng)
    return normalize(y, 0.08)


def dog_noise(n, rng=None):
    rng = rng or np.random.default_rng(8)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for start, amp in ((1.0, 1.0), (1.55, 0.75), (3.7, 0.9)):
        rel = t - start
        env = np.exp(-np.clip(rel, 0, None) / 0.12) * (rel >= 0) * (rel < 0.6)
        formant = np.sin(2 * np.pi * (420 - 180 * np.clip(rel, 0, 0.4)) * rel)
        noise = filtered_noise(n, 250, 1800, rng)
        y += amp * env * (0.55 * noise + 0.45 * formant)
    return normalize(y, 0.08)


def baby_noise(n, rng=None):
    rng = rng or np.random.default_rng(9)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for start, length, base in ((1.0, 1.4, 430), (3.8, 1.2, 500)):
        rel = t - start
        active = (rel >= 0) & (rel < length)
        f0 = base + 35 * np.sin(2 * np.pi * 4.2 * rel)
        phase = 2 * np.pi * np.cumsum(f0) / SR
        tone = sum(np.sin(h * phase) / h for h in range(1, 7))
        env = np.exp(-((rel - length / 2) / (length / 2.5)) ** 4) * active
        y += 0.35 * tone * env
    y += 0.08 * filtered_noise(n, 300, 3000, rng)
    return normalize(y, 0.08)


def construction_noise(n, rng=None):
    rng = rng or np.random.default_rng(10)
    t = np.arange(n) / SR
    y = 0.4 * filtered_noise(n, 30, 500, rng)
    for start in (0.5, 1.45, 2.4, 3.35, 4.3):
        rel = t - start
        env = np.exp(-np.clip(rel, 0, None) / 0.09) * (rel >= 0) * (rel < 0.5)
        y += 0.9 * env * filtered_noise(n, 50, 1200, rng)
    return normalize(y, 0.08)


def notification_noise(n, rng=None):
    rng = rng or np.random.default_rng(11)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for start, freq in ((0.6, 880), (2.6, 1100), (4.5, 1320)):
        rel = t - start
        active = (rel >= 0) & (rel < 0.35)
        env = np.exp(-np.clip(rel, 0, None) / 0.08) * active
        y += env * (np.sin(2 * np.pi * freq * rel) + 0.4 * np.sin(2 * np.pi * 2 * freq * rel))
    return normalize(y, 0.08)


def music_noise(n, rng=None):
    rng = rng or np.random.default_rng(12)
    t = np.arange(n) / SR
    notes = (220.0, 277.18, 329.63, 440.0, 329.63, 277.18)
    y = np.zeros(n, dtype=np.float32)
    for i, freq in enumerate(notes):
        start = i * 0.8
        rel = t - start
        active = (rel >= 0) & (rel < 1.1)
        env = np.exp(-np.clip(rel, 0, None) / 0.7) * active
        y += env * (np.sin(2 * np.pi * freq * rel) + 0.5 * np.sin(2 * np.pi * 2 * freq * rel))
    y += 0.25 * pink_noise(n, rng) + 0.1 * filtered_noise(n, 80, 2000, rng)
    return normalize(y, 0.08)


def cough_event(n, rng=None, sneeze=False):
    rng = rng or np.random.default_rng(13)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    if sneeze:
        specs = ((1.1, 0.28, 0.10, 1100, 7000), (3.5, 0.24, 0.08, 1400, 8000))
    else:
        specs = ((1.2, 0.42, 0.16, 220, 3500), (3.8, 0.38, 0.14, 260, 3000))
    for start, length, decay, low, high in specs:
        rel = t - start
        active = (rel >= 0) & (rel < length)
        env = (1 - np.exp(-np.clip(rel, 0, None) / 0.008)) * np.exp(-np.clip(rel, 0, None) / decay) * active
        burst = filtered_noise(n, low, high, rng)
        tone = np.sin(2 * np.pi * 300 * np.clip(rel, 0, None)) * 0.25
        y += env * (burst + tone)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0:
        y *= 0.95 / peak
    return y.astype(np.float32)


def reverb_rir(rng=None, decay=0.35):
    rng = rng or np.random.default_rng(14)
    length = int(0.7 * SR)
    t = np.arange(length) / SR
    rir = rng.standard_normal(length) * np.exp(-t / decay)
    rir[0] = 2.5
    rir[:int(0.006 * SR)] *= np.linspace(1.0, 0.2, int(0.006 * SR))
    return normalize(rir, 1.0, 1.0)


def add_event(n, event, start, gain):
    out = np.zeros(n, dtype=np.float32)
    left = int(start * SR)
    right = min(n, left + event.size)
    if right > left:
        out[left:right] = event[:right - left] * gain
    return out
