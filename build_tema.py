"""Arma "Primer Tema": escribe el arreglo y los efectos en el .flp. FL debe estar cerrado."""
import shutil
import sys
from pathlib import Path

import flbridge as fl
import flp_edit as flp

INTRO, VERSO, DROP = 1, 2, 3
# (patron, pista de la playlist, compases)
SECTIONS = [(INTRO, 0, 8), (VERSO, 1, 8), (DROP, 2, 16), (VERSO, 1, 8), (DROP, 2, 12), (INTRO, 0, 4)]
# pista del mixer -> efecto en el slot 0 (el master ya trae Fruity Limiter)
EFFECTS = {1: "Fruity Soft Clipper", 2: "Fruity Reeverb 2", 3: "Fruity Delay 2", 4: "Fruity Reeverb 2"}


def find_effect(name):
    data = fl._shared_path("FL Studio").parent / "Data"
    for path in sorted(data.rglob("*.flp")):
        _, events = flp.read(path)
        version = next(value for event, value in events if event == 199)
        if version.startswith((b"20.99", b"21")):
            try:
                return flp.plugin_block(events, name)
            except (ValueError, StopIteration):
                continue
    raise ValueError(f"Ningun proyecto de FL trae {name}")


def main(project):
    project = Path(project)
    base = project.with_suffix(".base.flp")
    if not base.exists():
        shutil.copyfile(project, base)
    if fl.fl_running():
        raise SystemExit("Cierra FL Studio primero.")
    header, events = flp.read(base)
    bars = flp.arrange(events, SECTIONS)
    for insert, name in EFFECTS.items():
        flp.add_effect(events, insert, 0, find_effect(name))
    flp.write(project, header, events)
    print(f"{bars} compases, {len(EFFECTS)} efectos: {project}")


if __name__ == "__main__":
    main(sys.argv[1])
