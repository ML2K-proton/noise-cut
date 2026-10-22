# Noise Suppression Benchmark

- Sample rate: 48000 Hz, duration: 5.0 s
- Speech: synthetic English TTS (Microsoft Zira/David), normalized to the same RMS.
- Noise: synthetic, deterministic; see `synth.py`.
- Metrics: noise attenuation in non-speech frames, SI-SDR, STOI, speech-level change.
- DFN3: `deepfilternet-rs` 0.1.1, `atten_lim=100`, no post-filter.
- Measured algorithmic delay: RNNoise 960 samples (20 ms), DFN3 1440 samples (30 ms).
- DFN3+HP rows use a high-passed clean reference so the filter's own speech coloration is not counted as residual.

## Headline

- DFN3 mean continuous-noise attenuation at +5 dB SNR: **7.43 dB** (RNNoise: 0.56 dB).
- DFN3 mean SI-SDR at +5 dB: **12.41 dB** (RNNoise: 4.10 dB).
- DFN3 mean STOI at +5 dB: **0.861** (RNNoise: 0.842).
- Event peak attenuation (mean): DFN3 **24.54 dB**, RNNoise 19.37 dB.
- DFN3 realtime p99: **3.123 ms/frame**, RTF **0.177**.
- With the app's 40 ms prefill, estimated end-to-end algorithm delay is ~60 ms for RNNoise and ~70 ms for DFN3 (excluding OS/device buffers).

## Continuous noise at +5 dB SNR

| Noise | RN drop | RN SI-SDR | RN STOI | DFN3 drop | DFN3 SI-SDR | DFN3 STOI | DFN3+HP drop | DFN3+HP STOI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fan | 0.86 | 4.57 | 0.78 | 6.51 | 11.38 | 0.78 | 4.25 | 0.97 |
| keyboard | 2.05 | 6.11 | 0.93 | 9.03 | 14.07 | 0.92 | 9.50 | 0.95 |
| traffic | 1.37 | 5.24 | 0.68 | 6.68 | 11.55 | 0.68 | 3.21 | 0.98 |
| rain | 1.56 | 5.49 | 0.97 | 11.76 | 17.13 | 0.97 | 12.49 | 0.97 |
| wind | -0.23 | 3.04 | 0.93 | 4.15 | 8.99 | 0.94 | 5.67 | 0.95 |
| babble | -2.18 | -0.18 | 0.69 | 1.88 | 6.35 | 0.83 | 0.10 | 0.90 |
| dog | 0.93 | 4.67 | 0.79 | 8.53 | 13.55 | 0.79 | 7.70 | 0.97 |
| baby | 0.53 | 4.15 | 0.92 | 6.62 | 11.32 | 0.94 | 6.16 | 0.98 |
| construction | 0.71 | 4.44 | 0.66 | 5.47 | 10.22 | 0.66 | 3.89 | 0.94 |
| notification | 0.99 | 4.76 | 0.98 | 14.17 | 19.56 | 0.99 | 12.07 | 0.99 |
| music | -0.39 | 2.84 | 0.94 | 6.97 | 12.39 | 0.96 | 6.83 | 0.97 |

## Continuous noise at 0 dB SNR

