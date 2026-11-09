"""Convierte un audio en las senales que mueven el video: espectro, graves, golpes, nota y secciones."""
import subprocess
from pathlib import Path
from typing import NamedTuple

import numpy as np

RATE = 44100
WINDOW = 2048
BANDS = 128
LOWEST, HIGHEST = 30.0, 16000.0
WAVE_POINTS = 512
SECTION_GAP = 16.0  # segundos minimos entre cambios de escena
BEAT_GAP = .18


class Analysis(NamedTuple):
    fps: int
    samples: np.ndarray    # mono, para dibujar la onda
    spectrum: np.ndarray   # cuadros x BANDS, 0..1
    bass: np.ndarray       # 0..1 respecto del propio tema
    mid: np.ndarray
    treble: np.ndarray
    energy: np.ndarray     # nivel lento: intro baja, coro alto
    beat: np.ndarray       # impulso que decae despues de cada golpe
    beats: np.ndarray      # cuadros donde hay golpe
    note: np.ndarray       # nota dominante, 0..1
    cuts: tuple            # cuadros donde cambia la seccion

    @property
    def frames(self):
        return len(self.bass)


def load(path, start=0.0, seconds=None):
    """Decodifica con ffmpeg a mono float32."""
    command = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if seconds:
        command += ["-t", str(seconds)]
    command += ["-i", str(Path(path)), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"]
    data = subprocess.run(command, capture_output=True, check=True).stdout
    samples = np.frombuffer(data, dtype=np.float32)
    if not len(samples):
        raise ValueError(f"{path} no tiene audio.")
    return samples


def band_matrix():
    """Bandas logaritmicas: cada fila promedia los bins de FFT de su banda."""
    freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
    edges = np.geomspace(LOWEST, HIGHEST, BANDS + 1)
    matrix = np.zeros((BANDS, len(freqs)), dtype=np.float32)
    for band in range(BANDS):
        low, high = edges[band], edges[band + 1]
        inside = (freqs >= low) & (freqs < high)
        if inside.any():
            matrix[band, inside] = 1 / inside.sum()
        else:  # en graves la banda es mas angosta que un bin
            matrix[band, np.argmin(np.abs(freqs - (low + high) / 2))] = 1
    return matrix, np.sqrt(edges[:-1] * edges[1:])


def magnitudes(samples, fps):
    """Un espectro por cuadro de video, centrado en el instante del cuadro."""
    frames = int(len(samples) / RATE * fps)
    padded = np.pad(samples, WINDOW)
    hann = np.hanning(WINDOW).astype(np.float32)
    starts = (np.arange(frames) * (RATE / fps)).astype(np.int64) + WINDOW // 2
    matrix, _ = band_matrix()
    bands = np.empty((frames, BANDS), dtype=np.float32)
    for first in range(0, frames, 512):
        chunk = starts[first:first + 512, None] + np.arange(WINDOW)
        bands[first:first + 512] = np.abs(np.fft.rfft(padded[chunk] * hann, axis=1)) @ matrix.T
    return bands


def smooth(values, attack, release):
    """Sube rapido y cae lento, como la aguja de un vumetro. Coeficientes por cuadro."""
    out = np.empty_like(values)
    state = np.zeros_like(values[0])
    for index, value in enumerate(values):
        state = state + (value - state) * np.where(value > state, attack, release)
        out[index] = state
    return out


def average(values, seconds, fps):
    size = max(1, int(seconds * fps))
    return np.convolve(np.pad(values, size, mode="edge"), np.ones(size) / size, "same")[size:-size]


def relative(values):
    """Normaliza contra el propio tema: 1 es lo mas fuerte que tiene, salvo picos aislados."""
    top = np.percentile(values, 98)
    return np.clip(values / top, 0, 1) if top > 1e-6 else np.zeros_like(values)


def find_beats(lows, fps):
    """Golpes: subidas de los graves por encima de lo que venia pasando."""
    flux = np.maximum(np.diff(lows, prepend=lows[:1]), 0)
    limit = average(flux, 1.0, fps) * 2.5 + flux.max() * .02
    gap, beats, last = int(BEAT_GAP * fps), [], -10 ** 9
    for frame in np.flatnonzero(flux > limit):
        if frame - last >= gap:
            beats.append(frame)
            last = frame
    return np.array(beats, dtype=np.int64)


def beat_envelope(beats, frames, fps):
    pulses = np.zeros(frames, dtype=np.float32)
    pulses[beats] = 1
    fall = .5 ** (1 / (.09 * fps))  # la mitad cada 90 ms
    state = 0.0
    for frame in range(frames):
        state = max(float(pulses[frame]), state * fall)
        pulses[frame] = state
    return pulses


def find_cuts(energy, fps, limit=8):
    """Los cambios de nivel mas marcados, separados por lo menos SECTION_GAP."""
    gap = int(SECTION_GAP * fps)
    change = np.abs(energy[gap // 4:] - energy[:-gap // 4]) if len(energy) > gap else np.zeros(0)
    cuts = []
    for frame in np.argsort(change)[::-1]:
        if change[frame] < .08 or len(cuts) == limit:
            break
        position = int(frame) + gap // 8
        if position > gap // 2 and all(abs(position - cut) >= gap for cut in cuts):
            cuts.append(position)
    return tuple(sorted(cuts))


def dominant_note(bands, centers):
    """Clase de altura mas fuerte entre 100 y 2000 Hz."""
    useful = (centers > 100) & (centers < 2000)
    classes = (np.round(12 * np.log2(centers[useful] / 440)) % 12).astype(int)
    chroma = np.stack([bands[:, useful][:, classes == note].sum(axis=1) for note in range(12)], axis=1)
    return chroma.argmax(axis=1) / 12


def analyze(samples, fps=60):
    _, centers = band_matrix()
    bands = magnitudes(samples, fps)
    # la mezcla tiene mucho mas grave que agudo: cada banda se mide contra su propio techo
    tops = np.percentile(bands, 99, axis=0)
    flat = np.sqrt(np.clip(bands / np.maximum(tops, 1e-5), 0, 1.2))
    per_frame = 1 / fps
    spectrum = smooth(flat, 1 - .5 ** (per_frame / .012), 1 - .5 ** (per_frame / .12)).astype(np.float32)

    def part(low, high):
        return bands[:, (centers >= low) & (centers < high)].mean(axis=1)

    lows = part(30, 150)
    bass = relative(smooth(lows, .6, .12))
    mid = relative(smooth(part(150, 2000), .4, .08))
    treble = relative(smooth(part(2000, 16000), .5, .12))
    level = np.sqrt(np.convolve(samples ** 2, np.ones(RATE // 10) / (RATE // 10), "same"))
    level = level[(np.arange(len(bass)) * (RATE / fps)).astype(np.int64).clip(0, len(level) - 1)]
    energy = relative(average(level, 3.0, fps))
    beats = find_beats(lows, fps)
    return Analysis(fps, samples, spectrum, bass, mid, treble, energy, beat_envelope(beats, len(bass), fps),
                    beats, dominant_note(bands, centers), find_cuts(energy, fps))


def wave_at(analysis, frame):
    """Los ultimos WAVE_POINTS puntos de la onda alrededor del cuadro, normalizados a -1..1."""
    size = WINDOW
    center = int(frame * RATE / analysis.fps)
    chunk = analysis.samples[max(0, center - size // 2):center + size // 2]
    if len(chunk) < size:
        chunk = np.pad(chunk, (0, size - len(chunk)))
    points = chunk[::size // WAVE_POINTS]
    return (points * np.hanning(WAVE_POINTS)).astype(np.float32)
