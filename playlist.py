"""Une temas del agente en un mix largo con una sola imagen, tracklist y capitulos.

    python playlist.py 2038 2039 2040 ... --semilla 11
Cada numero es la semilla de un tema de Agente Frequency. El orden se decide por energia.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import agente_musical as agent
import seo_youtube as seo
import video_espectral as video

TARGET_LUFS = -14.0
CROSSFADE = 4       # segundos entre temas
TAIL = .5           # lo que se deja despues del ultimo sonido
SILENCE_DB = -55


class Track(NamedTuple):
    title: str
    wav: Path
    lufs: float
    bpm: int
    seconds: float


def find_track(seed):
    folders = [path for path in agent.OUTPUT.iterdir() if path.is_dir() and path.name.endswith(f" {seed}")]
    if not folders:
        raise SystemExit(f"No encuentro el tema de la semilla {seed} en {agent.OUTPUT}.")
    folder = folders[0]
    plan = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    wav = folder / f"{folder.name}.wav"
    return Track(plan["titulo"], wav, plan["medidas"]["lufs"], plan["bpm"], sound_length(wav))


def sound_length(wav):
    """Segundos hasta el ultimo sonido: FL deja silencio al final."""
    samples = video.espectro.load(wav)
    block = video.espectro.RATE // 10
    whole = len(samples) // block * block
    level = (samples[:whole].reshape(-1, block) ** 2).mean(axis=1)
    loud = (level > 10 ** (SILENCE_DB / 10)).nonzero()[0]
    return (int(loud[-1]) + 1) / 10 + TAIL if len(loud) else len(samples) / video.espectro.RATE


def ordered(tracks):
    """Tempos cercanos seguidos, subiendo hacia el medio y bajando al final: el mix respira como un viaje."""
    by_tempo = sorted(tracks, key=lambda track: (track.bpm, track.title))
    return by_tempo[::2] + by_tempo[1::2][::-1]


def starts(tracks):
    """Segundo en que entra cada tema dentro del mix."""
    position, result = 0, []
    for track in tracks:
        result.append(round(position))
        position += track.seconds - CROSSFADE
    return result


def join(tracks, target):
    """Cada tema a la misma sonoridad, sin su silencio final y con fundido cruzado."""
    inputs, filters = [], []
    for index, track in enumerate(tracks):
        inputs += ["-i", str(track.wav)]
        filters.append(f"[{index}:a]atrim=0:{track.seconds},asetpts=N/SR/TB,volume={TARGET_LUFS - track.lufs}dB[t{index}]")
    last = "t0"
    for index in range(1, len(tracks)):
        filters.append(f"[{last}][t{index}]acrossfade=d={CROSSFADE}:c1=tri:c2=tri[x{index}]")
        last = f"x{index}"
    filters.append(f"[{last}]alimiter=limit=0.89:attack=5:release=50:level=false[out]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-c:a", "pcm_s24le", "-ar", "44100", str(target)], check=True)
    return target


def main():
    parser = argparse.ArgumentParser(description="Arma un mix largo con temas del agente.")
    parser.add_argument("temas", type=int, nargs="+", help="semillas de los temas")
    parser.add_argument("--semilla", type=int, default=1, help="semilla de la imagen y el titulo")
    parser.add_argument("--paleta", choices=list(video.style.PALETTES))
    parser.add_argument("--idea")
    parser.add_argument("--nombre", default="Starlight Mix")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    tracks = ordered([find_track(seed) for seed in args.temas])
    folder = video.OUTPUT / args.nombre
    folder.mkdir(parents=True, exist_ok=True)
    audio = join(tracks, folder / f"{args.nombre}.wav")
    chapters = list(zip((track.title for track in tracks), starts(tracks)))
    for title, second in chapters:
        print(seo.clock(second), title, flush=True)
    target = folder / f"{args.nombre}.mp4"
    video.make(audio, args.semilla, args.paleta, args.idea, target)
    target.with_suffix(".txt").write_text(seo.sheet(args.semilla, chapters), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
