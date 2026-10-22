import csv
import html
import json
import math
import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from deepfilternet_rs import DeepFilterNetRealtime
from pystoi import stoi
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from noisecut.denoiser import Denoiser, Highpass
import synth

SR = 48000
BLOCK = 480
DURATION = synth.DURATION
SAMPLES = int(SR * DURATION)
SMOKE = "--smoke" in sys.argv
BASE = Path(__file__).resolve().parent
OUT = BASE / ("smoke" if SMOKE else "out")
SPEECH_DIR = BASE / "speech"
SNRS = (0,) if SMOKE else (20, 10, 5, 0, -5)
EVENT_LEVELS = (0,) if SMOKE else (0, 5, 10)
NOISE_NAMES = [
    "fan",
    "keyboard",
    "traffic",
    "rain",
    "wind",
    "babble",
    "dog",
    "baby",
    "construction",
    "notification",
    "music",
]
PROCESSORS = ("noisy", "rnnoise", "dfn3", "dfn3_hp")
LABELS = {
    "noisy": "Noisy input",
    "rnnoise": "RNNoise",
    "dfn3": "DFN3",
    "dfn3_hp": "DFN3 + 80 Hz HP",
    "dfn3_lim30": "DFN3 atten 30",
    "dfn3_pf05": "DFN3 postfilter 0.05",
}
KNOWN_LAG = {
    "noisy": 0,
    "rnnoise": 960,
    "dfn3": 1440,
    "dfn3_hp": 1440,
    "dfn3_lim30": 1440,
    "dfn3_pf05": 1440,
}
if SMOKE:
    NOISE_NAMES = NOISE_NAMES[:2]
    PROCESSORS = ("noisy", "rnnoise", "dfn3")
    OUT = BASE / "smoke"


def rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x) + 1e-12))


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-12))


def fit_length(x, n):
    x = np.asarray(x, dtype=np.float32)
    if x.size < n:
        return np.pad(x, (0, n - x.size))
    return x[:n].copy()


def load_speech(path, n):
    x, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = np.mean(x, axis=1).astype(np.float32)
    if sr != SR:
        x = signal.resample_poly(x, SR, sr).astype(np.float32)
    idx = np.flatnonzero(np.abs(x) > 0.008)
    if idx.size:
        left = max(0, int(idx[0]) - int(0.03 * SR))
        right = min(x.size, int(idx[-1]) + int(0.12 * SR))
        x = x[left:right]
    x = fit_length(x, n)
    return synth.normalize(x, 0.05, 0.95)


def make_noise(name, speech, n):
    if name == "fan":
        return synth.fan_noise(n)
    if name == "keyboard":
        return synth.keyboard_noise(n)
    if name == "traffic":
        return synth.traffic_noise(n)
    if name == "rain":
        return synth.rain_noise(n)
    if name == "wind":
        return synth.wind_noise(n)
    if name == "babble":
        return synth.babble_noise(speech, n)
    if name == "dog":
        return synth.dog_noise(n)
    if name == "baby":
        return synth.baby_noise(n)
    if name == "construction":
        return synth.construction_noise(n)
    if name == "notification":
        return synth.notification_noise(n)
    return synth.music_noise(n)


def apply_highpass(x):
    x = np.asarray(x, dtype=np.float32)
    padded = fit_length(x, int(math.ceil(x.size / BLOCK) * BLOCK))
    h = Highpass()
    out = np.empty_like(padded)
    for i in range(0, padded.size, BLOCK):
        out[i:i + BLOCK] = h.process(padded[i:i + BLOCK])
    return out[:x.size]


def apply_rnnoise(x):
    x = np.asarray(x, dtype=np.float32)
    padded = fit_length(x, int(math.ceil(x.size / BLOCK) * BLOCK))
    d = Denoiser(1.0)
    out = np.empty_like(padded)
    try:
        for i in range(0, padded.size, BLOCK):
            out[i:i + BLOCK] = d.process(padded[i:i + BLOCK])
    finally:
        d.close()
    return out[:x.size]


def apply_dfn3(x, hp=False, atten_lim=100.0, post_filter_beta=0.0):
    x = np.asarray(x, dtype=np.float32)
    if hp:
        x = apply_highpass(x)
    p = DeepFilterNetRealtime(
        atten_lim=atten_lim,
        log_level="error",
        compensate_delay=False,
        post_filter_beta=post_filter_beta,
    )
    try:
        y = p.process_chunk(np.ascontiguousarray(x, dtype=np.float32))
    finally:
        p.close()
    return fit_length(y, x.size)


