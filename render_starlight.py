"""Arma, mezcla y renderiza Starlight Rebellion. Uso: render_starlight.py base.flp carpeta [1 2 ...]

Abre y cierra FL en cada version: mientras corre no se puede trabajar en FL.
"""
import subprocess
import sys
import time
from pathlib import Path

import build_starlight as song
import flbridge as fl
import mix_starlight as mix

TITLE = "Starlight Rebellion"


def close_fl():
    subprocess.run(["taskkill", "/F", "/IM", "FL64.exe"], capture_output=True)
    while fl.fl_running():
        time.sleep(1)


def open_fl(project):
    subprocess.Popen([str(fl._shared_path("FL Studio")), str(project)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            fl.status()
            time.sleep(5)  # deja terminar de cargar los plugins
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("FL no respondio por el tunel.")


def make(base, folder, number):
    version = song.VERSIONS[number - 1]
    project = folder / f"{TITLE} {number:02d} {version.name}.flp"
    song.main(base, project, version)
    open_fl(project)
    mix.main(project, version)
    close_fl()
    started = time.time()
    wav = fl.render(project, "wav", 900)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "320k",
                    str(wav.with_suffix(".mp3"))], check=True)
    print(f"{project.stem}: render {time.time() - started:.0f} s", flush=True)


def main(base, folder, numbers):
    folder = folder.resolve()
    folder.mkdir(exist_ok=True)
    close_fl()
    for number in numbers:
        make(base, folder, number)


if __name__ == "__main__":
    wanted = [int(n) for n in sys.argv[3:]] or range(1, len(song.VERSIONS) + 1)
    main(Path(sys.argv[1]), Path(sys.argv[2]), wanted)
