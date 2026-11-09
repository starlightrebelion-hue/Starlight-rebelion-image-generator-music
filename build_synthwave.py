"""Compone "Ruta Neon": synthwave original, 100 BPM, Re menor. FL debe estar cerrado.

Sale del proyecto base con limitador; despues hay que ajustar la mezcla por el tunel.
"""
import sys
from pathlib import Path

import flbridge as fl
import flp_edit as flp
from build_tema import find_effect

STEP = 24  # semicorchea a 96 PPQ
BAR = flp.BAR
PATTERN_BARS = 8
KICK, CLAP, HAT, SNARE = 0, 1, 2, 3
FACTORY = "%FLStudioFactoryData%\\Data\\Patches\\Packs\\Drums\\"

ROOTS = {"Dm": 38, "Bb": 34, "F": 41, "C": 36}
TRIADS = {"Dm": (0, 3, 7), "Bb": (0, 4, 7), "F": (0, 4, 7), "C": (0, 4, 7)}
VERSE = ["Dm", "Bb", "F", "C"] * 2
CHORUS = ["Bb", "F", "C", "Dm"] * 2

# (compas, paso, largo en pasos, nota): melodia original del coro
MELODY = [
    (0, 0, 6, 74), (0, 6, 2, 77), (0, 8, 4, 74), (0, 12, 4, 72),
    (1, 0, 8, 69), (1, 8, 4, 72), (1, 12, 4, 74),
    (2, 0, 6, 76), (2, 6, 2, 74), (2, 8, 8, 72),
    (3, 0, 12, 74), (3, 12, 4, 69),
    (4, 0, 6, 74), (4, 6, 2, 77), (4, 8, 4, 81), (4, 12, 4, 79),
    (5, 0, 8, 77), (5, 8, 4, 76), (5, 12, 4, 77),
    (6, 0, 6, 79), (6, 6, 2, 77), (6, 8, 8, 76),
    (7, 0, 16, 74),
]


def hit(notes, channel, bar, step, velocity=100, key=60, length=STEP):
    position = bar * BAR + step * STEP
    notes.append((position, flp.note(position, channel, length, key, velocity)))


def pad(notes, channel, chords, velocity=85):
    for bar, chord in enumerate(chords):
        for interval in TRIADS[chord] + (12,):
            hit(notes, channel, bar, 0, velocity, ROOTS[chord] + 24 + interval, BAR)


def bass(notes, channel, chords, gallop=False, velocity=105):
    steps = (0, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15) if gallop else range(0, 16, 2)
    for bar, chord in enumerate(chords):
        for step in steps:
            key = ROOTS[chord] + (24 if step == 14 else 12)
            hit(notes, channel, bar, step, velocity if step % 4 == 0 else velocity - 15, key, STEP + 12)


def arp(notes, channel, chords, velocity=80):
    for bar, chord in enumerate(chords):
        a, b, c = TRIADS[chord]
        shape = (a, b, c, 12, c, b, a, b, c, 12, 12 + b, 12, c, b, c, 12)
        for step, interval in enumerate(shape):
            accent = 12 if step % 4 == 0 else 0
            hit(notes, channel, bar, step, velocity - 12 + accent, ROOTS[chord] + 36 + interval, STEP)


def lead(notes, channel, velocity=105):
    for bar, step, length, key in MELODY:
        hit(notes, channel, bar, step, velocity, key, length * STEP)


def drums(notes, bars=8, four=False, sixteenths=False, clap=False):
    for bar in range(bars):
        for step in ((0, 4, 8, 12) if four else (0, 8, 10)):
            hit(notes, KICK, bar, step, 118)
        for step in (4, 12):
            hit(notes, SNARE, bar, step, 112)
            if clap:
                hit(notes, CLAP, bar, step, 95)
        for step in range(0, 16, 1 if sixteenths else 2):
            hit(notes, HAT, bar, step, 88 if step % 4 == 0 else 62 if step % 2 == 0 else 44)


