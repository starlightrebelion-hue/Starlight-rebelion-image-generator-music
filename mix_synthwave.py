"""Mezcla de Ruta Neon por el tunel: con el proyecto abierto en FL, ajusta y guarda."""
import os
import sys
import time
sys.path.insert(0, '.')
import flbridge as fl
c = fl.call

cmds = [("bridge", "setTempo", 100)]
for i in range(4, 8):
    cmds.append(("channels", "showEditor", i, 0))
for i, (name, vol) in enumerate((("Kick", .62), ("Clap", .55), ("Hat", .5), ("Snare", .65), ("Bajo", .78),
                                 ("Arpegio", .5), ("Pad", .78), ("Lead", .7), ("Crash", .4))):
    cmds += [("channels", "setChannelName", i, name), ("channels", "setChannelVolume", i, vol)]
    cmds.append(("mixer", "setTrackName", i + 1, name))
for track, level in ((5, 1.0), (6, .8), (7, 1.0), (8, .8)):
    cmds.append(("mixer", "setTrackVolume", track, level))
for n, name in enumerate(("Intro", "Verso", "Build", "Coro", "Break", "Outro"), 1):
    cmds += [("patterns", "setPatternName", n, name), ("playlist", "setTrackName", n, name)]


def p(track, slot, index, value):
    cmds.append(("plugins", "setParamValue", float(value), index, track, slot))


for track, slot, wet in ((2, 0, .2), (4, 0, .26), (7, 0, .24), (8, 1, .2)):
    p(track, slot, 10, .8)   # dry 100%
    p(track, slot, 12, wet)  # wet
    p(track, slot, 11, .2)   # early reflections
    p(track, slot, 5, .09)   # decay
for track, volume, feedback in ((6, .25, .3), (8, .3, .35)):
    for index, value in ((0, .5), (1, volume), (2, 1.0), (3, feedback), (4, .187), (7, .6)):
        p(track, 0, index, value)
p(1, 0, 0, .75)  # clipper suave en el kick
p(0, 9, 2, .49)  # techo del limitador -0.3 dB

results = fl.batch(cmds)
print("comandos", len(results), "de", len(cmds), "ok", all(r["ok"] for r in results))
if not results[-1]["ok"]:
    print(results[-1]["error"])
    raise SystemExit(1)
print(fl.status())
print([ascii(c("plugins", "getParamValueString", i, 7, 0)) for i in (5, 10, 12)])
f = sys.argv[1]
before = os.path.getmtime(f)
c("transport", "globalTransport", 92, 1)
time.sleep(3)
print("guardado", os.path.getmtime(f) > before, os.path.getsize(f))