| Noise | RN drop | RN SI-SDR | RN STOI | DFN3 drop | DFN3 SI-SDR | DFN3 STOI | DFN3+HP drop | DFN3+HP STOI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fan | 5.12 | 3.57 | 0.75 | 9.32 | 9.05 | 0.75 | 6.15 | 0.94 |
| keyboard | 6.83 | 5.83 | 0.92 | 12.82 | 12.74 | 0.90 | 12.78 | 0.92 |
| traffic | 5.47 | 4.03 | 0.66 | 9.17 | 8.94 | 0.66 | 4.63 | 0.95 |
| rain | 6.29 | 5.14 | 0.95 | 14.44 | 14.52 | 0.95 | 14.77 | 0.95 |
| wind | 3.64 | 1.21 | 0.88 | 5.96 | 5.58 | 0.90 | 6.31 | 0.91 |
| babble | 0.91 | -3.20 | 0.64 | 3.22 | 0.59 | 0.74 | 2.60 | 0.79 |
| dog | 5.40 | 3.94 | 0.78 | 11.00 | 10.72 | 0.78 | 10.06 | 0.95 |
| baby | 4.05 | 2.02 | 0.89 | 9.02 | 8.45 | 0.93 | 8.37 | 0.96 |
| construction | 4.48 | 2.65 | 0.61 | 7.80 | 7.36 | 0.63 | 5.46 | 0.90 |
| notification | 5.83 | 4.55 | 0.98 | 16.80 | 16.99 | 0.99 | 16.01 | 0.99 |
| music | 3.09 | 0.49 | 0.89 | 8.09 | 8.02 | 0.93 | 8.11 | 0.94 |

## Continuous noise at -5 dB SNR

| Noise | RN drop | RN SI-SDR | RN STOI | DFN3 drop | DFN3 SI-SDR | DFN3 STOI | DFN3+HP drop | DFN3+HP STOI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fan | 8.72 | 1.42 | 0.68 | 11.64 | 5.86 | 0.70 | 7.95 | 0.87 |
| keyboard | 11.60 | 5.54 | 0.90 | 17.08 | 11.95 | 0.88 | 16.74 | 0.90 |
| traffic | 8.92 | 1.72 | 0.61 | 11.23 | 5.41 | 0.62 | 6.13 | 0.88 |
| rain | 10.86 | 4.56 | 0.92 | 17.04 | 11.89 | 0.92 | 17.27 | 0.91 |
| wind | 7.17 | -1.82 | 0.82 | 7.73 | 0.22 | 0.82 | 7.51 | 0.82 |
| babble | 2.55 | -7.89 | 0.57 | 4.09 | -6.01 | 0.61 | 3.58 | 0.60 |
| dog | 9.92 | 3.24 | 0.76 | 13.87 | 8.27 | 0.76 | 12.80 | 0.92 |
| baby | 7.98 | 0.21 | 0.86 | 12.17 | 6.26 | 0.90 | 11.33 | 0.94 |
| construction | 7.56 | -0.91 | 0.53 | 9.63 | 3.42 | 0.58 | 6.92 | 0.82 |
| notification | 10.64 | 4.30 | 0.97 | 19.16 | 14.07 | 0.98 | 19.37 | 0.98 |
| music | 5.61 | -3.93 | 0.85 | 9.11 | 2.01 | 0.89 | 9.10 | 0.90 |

## Largest DFN3 leaks at +5 dB

- **babble**: 1.88 dB attenuation, SI-SDR 6.35 dB, STOI 0.827
- **wind**: 4.15 dB attenuation, SI-SDR 8.99 dB, STOI 0.942
- **construction**: 5.47 dB attenuation, SI-SDR 10.22 dB, STOI 0.657
- **fan**: 6.51 dB attenuation, SI-SDR 11.38 dB, STOI 0.777
- **baby**: 6.62 dB attenuation, SI-SDR 11.32 dB, STOI 0.940
- **traffic**: 6.68 dB attenuation, SI-SDR 11.55 dB, STOI 0.682
- **music**: 6.97 dB attenuation, SI-SDR 12.39 dB, STOI 0.964
- **dog**: 8.53 dB attenuation, SI-SDR 13.55 dB, STOI 0.793

## Transient human events

| Event | Level dB | RN peak drop | DFN3 peak drop | DFN3+HP peak drop | DFN3 RMS drop |
|---|---:|---:|---:|---:|---:|
| cough | 0 | 19.37 | 32.95 | 33.27 | 35.81 |
| cough | 10 | 19.91 | 31.91 | 31.87 | 34.85 |
| cough | 5 | 19.90 | 31.94 | 31.90 | 34.87 |
| sneeze | 0 | 18.98 | 16.74 | 16.29 | 25.59 |
| sneeze | 10 | 19.04 | 16.86 | 16.41 | 25.69 |
| sneeze | 5 | 19.03 | 16.82 | 16.37 | 25.65 |