def patterns(ch):
    intro, verse, build, chorus, breakdown, outro = ([] for _ in range(6))
    pad(intro, ch["pad"], VERSE)
    arp(intro, ch["arp"], VERSE, 70)
    for bar in range(4, 8):
        for step in range(0, 16, 2):
            hit(intro, HAT, bar, step, 55)

    drums(verse)
    bass(verse, ch["bass"], VERSE)
    pad(verse, ch["pad"], VERSE, 72)
    arp(verse, ch["arp"], VERSE, 66)

    drums(build, bars=7, sixteenths=True)
    bass(build, ch["bass"], VERSE)
    pad(build, ch["pad"], VERSE, 82)
    arp(build, ch["arp"], VERSE, 78)
    for step in range(16):
        hit(build, SNARE, 7, step, 55 + step * 4)

    drums(chorus, four=True, sixteenths=True, clap=True)
    bass(chorus, ch["bass"], CHORUS, gallop=True)
    pad(chorus, ch["pad"], CHORUS, 90)
    arp(chorus, ch["arp"], CHORUS, 84)
    lead(chorus, ch["lead"])
    hit(chorus, ch["crash"], 0, 0, 100, length=BAR)

    pad(breakdown, ch["pad"], CHORUS, 80)
    arp(breakdown, ch["arp"], CHORUS, 62)
    lead(breakdown, ch["lead"], 78)

    pad(outro, ch["pad"], VERSE, 70)
    arp(outro, ch["arp"], VERSE[:4], 58)
    return {1: intro, 2: verse, 3: build, 4: chorus, 5: breakdown, 6: outro}


INTRO, VERSO, BUILD, CORO, BREAK, OUTRO = range(1, 7)
SECTIONS = [(INTRO, 0, 8), (VERSO, 1, 16), (BUILD, 2, 8), (CORO, 3, 16), (BREAK, 4, 8),
            (VERSO, 1, 8), (BUILD, 2, 8), (CORO, 3, 16), (OUTRO, 5, 8)]


def instruments(base, sounds=None):
    """Abre la base y crea los canales. Devuelve (cabecera, eventos, canales)."""
    presets = fl._shared_path("FL Studio").parent / "Data/Patches/Plugin presets/Generators/Harmless/X Olbaid"
    header, events = flp.read(base)
    flp.set_sample(events, KICK, FACTORY + "Kicks\\Linn Kick.wav")
    flp.set_sample(events, HAT, FACTORY + "Hats\\Linn CH.wav")
    flp.set_sample(events, SNARE, FACTORY + "Snares\\Linn Snare.wav")
    ch = {}
    for key, name, insert, preset in (("bass", "Bajo", 5, "Bass/Bass Synthwave.fst"),
                                      ("arp", "Arpegio", 6, "Pluck/Pluck Arp.fst"),
                                      ("pad", "Pad", 7, "Pad/Pad Retro.fst"),
                                      ("lead", "Lead", 8, "Lead/Lead Retro.fst")):
        header, ch[key] = flp.add_channel(events, header, name, insert,
                                          preset=(sounds or {}).get(key, presets / preset))
    header, ch["crash"] = flp.add_channel(events, header, "Crash", 9, sample=FACTORY + "Cymbals\\909 Crash.wav")
    return header, events, ch


def main(base, project):
    if fl.fl_running():
        raise SystemExit("Cierra FL Studio primero.")
    header, events, ch = instruments(base)
    flp.set_patterns(events, patterns(ch))
    bars = flp.arrange(events, SECTIONS, PATTERN_BARS)
    for insert, slot, name in ((1, 0, "Fruity Soft Clipper"), (2, 0, "Fruity Reeverb 2"),
                               (4, 0, "Fruity Reeverb 2"), (6, 0, "Fruity Delay 2"),
                               (7, 0, "Fruity Reeverb 2"), (8, 0, "Fruity Delay 2"),
                               (8, 1, "Fruity Reeverb 2")):
        flp.add_effect(events, insert, slot, find_effect(name))
    flp.write(project, header, events)
    print(f"{bars} compases, {len(ch) + 4} canales: {project}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
