"""Copia de estudio del loop del video: mismas notas y estructura, para igualar el sonido.

Es un punto de partida privado: hay que cambiar las notas antes de publicar nada. FL debe estar cerrado.
"""
import struct
import sys
import tempfile
from pathlib import Path

import build_dune as dune
import build_epico as epico
import build_synthwave as song
import flbridge as fl
import flp_edit as flp

STEP, BAR = song.STEP, flp.BAR
KICK, CLAP, HAT, SNARE, BASS, BASS2, PAD, CHORDS, ARP, MELODY = range(10)
TRACKS = ("Kick", "Clap", "Hat", "Snare", "Bajo", "Bajo 2", "Pad", "Acordes", "Arpegio", "Melodia")
DRUMS, SYNTHS, REVERB, DELAY = epico.DRUMS, epico.SYNTHS, epico.REVERB, epico.DELAY
LOOP_BARS, REPEATS = 8, 2

# Leido del piano roll del video; los acordes y la bateria salen del audio
BASS_ROOTS = (40, 40, 43, 38)                # Mi Mi Sol Re
BASS_STEPS = (1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15)  # deja libre el golpe del bombo
PAD_LINE = ((0, 2, 64), (2, 1, 67), (3, 1, 62))
CHORD_BARS = ((64, 67, 71), (64, 67, 74), (62, 67, 71), (62, 66, 69))
ARP_NOTES = (83, 78, 76, 78, 83, 78, 76, 78, 79, 78, 76, 78, 79, 78, 76, 78)
MELODY_NOTES = ((2, 69), (5, 69), (8, 67), (11, 67), (14, 67), (16, 66), (19, 66), (22, 66),
                (25, 66), (28, 66), (30, 67))

DUNE_PATCHES = {
    BASS: "DUNE 2 Factory/Bass/32 Osc RH.fxp",
    PAD: "DUNE 2 Factory/Pads/Airy Voice Pad RL.fxp",
    ARP: "DUNE 3 Factory/Plucked/Mellow Phased ST.fxp",
    MELODY: "DUNE 3 Factory/Leads/80s Upbeat Lead XS.fxp",
}
SERUM_ROOT = dune.DOCUMENTS / "Xfer/Serum 2 Presets/Presets/Factory"
SERUM_PRESETS = {
    BASS2: "Bass/Retro Analog/BA - Neon Drive.SerumPreset",
    CHORDS: "Synth/SY - Hybrid Synthwave Poly.SerumPreset",
}
SERUM_TEMPLATE = Path(__file__).parent / "presets/serum2_template.fst"
INSTRUMENTS = ((BASS, "Bajo", 5), (BASS2, "Bajo 2", 6), (PAD, "Pad", 7), (CHORDS, "Acordes", 8),
               (ARP, "Arpegio", 9), (MELODY, "Melodia", 10))
ROUTES = {
    1: {DRUMS: 1, SYNTHS: 0}, 2: {DRUMS: 1, REVERB: .2}, 3: {DRUMS: 1}, 4: {DRUMS: 1, REVERB: .25},
    5: {SYNTHS: 1}, 6: {SYNTHS: 1}, 7: {SYNTHS: 1, REVERB: .35}, 8: {SYNTHS: 1, REVERB: .3},
    9: {SYNTHS: 1, REVERB: .3, DELAY: .5}, 10: {SYNTHS: 1, REVERB: .4, DELAY: .4},
    DRUMS: {0: 1}, SYNTHS: {0: 1}, REVERB: {SYNTHS: 1}, DELAY: {REVERB: .3, SYNTHS: 1},
}
EFFECTS = (
    (0, 0, "Fruity Parametric EQ 2/Default.fst"),
    (1, 0, "Fruity Parametric EQ 2/Default.fst"), (1, 1, "Fruity Soft Clipper/Default.fst"),
    (5, 0, "Fruity Parametric EQ 2/Default.fst"), (6, 0, "Fruity Parametric EQ 2/Default.fst"),
    (DRUMS, 0, "Fruity Compressor/External/Light.fst"),
    (REVERB, 0, "LuxeVerb/Hall/Lush Pad Hall.fst"), (REVERB, 1, "Fruity Parametric EQ 2/Default.fst"),
    (DELAY, 0, "Fruity Delay 3/Ping pong.fst"), (DELAY, 1, "Fruity Parametric EQ 2/Default.fst"),
)