## Reverb and echo

| Case | RN SI-SDR | RN STOI | DFN3 SI-SDR | DFN3 STOI | DFN3+HP SI-SDR | DFN3+HP STOI |
|---|---:|---:|---:|---:|---:|---:|
| echo_012 | 2.22 | 0.59 | 6.06 | 0.62 | 6.35 | 0.87 |
| reverb_025 | -38.03 | 0.34 | -42.17 | 0.51 | -34.31 | 0.48 |
| reverb_05 | -40.68 | 0.28 | -47.91 | 0.42 | -45.22 | 0.37 |

## DFN3 tuning variants

| Case | DFN3 drop | atten30 drop | postfilter drop | DFN3 SI-SDR | atten30 SI-SDR | postfilter SI-SDR |
|---|---:|---:|---:|---:|---:|---:|
| babble_snr_plus0 | 3.22 | 3.26 | 3.14 | 0.59 | 0.68 | 0.39 |
| babble_snr_plus5 | 1.88 | 1.98 | 1.70 | 6.35 | 6.44 | 6.17 |
| construction_snr_plus0 | 7.80 | 7.89 | 7.64 | 7.36 | 7.43 | 7.23 |
| construction_snr_plus5 | 5.47 | 5.60 | 5.37 | 10.22 | 10.34 | 10.13 |
| fan_snr_plus0 | 9.32 | 9.38 | 9.20 | 9.05 | 9.08 | 8.95 |
| fan_snr_plus5 | 6.51 | 6.63 | 6.43 | 11.38 | 11.50 | 11.32 |
| wind_snr_plus0 | 5.96 | 6.12 | 5.70 | 5.58 | 5.75 | 5.28 |
| wind_snr_plus5 | 4.15 | 4.33 | 4.00 | 8.99 | 9.19 | 8.86 |

## Realtime cost

| Processor | Load ms | p50 ms | p95 ms | p99 ms | Max ms | RTF |
|---|---:|---:|---:|---:|---:|---:|
| RNNoise | 0.1 | 0.971 | 1.708 | 2.081 | 2.943 | 0.103 |
| DFN3 | 144.3 | 1.707 | 2.721 | 3.123 | 3.894 | 0.177 |
| DFN3 + 80 Hz HP | 152.4 | 1.839 | 2.921 | 3.425 | 4.356 | 0.189 |

## Recommendation

- Integrate DFN3 as an **opt-in high-quality mode**; keep RNNoise as the default and fallback.
- Do not add the app's 80 Hz high-pass to the DFN3 path: the raw DFN3 variant was more consistent; the HP variant is retained only as a diagnostic.
- DFN3 is clearly better for stationary noise, keyboard/notification transients, and coughs, but babble, wind, and construction still leak. It is not a BVC/AEC replacement for Krisp.
- Measured CPU cost is acceptable: p99 ~3.1 ms per 10 ms frame and ~70 ms total algorithm delay with the app's 40 ms prefill. The runtime package is ~25 MB installed, and model load is ~150 ms.
- The `deepfilternet-rs` package is still alpha; pin the exact version and keep the RNNoise fallback.

## Interpretation

This is a synthetic benchmark, not a substitute for recordings of the target room, microphone, and Vietnamese speakers. Positive noise attenuation is measured in non-speech frames; negative values mean the processor added more residual than it removed.

Use the audio and spectrogram folders to check artifacts that the numeric metrics miss, especially breath, cough, keyboard transients, babble, and speech endings.

## Files

- `summary.csv`: all numeric rows
- `events.csv`: event-only attenuation rows
- `variants.csv`: DFN3 attenuation/postfilter tuning rows
- `realtime.csv`: realtime timing
- `out/mix/`: input mixtures
- `out/processed/`: processor outputs
- `spectrograms/`: selected comparisons
- `report.html`: listening report
