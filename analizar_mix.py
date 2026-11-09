"""Mide un mix largo y deja estadisticas de estilo: tempos, tonalidades, progresiones y ritmo.

Guarda solo distribuciones, nunca audio ni lineas melodicas: sirve de universo para componer notas propias.
    python analizar_mix.py mix.m4a universo_frequency.json
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

RATE = 22050
FFT = 8192
HOP = 1024
WINDOW = 30.0       # segundos por muestra
FRAME = HOP / RATE
NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR = np.array((6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88))
MINOR = np.array((6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17))
TEMPO_RANGE = (70, 150)
TEMPO_CENTER = 105  # desempata octavas: el genero vive cerca de aca


def load(path):
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                          capture_output=True, check=True).stdout
    return np.frombuffer(data, dtype=np.float32)


def spectrogram(samples):
    frames = (len(samples) - FFT) // HOP
    out = np.empty((frames, FFT // 2 + 1), dtype=np.float32)
    hann = np.hanning(FFT).astype(np.float32)
    starts = np.arange(frames) * HOP
    for first in range(0, frames, 256):
        chunk = starts[first:first + 256, None] + np.arange(FFT)
        out[first:first + 256] = np.abs(np.fft.rfft(samples[chunk] * hann, axis=1))
    return out


def chroma_matrix(low=65.0, high=1800.0):
    freqs = np.fft.rfftfreq(FFT, 1 / RATE)
    matrix = np.zeros((len(freqs), 12), dtype=np.float32)
    useful = (freqs >= low) & (freqs <= high)
    classes = np.round(12 * np.log2(freqs[useful] / 440) + 9).astype(int) % 12
    matrix[np.flatnonzero(useful), classes] = 1
    return matrix


def tempo_of(flux):
    """Autocorrelacion del ataque, con preferencia suave por el centro del genero."""
    flux = flux - flux.mean()
    spectrum = np.fft.rfft(flux, 2 * len(flux))
    correlation = np.fft.irfft(np.abs(spectrum) ** 2)[:len(flux)]
    lags = np.arange(int(60 / TEMPO_RANGE[1] / FRAME), int(60 / TEMPO_RANGE[0] / FRAME) + 1)
    bpm = 60 / (lags * FRAME)
    weight = np.exp(-.5 * (np.log2(bpm / TEMPO_CENTER) / .5) ** 2)
    best = int(np.argmax(correlation[lags] * weight))
    lag = lags[best]
    if 0 < best < len(lags) - 1:  # interpola entre lags para no quedar en pasos de 2 BPM
        a, b, c = correlation[lag - 1:lag + 2]
        lag = lag + .5 * (a - c) / (a - 2 * b + c)
    return 60 / (lag * FRAME)


def key_of(chroma):
    profile = chroma.mean(axis=0)
    scores = [(float(np.corrcoef(profile, np.roll(table, tonic))[0, 1]), tonic, mode)
              for tonic in range(12) for mode, table in (("mayor", MAJOR), ("menor", MINOR))]
    score, tonic, mode = max(scores)
    return tonic, mode, score


def beat_grid(flux, bpm):
    """Grilla de negras en la fase donde caen mas ataques."""
    period = 60 / bpm / FRAME
    phases = np.arange(0, period, 1)
    strength = [flux[np.round(np.arange(phase, len(flux) - 1, period)).astype(int)].sum() for phase in phases]
    return np.arange(phases[int(np.argmax(strength))], len(flux) - 1, period)


TRIADS = {(root, quality): np.roll(np.array(shape, dtype=np.float32), root)
          for root in range(12)
          for quality, shape in (("", (1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0)), ("m", (1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0)))}


def chords_per_beat(chroma, beats):
    names, table = list(TRIADS), np.stack(list(TRIADS.values()))
    table = table / np.linalg.norm(table, axis=1, keepdims=True)
    result = []
    for start, end in zip(beats[:-1].astype(int), beats[1:].astype(int)):
        vector = chroma[start:max(end, start + 1)].mean(axis=0)
        vector = vector / (np.linalg.norm(vector) + 1e-9)
        result.append(names[int(np.argmax(table @ vector))])
    return result


def bars_of(chords):
    """Agrupa de a 4 negras en la fase donde mas cambian los acordes, y toma el mas votado por compas."""
    changes = [0] * 4
    for index, (a, b) in enumerate(zip(chords, chords[1:])):
        changes[(index + 1) % 4] += a != b
    phase = int(np.argmax(changes))
    return [Counter(chords[start:start + 4]).most_common(1)[0][0] for start in range(phase, len(chords) - 3, 4)], phase


def roman(chord, tonic):
    root, quality = chord
    return f"{(root - tonic) % 12}{quality}"


def rhythm(flux_low, flux_high, beats):
    """Perfil de ataques en semicorcheas dentro del compas, para bombo y para agudos."""
    steps = np.interp(np.arange(0, len(beats) - 1, .25), np.arange(len(beats)), beats).astype(int)
    grid = {name: [] for name in ("graves", "agudos")}
    for name, flux in (("graves", flux_low), ("agudos", flux_high)):
        limit = np.percentile(flux, 85)
        hits = flux[steps] > limit
        whole = len(hits) // 16 * 16
        grid[name] = hits[:whole].reshape(-1, 16).mean(axis=0) if whole else np.zeros(16)
    return grid


def sample_at(spec, start, freqs, chroma_map):
    size = int(WINDOW / FRAME)
    part = spec[start:start + size]
    bass = part[:, (freqs >= 40) & (freqs < 160)].sum(axis=1)
    high = part[:, (freqs >= 2000) & (freqs < 9000)].sum(axis=1)
    whole = np.log1p(part[:, ::4]).astype(np.float32)
    flux = np.maximum(np.diff(whole, axis=0), 0).sum(axis=1)
    bass_flux = np.maximum(np.diff(np.log1p(bass)), 0)
    high_flux = np.maximum(np.diff(np.log1p(high)), 0)
    bpm = tempo_of(flux)
    chroma = part[:-1] ** .5 @ chroma_map
    tonic, mode, confidence = key_of(chroma)
    beats = beat_grid(flux, bpm)
    chords, _ = bars_of(chords_per_beat(chroma, beats))
    grid = rhythm(bass_flux, high_flux, beats)
    centroid = float((part.mean(axis=0) * freqs).sum() / part.mean(axis=0).sum())
    return {"segundo": round(start * FRAME), "bpm": round(float(bpm), 1), "tonica": NOTES[tonic], "modo": mode,
            "confianza": round(confidence, 2), "compases": [roman(chord, tonic) for chord in chords],
            "bombo": np.round(grid["graves"], 2).tolist(), "agudos": np.round(grid["agudos"], 2).tolist(),
            "brillo_hz": round(centroid), "nivel": round(float(np.log1p(part.mean())), 3)}


def split_tracks(samples):
    """Temas: tramos seguidos con el mismo tempo. Evita que un tema largo pese mas que uno corto."""
    tracks, current = [], [samples[0]]
    for sample in samples[1:]:
        same = abs(sample["bpm"] - np.median([item["bpm"] for item in current])) < 2
        if same:
            current.append(sample)
        else:
            tracks.append(current)
            current = [sample]
    tracks.append(current)
    return [track for track in tracks if len(track) >= 2]


def in_minor(sample):
    """Compases en grados de la menor relativa: una misma armonia no cuenta distinto segun el modo detectado."""
    shift = 3 if sample["modo"] == "mayor" else 0
    return [f"{(int(bar.rstrip('m')) + shift) % 12}{'m' if bar.endswith('m') else ''}" for bar in sample["compases"]]


def cycles(samples, length=4):
    """Ciclos de compases mas repetidos en distintas muestras, sin contar los compases sin movimiento."""
    found = Counter()
    for sample in samples:
        bars = in_minor(sample)
        found.update({tuple(bars[start:start + length]) for start in range(0, len(bars) - length + 1, 2)
                      if len(set(bars[start:start + length])) > 1})
    return found


def summary(samples):
    tracks = split_tracks(samples)
    keys = Counter()
    for track in tracks:
        votes = Counter((item["tonica"], item["modo"]) for item in track)
        keys[votes.most_common(1)[0][0]] += 1
    bpms = [float(np.median([item["bpm"] for item in track])) for track in tracks]
    return {
        "muestras": len(samples), "temas_estimados": len(tracks),
        "bpm": {"p10": round(float(np.percentile(bpms, 10)), 1), "mediana": round(float(np.median(bpms)), 1),
                "p90": round(float(np.percentile(bpms, 90)), 1), "por_tema": [round(value, 1) for value in bpms]},
        "tonalidades": {f"{tonic} {mode}": count for (tonic, mode), count in keys.most_common()},
        "modo_menor": round(sum(count for (_, mode), count in keys.items() if mode == "menor") / max(1, len(tracks)), 2),
        "ciclos_4": {" ".join(cycle): count for cycle, count in cycles(samples).most_common(25)},
        "acordes": dict(Counter(bar for sample in samples for bar in in_minor(sample)).most_common(14)),
        "bombo_16": np.round(np.mean([sample["bombo"] for sample in samples], axis=0), 2).tolist(),
        "agudos_16": np.round(np.mean([sample["agudos"] for sample in samples], axis=0), 2).tolist(),
        "brillo_hz": int(np.median([sample["brillo_hz"] for sample in samples])),
    }


def analyze(path, every=45.0):
    samples = load(path)
    print(f"{len(samples) / RATE / 60:.1f} minutos", flush=True)
    freqs = np.fft.rfftfreq(FFT, 1 / RATE)
    chroma_map = chroma_matrix()
    results = []
    block = 600  # de a 10 minutos para no ocupar 30 GB con el espectrograma entero
    for first in range(0, int(len(samples) / RATE), block):
        spec = spectrogram(samples[first * RATE:(first + block + int(WINDOW) + 1) * RATE])
        for offset in np.arange(0, block, every):
            start = int(offset / FRAME)
            if start + int(WINDOW / FRAME) < len(spec):
                item = sample_at(spec, start, freqs, chroma_map)
                item["segundo"] += first
                results.append(item)
        print(f"  minuto {first // 60 + 10}", flush=True)
    return results


def main(source, target):
    samples = analyze(source)
    Path(target).write_text(json.dumps(summary(samples), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary(samples), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:3])