def notes_for(channel, items):
    """`items`: [(paso, largo en pasos, tecla, velocidad), ...]."""
    return [(step * STEP, flp.note(step * STEP, channel, length * STEP, key, velocity))
            for step, length, key, velocity in items]


def patterns():
    bass = [(bar * 16 + step, 1, root, 100) for bar, root in enumerate(BASS_ROOTS) for step in BASS_STEPS]
    drums = notes_for(KICK, [(step, 1, 60, 118) for step in (0, 4, 8, 12)])
    drums += notes_for(HAT, [(step, 1, 60, 90) for step in (2, 6, 10, 14)])
    backbeat = notes_for(CLAP, [(step, 1, 60, 100) for step in (4, 12)])
    backbeat += notes_for(SNARE, [(step, 1, 60, 105) for step in (4, 12)])
    arp = [(n * 2 + cycle * 32, 2, key, 90) for cycle in range(2) for n, key in enumerate(ARP_NOTES)]
    chords = [(bar * 16, 16, key, 85) for bar, keys in enumerate(CHORD_BARS) for key in keys]
    return {
        1: drums, 2: backbeat,
        3: notes_for(BASS, bass), 4: notes_for(BASS2, bass),
        5: notes_for(PAD, [(bar * 16, bars * 16, key, 85) for bar, bars, key in PAD_LINE]),
        6: notes_for(CHORDS, chords),
        7: notes_for(ARP, arp),
        8: notes_for(MELODY, [(step, 2, key, 100) for step, key in MELODY_NOTES]),
    }


# patron -> (pista de la playlist, compases del clip)
LAYOUT = {1: (0, 1), 2: (1, 1), 3: (2, 4), 4: (3, 4), 5: (4, 4), 6: (5, 4), 7: (6, 4), 8: (7, 2)}


def serum_preset(folder, name, preset):
    header, events = flp.read(SERUM_TEMPLATE)
    events = [(event, flp.set_serum_preset(value, SERUM_ROOT / preset) if event == flp.PLUGIN_STATE else value)
              for event, value in events]
    path = Path(folder) / f"{name}.fst"
    flp.write(path, header, events)
    return path


def clips():
    return [(start, number, track, bars) for number, (track, bars) in LAYOUT.items()
            for start in range(0, LOOP_BARS * REPEATS, bars)]


def main(base, project, pump=None, pump_track=SYNTHS):
    """`pump`: efecto extra para la pista `pump_track`."""
    if fl.fl_running():
        raise SystemExit("Cierra FL Studio primero.")
    header, events = flp.read(base)
    flp.set_sample(events, KICK, song.FACTORY + "Kicks\\Linn Kick.wav")
    flp.set_sample(events, HAT, song.FACTORY + "Hats\\Linn CH.wav")
    flp.set_sample(events, SNARE, song.FACTORY + "Snares\\Linn Snare.wav")
    with tempfile.TemporaryDirectory() as folder:
        for channel, name, insert in INSTRUMENTS:
            if channel in DUNE_PATCHES:
                preset = dune.patched_preset(folder, name, DUNE_PATCHES[channel])
            else:
                preset = serum_preset(folder, name, SERUM_PRESETS[channel])
            header, index = flp.add_channel(events, header, name, insert, preset=preset)
            if index != channel:
                raise ValueError(f"{name} quedo en el canal {index}")
    flp.set_patterns(events, patterns())
    flp.place(events, clips())
    presets = fl._shared_path("FL Studio").parent / "Data/Patches/Plugin presets/Effects"
    for insert, slot, preset in EFFECTS:
        flp.add_effect(events, insert, slot, flp.effect_block(presets / preset))
    flp.add_effect(events, SYNTHS, 0, epico.sidechain_limiter())
    if pump:
        flp.add_effect(events, pump_track, 1 if pump_track == 5 else 0, pump)
    for insert, levels in ROUTES.items():
        flp.set_routes(events, insert, levels)
    flp.write(project, header, events)
    print(f"{len(patterns())} patrones, {len(clips())} clips: {project}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
