"""Mezcla de la copia de estudio por el tunel: con el proyecto abierto en FL, ajusta y guarda."""
import os
import sys
import time

import build_copia as song
import flbridge as fl
import mix_epico as mix

FADERS = (.62, .6, .78, .68, .92, .6, .48, .48, .56, .64)
NAMES = {1: "Bateria", 2: "Clap Snare", 3: "Bajo", 4: "Bajo 2", 5: "Pad", 6: "Acordes", 7: "Arpegio", 8: "Melodia"}
PLAYLIST = ("Bateria", "Clap Snare", "Bajo", "Bajo 2", "Pad", "Acordes", "Arpegio", "Melodia")
NOT_USED = ((6, 0), (7, 0), (7, 1), (8, 0))
mix.MASTER_EQ = ((1, mix.PEAKING, 250, -3), (4, mix.PEAKING, 1800, 3),
                 (6, mix.HIGH_SHELF, 4000, 5))
mix.EQ_SLOT[6] = 0
BASS_CUTS = mix.eq_band(5, 0, mix.HIGH_PASS, 60, order=mix.STEEP) + mix.eq_band(6, 0, mix.HIGH_PASS, 60, order=mix.STEEP)


def main(project):
    cmds = [("bridge", "setTempo", 100)]
    cmds += [("channels", "showEditor", channel, 0) for channel in range(4, 10)]
    for channel, (name, level) in enumerate(zip(song.TRACKS, FADERS)):
        cmds += [("channels", "setChannelName", channel, name), ("mixer", "setTrackName", channel + 1, name),
                 ("channels", "setChannelVolume", channel, level)]
    cmds += [("mixer", "setTrackName", track, name) for track, name in
             ((song.DRUMS, "Bus Bateria"), (song.SYNTHS, "Bus Sintes"), (song.REVERB, "Reverb"), (song.DELAY, "Delay"))]
    cmds += [("mixer", "setTrackVolume", track, .8) for track in (song.DRUMS, song.SYNTHS, song.REVERB, song.DELAY)]
    cmds += [("patterns", "setPatternName", number, name) for number, name in NAMES.items()]
    cmds += [("playlist", "setTrackName", track, name) for track, name in enumerate(PLAYLIST, 1)]
    cmds += [("plugins", "setParamValue", float(value), index, track, slot)
             for track, slot, index, value in mix.params() + BASS_CUTS if (track, slot) not in NOT_USED]
    results = fl.batch(cmds)
    print("comandos", len(results), "de", len(cmds), "ok", all(r["ok"] for r in results))
    if not results[-1]["ok"]:
        raise SystemExit(results[-1]["error"])
    fl.call("plugins", "setParamValue", mix.find_value(song.REVERB, 0, 4, 4.0), 4, song.REVERB, 0)
    fl.call("plugins", "setParamValue", mix.find_value(song.REVERB, 0, 5, 20.0), 5, song.REVERB, 0)
    before = os.path.getmtime(project)
    fl.call("transport", "globalTransport", 92, 1)
    time.sleep(3)
    print(fl.status(), "guardado", os.path.getmtime(project) > before)


if __name__ == "__main__":
    main(sys.argv[1])
