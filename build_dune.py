"""Ruta Neon Dune: Ruta Neon Epica con los patches de Dune 3 del video. FL debe estar cerrado.

`presets/dune3_template.fst` es un Dune 3 guardado por FL: de ahi sale el estado donde va cada patch.
"""
import sys
import tempfile
from pathlib import Path

import build_epico as epico
import flp_edit as flp

DOCUMENTS = Path.home() / "OneDrive/Documentos"
BANKS = DOCUMENTS / "Synapse Audio/DUNE 3/Soundbanks"
TEMPLATE = Path(__file__).parent / "presets/dune3_template.fst"
PATCHES = {
    "bass": "DUNE 2 Factory/Bass/European KS.fxp",
    "arp": "DUNE 3 Factory/Plucked/Mellow Phased ST.fxp",
    "pad": "DUNE 2 Factory/Pads/Classic Synth Pad RH.fxp",
    "lead": "DUNE 3 Factory/Leads/80s Upbeat Lead XS.fxp",
}
# Los patches de Dune ya traen su chorus: los Vintage Chorus sobran
EFFECTS = tuple(effect for effect in epico.EFFECTS if "Vintage Chorus" not in effect[2])
BASS_SHIFT = -12  # European KS suena una octava mas agudo que el bajo de Harmless
VERSE_BASS_TICKS = 18  # notas cortas: el bajo del Verso deja aire y el Coro crece
NOT_USED = ((6, 0), (7, 0), (8, 0))  # slots sin los parametros de mix_epico


def patched_preset(folder, key, patch):
    header, events = flp.read(TEMPLATE)
    chunk = flp.fxp_chunk(BANKS / patch)
    events = [(event, flp.set_vst3_chunk(value, chunk) if event == flp.PLUGIN_STATE else value)
              for event, value in events]
    path = Path(folder) / f"{key}.fst"
    flp.write(path, header, events)
    return path


def main(base, project):
    with tempfile.TemporaryDirectory() as folder:
        sounds = {key: patched_preset(folder, key, patch) for key, patch in PATCHES.items()}
        epico.main(base, project, sounds, EFFECTS, bass_shift=BASS_SHIFT, verse_bass_ticks=VERSE_BASS_TICKS)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
