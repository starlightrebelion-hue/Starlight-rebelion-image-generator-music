"""Mezcla de una version de Starlight Rebellion por el tunel: con el proyecto abierto, ajusta y guarda."""
import math
import os
import sys
import time

import build_starlight as song
import flbridge as fl
import mix_copia as base
import mix_epico as mix

FADERS = (.62, .6, .78, .68, .92, .72, .48, .48, .56)  # Kick a Arpegio; la melodia va por version
FX_FADERS = (.6, .5, .6)                              # Crash, Riser, Impacto
CEILING_DB = -2.0  # margen para que el MP3 y la recompresion de YouTube no saturen
mix.MASTER_EQ = ((1, mix.PEAKING, 250, -3), (3, mix.PEAKING, 700, -3), (4, mix.PEAKING, 1800, 2),
                 (6, mix.HIGH_SHELF, 4000, 6))
mix.EQ_SLOT.update({6: 0, 7: 0, 8: 0})
CUTS = (mix.eq_band(5, 0, mix.HIGH_PASS, 60, order=mix.STEEP) + mix.eq_band(6, 0, mix.HIGH_PASS, 60, order=mix.STEEP)
        + mix.eq_band(7, 0, mix.HIGH_PASS, 220) + mix.eq_band(8, 0, mix.HIGH_PASS, 220))
CHORUS_NOISE = 13  # parametro de ruido del Vintage Chorus
# sidechain: el Limiter del Bus Sintes comprime con el kick. Venia en -22 dB y bajaba unos 3 dB:
# el synthwave bombea mas.
PUMP_THRESHOLD, PUMP_THRESHOLD_DB = 8, -30.0
LEAD_FADER, TRACK_UNITY = .64, .8


def lead_levels(gain_db):
    """Reparte la ganancia: primero el fader del canal, lo que falte en la pista del mixer."""
    fader = min(1.0, LEAD_FADER * 10 ** (gain_db / 40))
    rest = gain_db - 40 * math.log10(fader / LEAD_FADER)
    return fader, min(1.0, TRACK_UNITY * 10 ** (rest / 58))


def apply(project, names, lead_fx, gain, decay, tempo=100, faders=FADERS):
    """Ajusta la mezcla del proyecto abierto en FL y lo guarda."""
    fader, track = lead_levels(gain)
    levels = faders + (fader,) + FX_FADERS
    cmds = [("transport", "stop"), ("bridge", "setTempo", tempo)]
    cmds += [("channels", "showEditor", channel, 0) for channel in range(4, 10)]
    for channel, (name, level) in enumerate(zip(song.TRACKS, levels)):
        cmds += [("channels", "setChannelName", channel, name), ("channels", "setChannelVolume", channel, level),
                 ("playlist", "setTrackName", channel + 1, name)]
    cmds += [("mixer", "setTrackName", channel + 1, name) for channel, name in enumerate(song.TRACKS[:10])]
    cmds += [("mixer", "setTrackName", track, name) for track, name in
             ((song.FX_INSERT, "FX"), (song.AMBIENT_INSERT, "Ambiente"), (song.DRUMS, "Bus Bateria"), (song.SYNTHS, "Bus Sintes"),
              (song.REVERB, "Reverb"), (song.DELAY, "Delay"))]
    cmds += [("mixer", "setTrackVolume", bus, .8) for bus in (song.DRUMS, song.SYNTHS, song.REVERB, song.DELAY)]
    cmds.append(("mixer", "setTrackVolume", song.LEAD_INSERT, track))
    cmds += [("patterns", "setPatternName", number, name) for number, name in names.items()]
    values = [value for value in mix.params() if value[:2] not in base.NOT_USED] + CUTS
    if "Vintage Chorus" in lead_fx:
        values.append((song.LEAD_INSERT, 0, CHORUS_NOISE, 0.0))
    cmds += [("plugins", "setParamValue", float(value), index, track, slot) for track, slot, index, value in values]
    results = fl.batch(cmds)
    failed = [result for result in results if not result["ok"]]
    print("comandos", len(results), "de", len(cmds), "fallidos", len(failed), failed[:2], flush=True)
    if failed or len(results) != len(cmds):
        raise SystemExit("La mezcla no se aplico completa.")
    fl.call("plugins", "setParamValue", mix.find_value(song.REVERB, 0, 4, decay), 4, song.REVERB, 0)
    fl.call("plugins", "setParamValue", mix.find_value(song.REVERB, 0, 5, 20.0), 5, song.REVERB, 0)
    fl.call("plugins", "setParamValue", mix.find_value(0, 9, 2, CEILING_DB), 2, 0, 9)
    if fl.call("plugins", "getParamName", PUMP_THRESHOLD, song.SYNTHS, 0) != "Comp threshold":
        raise SystemExit("El Limiter del sidechain no esta donde se esperaba.")
    fl.call("plugins", "setParamValue", mix.find_value(song.SYNTHS, 0, PUMP_THRESHOLD, PUMP_THRESHOLD_DB),
            PUMP_THRESHOLD, song.SYNTHS, 0)
    before = os.path.getmtime(project)
    fl.call("transport", "globalTransport", 92, 1)
    time.sleep(3)
    if os.path.getmtime(project) <= before:
        raise SystemExit("FL no guardo el proyecto.")


def main(project, version):
    apply(project, song.layers(version)[1], version.lead_fx, version.gain, version.decay)


if __name__ == "__main__":
    main(sys.argv[1], song.VERSIONS[int(sys.argv[2]) - 1])
