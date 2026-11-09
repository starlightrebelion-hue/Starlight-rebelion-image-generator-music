"""Mezcla de Ruta Neon Epica por el tunel: con el proyecto abierto en FL, ajusta y guarda."""
import math
import os
import re
import sys
import time

import build_epico as song
import flbridge as fl

KICK, BASS, PAD = 1, 5, 7
EQ_SLOT = {0: 0, KICK: 0, BASS: 0, song.REVERB: 1, song.DELAY: 1}
LOW_PASS, HIGH_PASS, PEAKING, HIGH_SHELF = 1 / 7, 3 / 7, 6 / 7, 1.0
STEEP = .25  # pendiente "Steep 4"
FADERS = ((1, .62), (2, .55), (3, .6), (4, .65), (5, .78), (6, .5), (7, .78), (8, .7), (9, .4), (10, .5), (11, .6))
MASTER_EQ = ((1, PEAKING, 250, -4), (3, PEAKING, 700, 3), (4, PEAKING, 2000, 3), (6, HIGH_SHELF, 5000, 3))
TRACK_LEVELS = ((5, 1.0), (6, .8), (7, 1.0), (8, .8), (song.DRUMS, .8), (song.SYNTHS, .8),
                (song.REVERB, .8), (song.DELAY, .8))


def eq_freq(hertz):
    return .167 + .333 * math.log10(hertz / 63)


def eq_band(track, band, kind, hertz, gain_db=0.0, order=.5):
    slot = EQ_SLOT[track]
    return [(track, slot, 21 + band, kind), (track, slot, 7 + band, eq_freq(hertz)),
            (track, slot, 28 + band, order), (track, slot, band, .5 + gain_db / 36)]


def find_value(track, slot, index, target):
    """Busca el valor 0-1 cuyo texto en FL muestra `target`; el parametro debe subir con el valor."""
    low, high = 0.0, 1.0
    for _ in range(14):
        middle = (low + high) / 2
        fl.call("plugins", "setParamValue", middle, index, track, slot)
        shown = fl.call("plugins", "getParamValueString", index, track, slot)
        number = float(re.search(r"-?[\d.]+", shown).group())
        low, high = (middle, high) if number < target else (low, middle)
    return (low + high) / 2


def params():
    values = []
    for band in (eq_band(KICK, 0, HIGH_PASS, 40, order=STEEP), eq_band(KICK, 1, PEAKING, 100, 3),
                 eq_band(BASS, 0, HIGH_PASS, 55, order=STEEP), eq_band(BASS, 1, PEAKING, 110, 3),
                 eq_band(BASS, 3, PEAKING, 700, 3),
                 *(eq_band(0, band, kind, hertz, gain) for band, kind, hertz, gain in MASTER_EQ),
                 eq_band(song.REVERB, 0, HIGH_PASS, 300), eq_band(song.REVERB, 6, LOW_PASS, 6000),
                 eq_band(song.DELAY, 0, HIGH_PASS, 300), eq_band(song.DELAY, 6, LOW_PASS, 5000)):
        values += band
    values += [(song.REVERB, 0, 32, 0.0),            # retorno 100% humedo, como en el video
               (song.DELAY, 0, 25, 0.0), (song.DELAY, 0, 4, .186), (song.DELAY, 0, 14, .35),
               (PAD, 1, 2, .35),                     # abre el pad un 30%
               (song.DRUMS, 0, 4, .1),               # release corto en el bus de bateria
               (song.SYNTHS, 0, 8, .2), (song.SYNTHS, 0, 9, .87), (song.SYNTHS, 0, 12, .65),
               (6, 0, 13, 0.0), (PAD, 0, 13, 0.0), (8, 0, 13, 0.0),  # sin el ruido del chorus
               (0, 9, 2, .49)]                       # techo del limitador -0.3 dB
    return values


def main(project, drop=()):
    """`drop`: parametros (pista, slot) que no aplican a esta version."""
    _, names, _ = song.layers()
    cmds = [("bridge", "setTempo", 100)]
    cmds += [("channels", "showEditor", channel, 0) for channel in range(4, 8)]
    for channel, name in enumerate(song.TRACKS):
        cmds += [("channels", "setChannelName", channel, name), ("mixer", "setTrackName", channel + 1, name),
                 ("playlist", "setTrackName", channel + 1, name)]
    cmds += [("mixer", "setTrackName", track, name) for track, name in song.BUSES.items()]
    cmds += [("channels", "setChannelVolume", track - 1, level) for track, level in FADERS]
    cmds += [("mixer", "setTrackVolume", track, level) for track, level in TRACK_LEVELS]
    cmds += [("patterns", "setPatternName", number, name) for number, name in names.items()]
    cmds += [("plugins", "setParamValue", float(value), index, track, slot)
             for track, slot, index, value in params() if (track, slot) not in drop]
    results = fl.batch(cmds)
    print("comandos", len(results), "de", len(cmds), "ok", all(r["ok"] for r in results))
    if not results[-1]["ok"]:
        raise SystemExit(results[-1]["error"])
    # Como en la Valhalla del video: 4 s de decay y 20 ms de pre-delay
    fl.call("plugins", "setParamValue", find_value(song.REVERB, 0, 4, 4.0), 4, song.REVERB, 0)
    fl.call("plugins", "setParamValue", find_value(song.REVERB, 0, 5, 20.0), 5, song.REVERB, 0)
    for track, slot, indexes in ((song.REVERB, 0, (4, 5, 32, 33)), (song.REVERB, 1, (7, 13, 21, 27)),
                                 (song.DELAY, 0, (4, 14, 25)), (song.SYNTHS, 0, (8, 9, 12)),
                                 (KICK, 0, (7, 8, 21, 22)), (PAD, 0, (13,)), (0, 0, (1, 3, 4, 6))):
        if (track, slot) in drop:
            continue
        print(track, slot, [ascii(fl.call("plugins", "getParamValueString", i, track, slot)) for i in indexes])
    print(fl.status())
    before = os.path.getmtime(project)
    fl.call("transport", "globalTransport", 92, 1)
    time.sleep(3)
    print("guardado", os.path.getmtime(project) > before, os.path.getsize(project))


if __name__ == "__main__":
    main(sys.argv[1])
