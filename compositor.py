"""Escribe el tema desde un plan: armonia, melodia, bajo, bateria y arreglo. Solo Python, sin FL."""
import math
import random
import struct
from typing import NamedTuple

import build_copia as copia
import build_starlight as song
import estilo_frequency as style
import flp_edit as flp

KICK, CLAP, HAT, SNARE, BASS, BASS2, PAD, CHORDS, ARP, MELODY = range(10)
CRASH, RISER, IMPACT, AMBIENT = song.CRASH, song.RISER, song.IMPACT, song.AMBIENT
AMBIENT_LEVELS = {"Intro": 96, "Verso": 64, "Coro": 46, "Break": 100, "Outro": 96}
AMBIENT_SWELL = (60, 90)
LOW_BASS, LOW_PAD, HIGH_PAD = 36, 60, 72
LOW_LEAD, HIGH_LEAD = 62, 84
RISER_SECONDS = 7.5
BUILD_SWELL = (52, 104)  # velocidad de pad y arpegio al empezar y terminar el build
PPQ = 96
VIDEO_LINE = [key for _, key in copia.MELODY_NOTES]


class Song(NamedTuple):
    patterns: dict
    names: dict
    clips: list
    bars: int
    notes: list      # (canal, paso absoluto, largo en pasos, tecla, velocidad)
    melody: list     # (paso, largo, tecla) del motivo de 8 compases


def scale_classes(plan):
    tonic = style.TONICS[plan["tonica"]]
    return [(tonic + step) % 12 for step in style.SCALES[plan["escala"]]]


def triad(classes, degree):
    return [classes[(degree + n) % 7] for n in (0, 2, 4)]


def voice(chord, previous):
    """Inversion del acorde dentro del registro del pad, lo mas cerca posible del acorde anterior."""
    keys = [key for key in range(LOW_PAD, HIGH_PAD + 1) if key % 12 in chord]
    options = [sorted(group) for group in _triads(keys, chord)]
    return min(options, key=lambda option: sum(abs(a - b) for a, b in zip(option, previous)))


def _triads(keys, chord):
    by_class = [[key for key in keys if key % 12 == pitch] for pitch in chord]
    return [(a, b, c) for a in by_class[0] for b in by_class[1] for c in by_class[2] if max(a, b, c) - min(a, b, c) < 12]


def bass_key(root):
    return LOW_BASS + (root - LOW_BASS) % 12


class Harmony(NamedTuple):
    root: int
    classes: list
    voicing: list


def progression(degrees, classes, bars, start=(61, 66, 69)):
    chords, previous = [], list(start)
    for bar in range(bars):
        chord = triad(classes, degrees[bar % len(degrees)])
        previous = voice(chord, previous)
        chords.append(Harmony(chord[0], chord, previous))
    return chords


def melody_pool(plan, classes):
    if plan["melodia"] == "pentatonica":
        classes = [classes[degree] for degree in style.PENTATONIC_DEGREES]
    return [key for key in range(LOW_LEAD, HIGH_LEAD + 1) if key % 12 in classes]


def contour(kind, moment):
    """Altura deseada entre -1 y 1 para un momento de la frase entre 0 y 1."""
    if kind == "sube":
        return moment * 2 - 1
    if kind == "baja":
        return 1 - moment * 2
    if kind == "pendulo":
        return math.sin(moment * math.pi * 4)
    if kind == "saltos":
        return 1 if int(moment * 16) % 2 else -.6
    return math.sin(moment * math.pi) * 2 - 1


def nearest(keys, target):
    return min(keys, key=lambda key: abs(key - target))


def moved(keys, target, previous):
    """La nota mas cercana al objetivo que no repita la anterior."""
    return nearest([key for key in keys if key != previous] or keys, target)


def phrase(plan, chords, rng, classes):
    """8 compases A A' B A'': el ritmo se repite y las notas caen en notas del acorde al golpe fuerte."""
    pool = melody_pool(plan, classes)
    cells = style.RHYTHMS[plan["densidad"]]
    motif, answer = rng.choice(cells), rng.choice(cells)
    bars = (motif, answer, motif, answer, rng.choice(cells), answer, motif, ((0, 12),))
    center, width = rng.choice((70, 72, 74)), rng.choice((7, 9, 11))
    items, shape = [], {}
    for bar, cell in enumerate(bars):
        tones = [key for key in range(LOW_LEAD, HIGH_LEAD + 1) if key % 12 in chords[bar].classes]
        for index, (onset, length) in enumerate(cell):
            target = center + width * contour(plan["contorno"], (bar * 16 + onset) / 128)
            previous = items[-1][2] if items else None
            strong = onset % 8 == 0
            gesture = (id(cell), index)
            if strong:
                key = moved(tones, target, previous)
            elif gesture in shape:
                # repite el gesto del motivo: mismo movimiento en grados de la escala
                position = pool.index(nearest(pool, previous)) + shape[gesture]
                key = moved(pool, pool[max(0, min(len(pool) - 1, position))], previous)
            else:
                key = moved(pool, target + rng.choice((-2, 2)), previous)
            if previous is not None and gesture not in shape:
                shape[gesture] = pool.index(nearest(pool, key)) - pool.index(nearest(pool, previous))
            items.append((bar * 16 + onset, length, key))
    tonic = [key for key in range(LOW_LEAD, HIGH_LEAD + 1) if key % 12 == classes[0]]
    start, length, last = items[-1]
    items[-1] = (start, length, nearest(tonic, last))
    return items