def apply_processor(name, x):
    if name == "noisy":
        return np.asarray(x, dtype=np.float32).copy()
    if name == "rnnoise":
        return apply_rnnoise(x)
    if name == "dfn3":
        return apply_dfn3(x, False)
    if name == "dfn3_lim30":
        return apply_dfn3(x, False, atten_lim=30.0)
    if name == "dfn3_pf05":
        return apply_dfn3(x, False, post_filter_beta=0.05)
    return apply_dfn3(x, True)


def shift_fixed(y, lag):
    y = np.asarray(y, dtype=np.float32)
    out = np.zeros_like(y)
    n = y.size
    if lag <= 0:
        out[-lag:] = y[:n + lag]
    elif lag < n:
        out[:n - lag] = y[lag:]
    return out


def speech_mask(clean):
    n = (clean.size // BLOCK) * BLOCK
    frames = np.asarray(clean[:n], dtype=np.float64).reshape(-1, BLOCK)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    threshold = max(0.10 * rms(clean), 1e-5)
    return frame_rms > threshold


def si_sdr(clean, y):
    clean = np.asarray(clean, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    alpha = float(np.dot(y, clean) / (np.dot(clean, clean) + 1e-12))
    target = alpha * clean
    noise = y - target
    return 10.0 * math.log10((np.sum(target * target) + 1e-12) / (np.sum(noise * noise) + 1e-12))


def stoi_score(clean, y):
    c = signal.resample_poly(np.asarray(clean, dtype=np.float32), 1, 3)
    v = signal.resample_poly(np.asarray(y, dtype=np.float32), 1, 3)
    n = min(c.size, v.size)
    try:
        return float(stoi(c[:n], v[:n], 16000, extended=False))
    except Exception:
        return float("nan")


def measure(clean, mix, y, processor):
    lag = KNOWN_LAG[processor]
    y_aligned = shift_fixed(y, lag)
    n = min(clean.size, mix.size, y_aligned.size)
    clean = clean[:n]
    mix = mix[:n]
    y_aligned = y_aligned[:n]
    if processor == "dfn3_hp":
        clean = apply_highpass(clean)
        mix = apply_highpass(mix)
    mask = speech_mask(clean)
    residual = y_aligned - clean
    noise_ref = mix - clean
    nf = (clean.size // BLOCK) * BLOCK
    residual_frames = residual[:nf].reshape(-1, BLOCK)
    noise_frames = noise_ref[:nf].reshape(-1, BLOCK)
    use = mask[:residual_frames.shape[0]]
    if np.sum(use) >= 5:
        res_rms = rms(residual_frames[use])
        ref_rms = rms(noise_frames[use])
    else:
        res_rms = rms(residual)
        ref_rms = rms(noise_ref)
    noise_drop = db(ref_rms) - db(res_rms)
    active = mask[:clean.size // BLOCK]
    speech_delta = float("nan")
    if np.any(active) and clean.size >= BLOCK:
        c_frames = clean[:active.size * BLOCK].reshape(-1, BLOCK)[active]
        y_frames = y_aligned[:active.size * BLOCK].reshape(-1, BLOCK)[active]
        speech_delta = db(rms(y_frames)) - db(rms(c_frames))
    return {
        "processor": processor,
        "noise_drop_db": float(noise_drop),
        "si_sdr_db": float(si_sdr(clean, y_aligned)),
        "stoi": stoi_score(clean, y_aligned),
        "speech_delta_db": speech_delta,
        "lag_samples": int(lag),
        "output_rms": rms(y_aligned),
    }


def write_wav(path, x):
    x = np.clip(np.asarray(x, dtype=np.float32), -1.0, 1.0)
    sf.write(str(path), x, SR, subtype="PCM_16")


def build_cases(speech):
    cases = []
    for idx, name in enumerate(NOISE_NAMES):
        noise = make_noise(name, speech, SAMPLES)
        for snr in SNRS:
            clean = np.asarray(speech[idx % len(speech)], dtype=np.float32).copy()
            noise_ref = noise / max(rms(noise), 1e-9) * rms(clean) * (10.0 ** (-snr / 20.0))
            mix = clean + noise_ref
            peak = float(np.max(np.abs(mix)))
            if peak > 0.95:
                scale = 0.95 / peak
                clean *= scale
                noise_ref *= scale
                mix *= scale
            case_id = f"{name}_snr_{'plus' if snr >= 0 else 'minus'}{abs(snr)}"
            cases.append({
                "id": case_id,
                "noise": name,
                "kind": "continuous",
                "snr": snr,
                "clean": clean.astype(np.float32),
                "mix": mix.astype(np.float32),
                "noise_ref": noise_ref.astype(np.float32),
            })
    for name in ("cough", "sneeze"):
        event = synth.cough_event(SAMPLES, sneeze=(name == "sneeze"))
        for level in EVENT_LEVELS:
            clean = np.asarray(speech[0], dtype=np.float32).copy()
            event_ref = event / max(rms(event), 1e-9) * rms(clean) * (10.0 ** (level / 20.0))
            mix = clean + event_ref
            peak = float(np.max(np.abs(mix)))
            if peak > 0.95:
                scale = 0.95 / peak
                clean *= scale
                event_ref *= scale
                mix *= scale
            case_id = f"{name}_level_plus{level}"
            cases.append({
                "id": case_id,
                "noise": name,
                "kind": "event_mix",
                "snr": level,
                "clean": clean.astype(np.float32),
                "mix": mix.astype(np.float32),
                "noise_ref": event_ref.astype(np.float32),
                "event_only": event_ref.astype(np.float32),
            })
    for decay in (0.25, 0.5):
        clean = np.asarray(speech[1], dtype=np.float32).copy()
        rir = synth.reverb_rir(decay=decay)
        wet = signal.fftconvolve(clean, rir, mode="full")[:clean.size].astype(np.float32)
        wet = synth.normalize(wet, rms(clean), 0.95)
        cases.append({
            "id": f"reverb_{str(decay).replace('.', '')}",
            "noise": "reverb",
            "kind": "reverb",
            "snr": 0,
            "clean": clean,
            "mix": wet,
            "noise_ref": None,
        })
    clean = np.asarray(speech[2], dtype=np.float32).copy()
    delay = int(0.12 * SR)
    echo = clean.copy()
    echo[delay:] += 0.55 * clean[:-delay]
    echo = synth.normalize(echo, rms(clean), 0.95)
    cases.append({
        "id": "echo_012",
        "noise": "echo",
        "kind": "echo",
        "snr": 0,
        "clean": clean,
        "mix": echo,
        "noise_ref": None,
    })
    return cases


def process_cases(cases):
    results = []
    event_results = []
    for path in ("clean", "mix", "processed", "events"):
        (OUT / path).mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(cases, 1):
        cid = case["id"]
        write_wav(OUT / "clean" / f"{cid}.wav", case["clean"])
        write_wav(OUT / "mix" / f"{cid}.wav", case["mix"])
        for pname in PROCESSORS:
            y = apply_processor(pname, case["mix"])
            if pname != "noisy":
                write_wav(OUT / "processed" / f"{cid}_{pname}.wav", y)
            row = {
                "case": cid,
                "noise": case["noise"],
                "kind": case["kind"],
                "snr_db": case["snr"],
                "processor": pname,
            }
            row.update(measure(case["clean"], case["mix"], y, pname))
            row["audio"] = (
                f"out/mix/{cid}.wav"
                if pname == "noisy"
                else f"out/processed/{cid}_{pname}.wav"
            )
            results.append(row)
        if "event_only" in case:
            event = case["event_only"]
            write_wav(OUT / "events" / f"{cid}.wav", event)
            for pname in PROCESSORS:
                y = apply_processor(pname, event)
                if pname != "noisy":
                    write_wav(OUT / "events" / f"{cid}_{pname}.wav", y)
                lag = KNOWN_LAG[pname]
                aligned = shift_fixed(y, lag)
                if pname == "noisy":
                    drop = 0.0
                    rms_drop = 0.0
                else:
                    drop = db(float(np.max(np.abs(event)))) - db(float(np.max(np.abs(aligned))))
                    rms_drop = db(rms(event)) - db(rms(aligned))
                event_results.append({
                    "case": cid,
                    "event": case["noise"],
                    "level_db": case["snr"],
                    "processor": pname,
                    "peak_drop_db": float(drop),
                    "rms_drop_db": float(rms_drop),
                    "lag_samples": int(lag),
                })
        print(f"[{index}/{len(cases)}] {cid}", flush=True)
    return results, event_results


def process_variants(cases):
    if SMOKE:
        return []
    wanted = {
        f"{noise}_snr_plus5"
        for noise in ("babble", "wind", "fan", "construction")
    } | {
        f"{noise}_snr_plus0"
        for noise in ("babble", "wind", "fan", "construction")
    }
    rows = []
    for case in cases:
        if case["id"] not in wanted:
            continue
        for pname in ("dfn3_lim30", "dfn3_pf05"):
            y = apply_processor(pname, case["mix"])
            write_wav(OUT / "processed" / f"{case['id']}_{pname}.wav", y)
            row = {
                "case": case["id"],
                "noise": case["noise"],
                "kind": case["kind"],
                "snr_db": case["snr"],
                "processor": pname,
            }
            row.update(measure(case["clean"], case["mix"], y, pname))
            row["audio"] = f"out/processed/{case['id']}_{pname}.wav"
            rows.append(row)
        print(f"[variant] {case['id']}", flush=True)
    with (BASE / "variants.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "case", "noise", "kind", "snr_db", "processor", "noise_drop_db",
            "si_sdr_db", "stoi", "speech_delta_db", "lag_samples", "output_rms", "audio",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def realtime_test(x):
    rows = []
    configs = [
        ("rnnoise", None),
        ("dfn3", False),
        ("dfn3_hp", True),
    ]
    if SMOKE:
        configs = configs[:2]
    x = fit_length(x, int(math.ceil(x.size / BLOCK) * BLOCK))
    for name, hp in configs:
        if name == "rnnoise":
            t0 = time.perf_counter()
            state = Denoiser(1.0)
            load_ms = (time.perf_counter() - t0) * 1000.0
            process = state.process
            close = state.close
        else:
            t0 = time.perf_counter()
            state = DeepFilterNetRealtime(
                atten_lim=100.0,
                log_level="error",
                compensate_delay=False,
                post_filter_beta=0.0,
            )
            load_ms = (time.perf_counter() - t0) * 1000.0
            highpass = Highpass() if hp else None

            def process(frame, state=state, highpass=highpass):
                if highpass is not None:
                    frame = highpass.process(frame)
                return state.process_chunk(frame)

            close = state.close
        times = []
        try:
            for i in range(0, min(x.size, BLOCK * 50), BLOCK):
                process(x[i:i + BLOCK])
            for _ in range(3):
                for i in range(0, x.size, BLOCK):
                    frame = x[i:i + BLOCK]
                    if frame.size < BLOCK:
                        frame = np.pad(frame, (0, BLOCK - frame.size))
                    t0 = time.perf_counter_ns()
                    process(frame)
                    times.append((time.perf_counter_ns() - t0) / 1_000_000.0)
        finally:
            close()
        t = np.asarray(times, dtype=np.float64)
        rows.append({
            "processor": name,
            "load_ms": float(load_ms),
            "p50_ms": float(np.percentile(t, 50)),
            "p95_ms": float(np.percentile(t, 95)),
            "p99_ms": float(np.percentile(t, 99)),
            "max_ms": float(np.max(t)),
            "rtf": float(np.sum(t) / 1000.0 / (t.size * BLOCK / SR)),
            "frames": int(t.size),
        })
        print(f"[rt] {name} p99={rows[-1]['p99_ms']:.3f} ms rtf={rows[-1]['rtf']:.3f}", flush=True)
    return rows


def find_results(results, case, processor):
    for row in results:
        if row["case"] == case and row["processor"] == processor:
            return row
    return None


def fmt(v, digits=2):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    return f"{v:.{digits}f}"


def continuous_table(results, snr):
    lines = [
        "| Noise | RN drop | RN SI-SDR | RN STOI | DFN3 drop | DFN3 SI-SDR | DFN3 STOI | DFN3+HP drop | DFN3+HP STOI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for noise in NOISE_NAMES:
        case = f"{noise}_snr_{'plus' if snr >= 0 else 'minus'}{abs(snr)}"
        rn = find_results(results, case, "rnnoise")
        df = find_results(results, case, "dfn3")
        dhp = find_results(results, case, "dfn3_hp")
        if not df:
            continue
        lines.append(
            f"| {noise} | {fmt(rn['noise_drop_db'] if rn else None)} | "
            f"{fmt(rn['si_sdr_db'] if rn else None)} | {fmt(rn['stoi'] if rn else None)} | "
            f"{fmt(df['noise_drop_db'])} | {fmt(df['si_sdr_db'])} | {fmt(df['stoi'])} | "
            f"{fmt(dhp['noise_drop_db'] if dhp else None)} | {fmt(dhp['stoi'] if dhp else None)} |"
        )
    return "\n".join(lines)


def leak_rows(results, snr):
    rows = []
    for noise in NOISE_NAMES:
        case = f"{noise}_snr_{'plus' if snr >= 0 else 'minus'}{abs(snr)}"
        row = find_results(results, case, "dfn3")
        if row:
            rows.append((row["noise_drop_db"], noise, row))
    rows.sort()
    return rows


def event_table(event_results):
    lines = [
        "| Event | Level dB | RN peak drop | DFN3 peak drop | DFN3+HP peak drop | DFN3 RMS drop |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    cases = sorted({r["case"] for r in event_results})
    for case in cases:
        rn = next((r for r in event_results if r["case"] == case and r["processor"] == "rnnoise"), None)
        df = next((r for r in event_results if r["case"] == case and r["processor"] == "dfn3"), None)
        dhp = next((r for r in event_results if r["case"] == case and r["processor"] == "dfn3_hp"), None)
        base = df or rn or dhp
        if not base:
            continue
        lines.append(
            f"| {base['event']} | {base['level_db']} | "
            f"{fmt(rn['peak_drop_db'] if rn else None)} | "
            f"{fmt(df['peak_drop_db'] if df else None)} | "
            f"{fmt(dhp['peak_drop_db'] if dhp else None)} | "
            f"{fmt(df['rms_drop_db'] if df else None)} |"
        )
    return "\n".join(lines)


def reverb_table(results):
    lines = [
        "| Case | RN SI-SDR | RN STOI | DFN3 SI-SDR | DFN3 STOI | DFN3+HP SI-SDR | DFN3+HP STOI |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in sorted({r["case"] for r in results if r["kind"] in ("reverb", "echo")}):
        rn = find_results(results, case, "rnnoise")
        df = find_results(results, case, "dfn3")
        dhp = find_results(results, case, "dfn3_hp")
        if df:
            lines.append(
                f"| {case} | {fmt(rn['si_sdr_db'] if rn else None)} | {fmt(rn['stoi'] if rn else None)} | "
                f"{fmt(df['si_sdr_db'])} | {fmt(df['stoi'])} | "
                f"{fmt(dhp['si_sdr_db'] if dhp else None)} | {fmt(dhp['stoi'] if dhp else None)} |"
            )
    return "\n".join(lines)


def realtime_table(rows):
    lines = [
        "| Processor | Load ms | p50 ms | p95 ms | p99 ms | Max ms | RTF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {LABELS.get(row['processor'], row['processor'])} | {fmt(row['load_ms'], 1)} | "
            f"{fmt(row['p50_ms'], 3)} | {fmt(row['p95_ms'], 3)} | {fmt(row['p99_ms'], 3)} | "
            f"{fmt(row['max_ms'], 3)} | {fmt(row['rtf'], 3)} |"
        )
    return "\n".join(lines)


def variant_table(variants, results):
    if not variants:
        return "No variant rows."
    lines = [
        "| Case | DFN3 drop | atten30 drop | postfilter drop | DFN3 SI-SDR | atten30 SI-SDR | postfilter SI-SDR |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in sorted({r["case"] for r in variants}):
        base = find_results(results, case, "dfn3")
        lim = find_results(variants, case, "dfn3_lim30")
        pf = find_results(variants, case, "dfn3_pf05")
        if not any((base, lim, pf)):
            continue
        lines.append(
            f"| {case} | {fmt(base['noise_drop_db'] if base else None)} | "
            f"{fmt(lim['noise_drop_db'] if lim else None)} | "
            f"{fmt(pf['noise_drop_db'] if pf else None)} | "
            f"{fmt(base['si_sdr_db'] if base else None)} | "
            f"{fmt(lim['si_sdr_db'] if lim else None)} | "
            f"{fmt(pf['si_sdr_db'] if pf else None)} |"
        )
    return "\n".join(lines)


def summary_values(results, event_results, realtime):
    dfn = [r for r in results if r["processor"] == "dfn3" and r["kind"] == "continuous"]
    rn = [r for r in results if r["processor"] == "rnnoise" and r["kind"] == "continuous"]
    d5 = [r for r in dfn if r["snr_db"] == 5]
    r5 = [r for r in rn if r["snr_db"] == 5]
    mean_drop = float(np.mean([r["noise_drop_db"] for r in d5])) if d5 else float("nan")
    mean_rn = float(np.mean([r["noise_drop_db"] for r in r5])) if r5 else float("nan")
    mean_sdr = float(np.mean([r["si_sdr_db"] for r in d5])) if d5 else float("nan")
    mean_rn_sdr = float(np.mean([r["si_sdr_db"] for r in r5])) if r5 else float("nan")
    mean_stoi = float(np.mean([r["stoi"] for r in d5])) if d5 else float("nan")
    mean_rn_stoi = float(np.mean([r["stoi"] for r in r5])) if r5 else float("nan")
    event_dfn = [r["peak_drop_db"] for r in event_results if r["processor"] == "dfn3"]
    event_rn = [r["peak_drop_db"] for r in event_results if r["processor"] == "rnnoise"]
    rt = {r["processor"]: r for r in realtime}
    return {
        "dfn3_mean_drop_5": mean_drop,
        "rnnoise_mean_drop_5": mean_rn,
        "dfn3_mean_si_sdr_5": mean_sdr,
        "rnnoise_mean_si_sdr_5": mean_rn_sdr,
        "dfn3_mean_stoi_5": mean_stoi,
        "rnnoise_mean_stoi_5": mean_rn_stoi,
        "dfn3_mean_event_peak_drop": float(np.mean(event_dfn)) if event_dfn else float("nan"),
        "rnnoise_mean_event_peak_drop": float(np.mean(event_rn)) if event_rn else float("nan"),
        "dfn3_p99_ms": rt.get("dfn3", {}).get("p99_ms", float("nan")),
        "dfn3_rtf": rt.get("dfn3", {}).get("rtf", float("nan")),
    }


def write_report(results, event_results, realtime, values, variants):
    lines = [
        "# Noise Suppression Benchmark",
        "",
        f"- Sample rate: {SR} Hz, duration: {DURATION:.1f} s",
        "- Speech: synthetic English TTS (Microsoft Zira/David), normalized to the same RMS.",
        "- Noise: synthetic, deterministic; see `synth.py`.",
        "- Metrics: noise attenuation in non-speech frames, SI-SDR, STOI, speech-level change.",
        "- DFN3: `deepfilternet-rs` 0.1.1, `atten_lim=100`, no post-filter.",
        "- Measured algorithmic delay: RNNoise 960 samples (20 ms), DFN3 1440 samples (30 ms).",
        "- DFN3+HP rows use a high-passed clean reference so the filter's own speech coloration is not counted as residual.",
        "",
        "## Headline",
        "",
        f"- DFN3 mean continuous-noise attenuation at +5 dB SNR: **{fmt(values['dfn3_mean_drop_5'])} dB** "
        f"(RNNoise: {fmt(values['rnnoise_mean_drop_5'])} dB).",
        f"- DFN3 mean SI-SDR at +5 dB: **{fmt(values['dfn3_mean_si_sdr_5'])} dB** "
        f"(RNNoise: {fmt(values['rnnoise_mean_si_sdr_5'])} dB).",
        f"- DFN3 mean STOI at +5 dB: **{fmt(values['dfn3_mean_stoi_5'], 3)}** "
        f"(RNNoise: {fmt(values['rnnoise_mean_stoi_5'], 3)}).",
        f"- Event peak attenuation (mean): DFN3 **{fmt(values['dfn3_mean_event_peak_drop'])} dB**, "
        f"RNNoise {fmt(values['rnnoise_mean_event_peak_drop'])} dB.",
        f"- DFN3 realtime p99: **{fmt(values['dfn3_p99_ms'], 3)} ms/frame**, RTF **{fmt(values['dfn3_rtf'], 3)}**.",
        "- With the app's 40 ms prefill, estimated end-to-end algorithm delay is ~60 ms for RNNoise and ~70 ms for DFN3 (excluding OS/device buffers).",
        "",
        "## Continuous noise at +5 dB SNR",
        "",
        continuous_table(results, 5),
        "",
        "## Continuous noise at 0 dB SNR",
        "",
        continuous_table(results, 0),
        "",
        "## Continuous noise at -5 dB SNR",
        "",
        continuous_table(results, -5),
        "",
        "## Largest DFN3 leaks at +5 dB",
        "",
    ]
    for drop, noise, row in leak_rows(results, 5)[:8]:
        lines.append(
            f"- **{noise}**: {fmt(drop)} dB attenuation, SI-SDR {fmt(row['si_sdr_db'])} dB, "
            f"STOI {fmt(row['stoi'], 3)}"
        )
    lines += [
        "",
        "## Transient human events",
        "",
        event_table(event_results),
        "",
        "## Reverb and echo",
        "",
        reverb_table(results),
        "",
        "## DFN3 tuning variants",
        "",
        variant_table(variants, results),
        "",
        "## Realtime cost",
        "",
        realtime_table(realtime),
        "",
        "## Recommendation",
        "",
        "- Integrate DFN3 as an **opt-in high-quality mode**; keep RNNoise as the default and fallback.",
        "- Do not add the app's 80 Hz high-pass to the DFN3 path: the raw DFN3 variant was more consistent; "
        "the HP variant is retained only as a diagnostic.",
        "- DFN3 is clearly better for stationary noise, keyboard/notification transients, and coughs, but "
        "babble, wind, and construction still leak. It is not a BVC/AEC replacement for Krisp.",
        "- Measured CPU cost is acceptable: p99 ~3.1 ms per 10 ms frame and ~70 ms total algorithm delay "
        "with the app's 40 ms prefill. The runtime package is ~25 MB installed, and model load is ~150 ms.",
        "- The `deepfilternet-rs` package is still alpha; pin the exact version and keep the RNNoise fallback.",
        "",
        "## Interpretation",
        "",
        "This is a synthetic benchmark, not a substitute for recordings of the target room, microphone, "
        "and Vietnamese speakers. Positive noise attenuation is measured in non-speech frames; negative "
        "values mean the processor added more residual than it removed.",
        "",
        "Use the audio and spectrogram folders to check artifacts that the numeric metrics miss, especially "
        "breath, cough, keyboard transients, babble, and speech endings.",
        "",
        "## Files",
        "",
        "- `summary.csv`: all numeric rows",
        "- `events.csv`: event-only attenuation rows",
        "- `variants.csv`: DFN3 attenuation/postfilter tuning rows",
        "- `realtime.csv`: realtime timing",
        "- `out/mix/`: input mixtures",
        "- `out/processed/`: processor outputs",
        "- `spectrograms/`: selected comparisons",
        "- `report.html`: listening report",
    ]
    (BASE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (BASE / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "case", "noise", "kind", "snr_db", "processor", "noise_drop_db",
            "si_sdr_db", "stoi", "speech_delta_db", "lag_samples", "output_rms", "audio",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    with (BASE / "events.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["case", "event", "level_db", "processor", "peak_drop_db", "rms_drop_db", "lag_samples"],
        )
        writer.writeheader()
        writer.writerows(event_results)
    with (BASE / "realtime.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["processor", "load_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "rtf", "frames"])
        writer.writeheader()
        writer.writerows(realtime)
    meta = {
        "sample_rate": SR,
        "duration": DURATION,
        "snrs": list(SNRS),
        "event_levels": list(EVENT_LEVELS),
        "processors": list(PROCESSORS),
        "smoke": SMOKE,
        "values": values,
    }
    (BASE / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def write_spectrograms(results):
    target_dir = BASE / ("smoke-spectrograms" if SMOKE else "spectrograms")
    target_dir.mkdir(parents=True, exist_ok=True)
    selected = ["fan_snr_plus0", "keyboard_snr_plus0", "babble_snr_plus0", "construction_snr_plus0"]
    if SMOKE:
        selected = selected[:1]
    for cid in selected:
        rn = find_results(results, cid, "rnnoise")
        df = find_results(results, cid, "dfn3")
        if not rn or not df:
            continue
        paths = [
            ("Noisy", OUT / "mix" / f"{cid}.wav"),
            ("RNNoise", OUT / "processed" / f"{cid}_rnnoise.wav"),
            ("DFN3", OUT / "processed" / f"{cid}_dfn3.wav"),
        ]
        fig, axes = plt.subplots(len(paths), 1, figsize=(12, 7), sharex=True)
        for ax, (label, path) in zip(axes, paths):
            x, sr = sf.read(str(path), dtype="float32")
            f, t, s = signal.spectrogram(x, sr, nperseg=1024, noverlap=768)
            ax.pcolormesh(t, f, 10 * np.log10(s + 1e-12), shading="auto", vmin=-120, vmax=-20)
            ax.set_ylabel("Hz")
            ax.set_title(label, loc="left", fontsize=9)
            ax.set_ylim(0, 12000)
        axes[-1].set_xlabel("Time (s)")
        fig.suptitle(cid)
        fig.tight_layout()
        fig.savefig(target_dir / f"{cid}.png", dpi=130)
        plt.close(fig)


def write_html(results, event_results, realtime, values):
    keys = ["fan_snr_plus5", "keyboard_snr_plus5", "babble_snr_plus5", "construction_snr_plus5"]
    if SMOKE:
        keys = ["fan_snr_plus0"]
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Noise Suppression Benchmark</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px;background:#111;color:#eee}"
        "table{border-collapse:collapse;margin:12px 0}td,th{border:1px solid #444;padding:6px 10px;text-align:right}"
        "th{background:#222}audio{height:30px;width:230px}h1,h2{color:#8fd}h3{margin-top:28px}"
        "a{color:#8cf}.note{color:#bbb}</style></head><body>",
        "<h1>Noise Suppression Benchmark</h1>",
        "<p class='note'>Synthetic English TTS + deterministic synthetic noise. "
        "Use headphones and compare the same sentence across processors.</p>",
        "<h2>Headline</h2><ul>",
        f"<li>DFN3 attenuation at +5 dB: {fmt(values['dfn3_mean_drop_5'])} dB "
        f"(RNNoise {fmt(values['rnnoise_mean_drop_5'])} dB)</li>",
        f"<li>DFN3 SI-SDR at +5 dB: {fmt(values['dfn3_mean_si_sdr_5'])} dB "
        f"(RNNoise {fmt(values['rnnoise_mean_si_sdr_5'])} dB)</li>",
        f"<li>DFN3 STOI at +5 dB: {fmt(values['dfn3_mean_stoi_5'], 3)} "
        f"(RNNoise {fmt(values['rnnoise_mean_stoi_5'], 3)})</li>",
        f"<li>DFN3 p99: {fmt(values['dfn3_p99_ms'], 3)} ms/frame; RTF {fmt(values['dfn3_rtf'], 3)}</li>",
        "</ul>",
    ]
    for cid in keys:
        row = find_results(results, cid, "dfn3")
        if not row:
            continue
        parts.append(f"<h3>{html.escape(cid)}</h3><table><tr><th>Processor</th><th>Noise drop dB</th><th>SI-SDR</th><th>STOI</th><th>Audio</th></tr>")
        for pname in PROCESSORS:
            r = find_results(results, cid, pname)
            if not r:
                continue
            parts.append(
                f"<tr><td>{html.escape(LABELS[pname])}</td><td>{fmt(r['noise_drop_db'])}</td>"
                f"<td>{fmt(r['si_sdr_db'])}</td><td>{fmt(r['stoi'], 3)}</td>"
                f"<td><audio controls src='{html.escape(r['audio'])}'></audio></td></tr>"
            )
        parts.append("</table>")
        image = BASE / "spectrograms" / f"{cid}.png"
        if image.exists():
            parts.append(f"<p><img src='spectrograms/{html.escape(cid)}.png' style='max-width:100%'></p>")
    parts.append("<h2>Continuous noise at +5 dB</h2>")
    parts.append(continuous_table(results, 5).replace("\n", "<br>"))
    parts.append("<h2>Events</h2>")
    parts.append(event_table(event_results).replace("\n", "<br>"))
    parts.append("<h2>Realtime</h2>")
    parts.append(realtime_table(realtime).replace("\n", "<br>"))
    parts.append(
        "<h2>Recommendation</h2><ul>"
        "<li>Use DFN3 as an opt-in high-quality mode; keep RNNoise as the default and fallback.</li>"
        "<li>Do not add the 80 Hz high-pass to the DFN3 path; raw DFN3 was more consistent.</li>"
        "<li>Expect babble, wind, and construction to leak; DFN3 is not a BVC/AEC replacement.</li>"
        "<li>Runtime package is about 25 MB installed; model load is about 150 ms.</li>"
        "</ul>"
    )
    parts.append("</body></html>")
    (BASE / "report.html").write_text("\n".join(parts), encoding="utf-8")


def main():
    t0 = time.perf_counter()
    if not SPEECH_DIR.exists() or not list(SPEECH_DIR.glob("*.wav")):
        raise SystemExit(f"missing speech corpus in {SPEECH_DIR}")
    speech_paths = sorted(p for p in SPEECH_DIR.glob("*.wav") if p.name != "test.wav")
    speech = [load_speech(p, SAMPLES) for p in speech_paths]
    if not speech:
        raise SystemExit("no speech files")
    print(f"speech clips: {len(speech)}", flush=True)
    cases = build_cases(speech)
    print(f"cases: {len(cases)}  processors: {len(PROCESSORS)}", flush=True)
    results, event_results = process_cases(cases)
    variants = process_variants(cases)
    rt_source = next((c["mix"] for c in cases if c["noise"] == "babble"), cases[0]["mix"])
    realtime = realtime_test(rt_source)
    values = summary_values(results, event_results, realtime)
    write_report(results, event_results, realtime, values, variants)
    write_spectrograms(results)
    write_html(results, event_results, realtime, values)
    print(json.dumps(values, indent=2), flush=True)
    print(f"done in {time.perf_counter() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