def grams(keys, size=6):
    steps = [b - a for a, b in zip(keys, keys[1:])]
    return {tuple(steps[n:n + size]) for n in range(len(steps) - size + 1)}


def original_phrase(plan, chords, rng, classes):
    """Descarta melodias que repitan una linea del video. Suele salir en el primer intento."""
    for _ in range(50):
        items = phrase(plan, chords, rng, classes)
        if not grams([key for _, _, key in items]) & grams(VIDEO_LINE):
            return items
    raise ValueError("No salio una melodia distinta del video.")


def every_bar(bars, steps, key=60, velocity=100):
    return [(bar * 16 + step, 1, key, velocity) for bar in bars for step in steps]


def bass_line(chords, steps, velocity=100, length=1):
    # un paso de 16 en adelante suena una octava arriba
    return [(bar * 16 + step % 16, length, bass_key(chord.root) + 12 * (step // 16), velocity)
            for bar, chord in enumerate(chords) for step in steps]


def held(chords, velocity, first_bar=0):
    return [(bar * 16, 16, key, velocity) for bar, chord in enumerate(chords) if bar >= first_bar for key in chord.voicing]


def stabs(chords, plan, velocity, first_bar=0):
    rhythm = style.CHORD_STYLES[plan["acordes"]]
    return [(bar * 16 + onset, length, key, velocity) for bar, chord in enumerate(chords) if bar >= first_bar
            for onset, length in rhythm for key in chord.voicing]


def arp_line(chords, plan, velocity):
    pattern = style.ARPS[plan["arpegio"]]
    size = 16 // len(pattern)
    items = []
    for bar, chord in enumerate(chords):
        low, middle, high = (key + 12 for key in chord.voicing)
        tones = (low, middle, high, low + 12)
        items += [(bar * 16 + n * size, size, tones[tone], velocity + (10 if n * size % 4 == 0 else 0))
                  for n, tone in enumerate(pattern)]
    return items


def crescendo(items, bars, low, high):
    """La velocidad sube a lo largo de la seccion: en los presets que la usan abre el filtro, como un barrido."""
    total = max(1, bars * 16 - 1)
    return [(step, length, key, round(low + (high - low) * min(step, total) / total)) for step, length, key, _ in items]


def lead_line(melody, velocity, bars, octave_up=False):
    items = []
    for cycle in range(bars // 8):
        for step, length, key in melody:
            items.append((step + cycle * 128, length, key, velocity))
            if octave_up and key + 12 <= 96:
                items.append((step + cycle * 128, length, key + 12, velocity - 30))
    return items


def ambient_line(chords, velocity):
    """Acordes largos una octava arriba del pad: la capa de Pigments."""
    return [(bar * 16, 16, key + 12, velocity) for bar, chord in enumerate(chords) for key in chord.voicing]


def parts(kind, chords, plan, melody, last_chorus):
    """Las partes de la seccion, con la capa de ambiente: presente sin bateria, bajita en los coros."""
    found = _parts(kind, chords, plan, melody, last_chorus)
    if kind == "Build":
        found[AMBIENT] = crescendo(ambient_line(chords, 0), len(chords), *AMBIENT_SWELL)
    else:
        found[AMBIENT] = ambient_line(chords, AMBIENT_LEVELS.get(kind, AMBIENT_LEVELS["Outro"]))
    return found


def _parts(kind, chords, plan, melody, last_chorus):
    bars = range(len(chords))
    half = len(chords) // 2
    bass, drums = style.BASS_STYLES[plan["bajo"]], style.DRUM_STYLES[plan["bateria"]]
    hats = every_bar(bars, drums["hats"], velocity=90) + every_bar(bars, drums["fills"], velocity=45)
    if kind == "Intro":
        return {HAT: every_bar(bars[half:], drums["hats"], velocity=55), PAD: held(chords, 80),
                ARP: arp_line(chords, plan, 74)}
    if kind == "Verso":
        return {KICK: every_bar(bars, drums["kick"], velocity=100), CLAP: every_bar(bars[half:], (4, 12), velocity=85),
                HAT: every_bar(bars, drums["hats"], velocity=80), BASS: bass_line(chords, bass, 70, .75),
                PAD: held(chords, 72), CHORDS: stabs(chords, plan, 62, half), ARP: arp_line(chords, plan, 72)}
    if kind == "Build":
        steps = round(RISER_SECONDS * plan["bpm"] / 15)
        last = len(chords) * 16 - 16
        return {KICK: every_bar(bars, drums["kick"], velocity=112), HAT: hats,
                SNARE: every_bar(bars[:-1], (4, 12), velocity=95) + [(last + n, 1, 60, 55 + n * 4) for n in range(16)],
                BASS: bass_line(chords, bass, 95), BASS2: bass_line(chords, bass, 80),
                PAD: crescendo(held(chords, 80), len(chords), *BUILD_SWELL),
                ARP: crescendo(arp_line(chords, plan, 78), len(chords), *BUILD_SWELL), RISER: [(len(chords) * 16 - steps, steps, 60, 100)]}
    if kind == "Coro":
        return {KICK: every_bar(bars, drums["kick"], velocity=118), CLAP: every_bar(bars, (4, 12)),
                SNARE: every_bar(bars, (4, 12), velocity=105), HAT: hats, BASS: bass_line(chords, bass),
                BASS2: bass_line(chords, bass), PAD: held(chords, 85), CHORDS: stabs(chords, plan, 85),
                ARP: arp_line(chords, plan, 85), MELODY: lead_line(melody, 100, len(chords), last_chorus),
                CRASH: [(0, 16, 60, 100)], IMPACT: [(0, 32, 60, 110)]}
    if kind == "Break":
        return {PAD: held(chords, 80), CHORDS: stabs(chords, plan, 58), ARP: arp_line(chords, plan, 65),
                MELODY: lead_line(melody, 78, len(chords)), CRASH: [(0, 16, 60, 85)]}  # la cola del crash baja al break
    return {PAD: held(chords, 80), ARP: arp_line(chords[:max(1, len(chords) * 3 // 4)], plan, 70)}


def compose(plan, seed):
    """Mismo plan y misma semilla dan el mismo tema."""
    rng = random.Random(seed)
    classes = scale_classes(plan)
    verse = style.VERSES[plan["escala"]][plan["progresion_verso"]]
    chorus = style.CHORUSES[plan["escala"]][plan["progresion_coro"]]
    chorus_bars = progression(chorus, classes, 8)
    melody = original_phrase(plan, chorus_bars, rng, classes)

    sections = style.STRUCTURES[plan["estructura"]]
    last_chorus = max(n for n, (kind, _) in enumerate(sections) if kind == "Coro")
    patterns, names, clips, notes, start, seen = {}, {}, [], [], 0, {}
    for index, (kind, bars) in enumerate(sections):
        seen[kind] = seen.get(kind, 0) + 1
        label = kind if seen[kind] == 1 else f"{kind} {seen[kind]}"
        degrees = chorus if kind in ("Coro", "Break") else verse
        chords = progression(degrees, classes, bars)
        for channel, items in sorted(parts(kind, chords, plan, melody, index == last_chorus).items()):
            number = len(patterns) + 1
            patterns[number] = [(round(step * copia.STEP), flp.note(round(step * copia.STEP), channel,
                                                                   round(length * copia.STEP), key, velocity))
                                for step, length, key, velocity in items]
            names[number] = f"{song.TRACKS[channel]} {label}"
            clips.append((start, number, channel, math.ceil(max(step + length for step, length, _, _ in items) / 16)))
            notes += [(channel, start * 16 + step, length, key, velocity) for step, length, key, velocity in items]
        start += bars
    return Song(patterns, names, clips, start, notes, melody)


def _variable(number):
    data = [number & 127]
    while number := number >> 7:
        data.insert(0, number & 127 | 128)
    return bytes(data)


def _track(events):
    data, now = b"", 0
    for tick, payload in sorted(events, key=lambda event: (event[0], event[1][0] & 0xF0 == 0x90)):
        data += _variable(tick - now) + payload
        now = tick
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def write_midi(path, composed, bpm):
    """MIDI estandar, una pista por instrumento: sirve en cualquier DAW."""
    tempo = b"\xff\x51\x03" + (60_000_000 // bpm).to_bytes(3, "big")
    tracks = [_track([(0, tempo)])]
    for channel, name in enumerate(song.TRACKS):
        label = name.encode()
        events = [(0, b"\xff\x03" + _variable(len(label)) + label)]
        for owner, step, length, key, velocity in composed.notes:
            if owner == channel:
                begin = round(step * PPQ / 4)
                events.append((begin, bytes((0x90, key, velocity))))
                events.append((begin + max(1, round(length * PPQ / 4)), bytes((0x80, key, 0))))
        if len(events) > 1:
            tracks.append(_track(events))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
    with open(path, "wb") as file:
        file.write(header + b"".join(tracks))
