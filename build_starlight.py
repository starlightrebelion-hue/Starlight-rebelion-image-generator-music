"""Starlight Rebellion: tema original con el sonido de la copia de estudio, en 10 versiones.

Fa# menor, 100 BPM, 80 compases. Comparten bajo, pad, acordes y bateria; cada version cambia la
melodia, el sonido del lead, el arpegio y los efectos. FL debe estar cerrado.
"""
import math
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import build_copia as copia
import build_dune as dune
import build_synthwave as song
import flbridge as fl
import flp_edit as flp

KICK, CLAP, HAT, SNARE, BASS, BASS2, PAD, CHORDS, ARP, MELODY = range(10)
CRASH, RISER, IMPACT, AMBIENT = 10, 11, 12, 13
TRACKS = copia.TRACKS + ("Crash", "Riser", "Impacto", "Ambiente")
DRUMS, SYNTHS, REVERB, DELAY = copia.DRUMS, copia.SYNTHS, copia.REVERB, copia.DELAY
FX_INSERT, LEAD_INSERT, AMBIENT_INSERT = 11, 10, 16
EQ = "Fruity Parametric EQ 2/Default.fst"
# capa de ambiente: Pigments con un preset propio. La plantilla es un canal Pigments guardado desde FL.
PIGMENTS_TEMPLATE = Path(__file__).parent / "presets/pigments_template.fst"
AMBIENT_PRESET = "Starlight Ambiente"

# acorde -> (tecla del bajo, notas del pad)
HARMONY = {"F#m": (42, (61, 66, 69)), "D": (38, (62, 66, 69)), "E": (40, (64, 68, 71)),
           "A": (45, (61, 64, 69)), "C#m": (37, (61, 64, 68))}
VERSE = ("F#m", "D", "A", "E")
CHORUS = ("D", "E", "F#m", "A", "D", "E", "C#m", "F#m")
OUTRO = ("F#m", "D", "A", "F#m")
SECTIONS = (("Intro", VERSE * 2), ("Verso", VERSE * 4), ("Build", VERSE), ("Coro", CHORUS * 2),
            ("Break", CHORUS), ("Build 2", VERSE), ("Coro 2", CHORUS * 2), ("Outro", OUTRO * 2))

BASS_STEPS = (1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15)
OFFBEATS = (2, 6, 10, 14)
SIXTEENTHS = (1, 3, 5, 7, 9, 11, 13, 15)
ARPS = {
    "sube": (0, 1, 2, 3, 2, 1, 2, 3),
    "rebote": (0, 2, 1, 3, 0, 2, 1, 3),
    "cascada": (3, 2, 1, 0, 3, 2, 1, 2),
    "doble": (0, 1, 2, 3, 2, 3, 1, 2, 0, 1, 2, 3, 2, 3, 1, 3),
}
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class Version(NamedTuple):
    name: str
    melody: str          # 8 compases separados por |; cada nota es NOMBRE.pasos, r es silencio
    lead: str            # .fxp de Dune 3 o .SerumPreset
    lead_fx: str         # efecto en la pista de la melodia
    arp: str
    decay: float         # segundos de reverb
    reverb: float        # envio de la melodia a la reverb
    delay: float         # envio de la melodia al delay
    gain: float = 0      # dB que necesita este lead para sobresalir unos 2 dB de la mezcla


DUNE_LEADS, SERUM_LEADS = "DUNE 3 Factory/Leads/", "Lead/LD - "
VERSIONS = (
    Version("Himno",
            "A5.6 F#5.2 A5.4 D6.4|B5.6 G#5.2 B5.4 E6.4|C#6.8 A5.4 C#6.4|E6.12 C#6.4|"
            "D6.6 C#6.2 A5.4 F#5.4|G#5.6 B5.2 E6.4 D6.4|C#6.6 B5.2 G#5.4 B5.4|F#5.12 r.4",
            DUNE_LEADS + "80s Upbeat Lead XS.fxp", "Vintage Chorus/Juno 6 Mode I.fst", "sube", 4, .4, .4, 2.9),
    Version("Galope",
            "F#6.3 E6.3 D6.2 A5.3 D6.3 E6.2|B5.3 G#5.3 E5.2 G#5.3 B5.3 E6.2|"
            "C#6.3 A5.3 F#5.2 A5.3 C#6.3 F#6.2|E6.3 C#6.3 A5.2 E6.8|"
            "F#6.3 E6.3 D6.2 A5.3 D6.3 E6.2|B5.3 G#5.3 E5.2 G#5.3 B5.3 E6.2|"
            "E6.3 C#6.3 G#5.2 C#6.3 E6.3 G#6.2|F#6.12 r.4",
            SERUM_LEADS + "Analog Glow.SerumPreset", "Vintage Chorus/Juno 106 Mode I.fst", "rebote", 3, .3, .3, 7.3),
    Version("Eco",
            "D6.2 r.2 D6.2 E6.2 F#6.4 r.4|E6.2 r.2 E6.2 D6.2 B5.4 r.4|C#6.2 r.2 C#6.2 D6.2 E6.4 r.4|"
            "C#6.4 A5.4 E6.8|D6.2 r.2 D6.2 E6.2 F#6.4 A6.4|G#6.4 E6.4 B5.8|"
            "C#6.2 r.2 C#6.2 B5.2 G#5.4 r.4|A5.2 G#5.2 F#5.12",
            DUNE_LEADS + "Stars DH.fxp", "Fruity Delay 3/Diffused.fst", "cascada", 5, .45, .7, 2.4),
    Version("Ascenso",
            "F#5.4 G#5.2 A5.2 B5.4 A5.4|G#5.4 A5.2 B5.2 C#6.4 B5.4|A5.4 B5.2 C#6.2 D6.4 C#6.4|"
            "C#6.4 D6.2 E6.2 F#6.4 E6.4|F#6.8 E6.4 D6.4|E6.8 D6.4 B5.4|C#6.8 B5.4 G#5.4|A5.4 G#5.4 F#5.8",
            SERUM_LEADS + "Bold Voyage.SerumPreset", "Vintage Phaser/Slow and simple.fst", "sube", 4, .35, .35, 10.5),
    Version("Arcade",
            "A5.1 D6.1 F#6.2 A5.1 D6.1 F#6.2 E6.2 D6.2 A5.4|B5.1 E6.1 G#6.2 B5.1 E6.1 G#6.2 F#6.2 E6.2 B5.4|"
            "C#6.1 F#6.1 A6.2 C#6.1 F#6.1 A6.2 G#6.2 F#6.2 C#6.4|A6.4 G#6.2 E6.2 C#6.8|"
            "A5.1 D6.1 F#6.2 A5.1 D6.1 F#6.2 E6.2 D6.2 A5.4|B5.1 E6.1 G#6.2 B5.1 E6.1 G#6.2 F#6.2 E6.2 B5.4|"
            "G#5.1 C#6.1 E6.2 G#5.1 C#6.1 E6.2 D6.2 C#6.2 G#5.4|F#6.4 C#6.4 F#5.8",
            DUNE_LEADS + "Sync Me MK.fxp", "Fruity Flanger/Subtle.fst", "doble", 2.5, .25, .25, 2.3),
    Version("Noche",
            "F#5.8 A5.4 F#5.4|E5.8 G#5.4 B5.4|A5.12 G#5.4|E5.12 r.4|D6.8 C#6.4 A5.4|B5.8 G#5.4 E5.4|"
            "G#5.8 E5.4 G#5.4|F#5.12 r.4",
            DUNE_LEADS + "Dream Sunset RH.fxp", "Vintage Chorus/Retro Chorus MKI.fst", "cascada", 6, .55, .5, 5),
    Version("Salto",
            "D5.2 D6.2 r.2 A5.2 D6.4 E6.4|E5.2 E6.2 r.2 B5.2 E6.4 F#6.4|F#5.2 F#6.2 r.2 C#6.2 F#6.4 E6.4|"
            "A5.2 A6.2 r.2 E6.2 C#6.8|D5.2 D6.2 r.2 A5.2 F#6.4 E6.4|E5.2 E6.2 r.2 B5.2 G#6.4 F#6.4|"
            "C#5.2 C#6.2 r.2 G#5.2 E6.4 C#6.4|F#5.2 F#6.2 r.2 C#6.2 F#6.8",
            SERUM_LEADS + "Lush and Vintage.SerumPreset", "Vintage Chorus/Juno 6 Mode II.fst", "rebote", 4, .35, .45, 10.2),
    Version("Contratiempo",
            "r.2 A5.2 r.2 D6.4 F#6.2 E6.4|r.2 B5.2 r.2 E6.4 G#6.2 F#6.4|r.2 C#6.2 r.2 F#6.4 E6.2 C#6.4|"
            "r.2 C#6.2 r.2 E6.10|r.2 A5.2 r.2 D6.4 A6.2 F#6.4|r.2 G#6.2 r.2 E6.4 D6.2 B5.4|"
            "r.2 C#6.2 r.2 E6.4 D6.2 C#6.4|r.2 A5.2 r.2 F#5.10",
            DUNE_LEADS + "Eighties Analog Brass BT.fxp", "Vintage Phaser/Classic cycle stereo.fst", "sube", 3, .3, .4, 11.1),
    Version("Cometa",
            "A6.6 F#6.2 D6.4 A5.4|G#6.6 E6.2 B5.4 G#5.4|A6.6 F#6.2 C#6.4 A5.4|C#6.2 E6.2 A6.12|"
            "F#6.6 D6.2 A5.4 F#5.4|E6.6 B5.2 G#5.4 E5.4|E6.6 C#6.2 G#5.4 E5.4|F#5.4 A5.4 C#6.4 F#6.4",
            SERUM_LEADS + "Euphoria.SerumPreset", "Fruity Flanger/Slow Flanger.fst", "cascada", 5, .45, .5, 7.1),
    Version("Final",
            "D6.3 D6.1 D6.4 F#6.4 A6.4|G#6.3 G#6.1 G#6.4 E6.8|A6.3 A6.1 A6.4 F#6.4 C#6.4|E6.12 r.4|"
            "D6.3 D6.1 D6.4 E6.4 F#6.4|G#6.3 F#6.1 E6.4 B5.8|C#6.3 D6.1 E6.4 G#6.4 E6.4|F#6.12 r.4",
            DUNE_LEADS + "Prophetic Brass IW.fxp", "Vintage Chorus/Juno 106 Mode II.fst", "rebote", 4, .4, .35, 9.3),
)


def key_of(name):
    return NOTE_NAMES.index(name[:-1]) + 12 * int(name[-1])


def melody_items(text, velocity, bars=16, octave_up=False):
    """Pasa el texto de la melodia a [(paso, largo, tecla, velocidad)], repetido hasta `bars`."""
    items, step = [], 0
    for bar in text.split("|"):
        for token in bar.split():
            name, length = token.split(".")
            if name != "r":
                items.append((step, int(length), key_of(name), velocity))
                if octave_up:
                    items.append((step, int(length), key_of(name) + 12, velocity - 30))
            step += int(length)
    return [(start + cycle * 128, length, key, level) for cycle in range(bars // 8)
            for start, length, key, level in items]


def every_bar(bars, steps, key=60, velocity=100):
    return [(bar * 16 + step, 1, key, velocity) for bar in bars for step in steps]


def bass_line(chords, velocity=100, length=1):
    return [(bar * 16 + step, length, HARMONY[chord][0], velocity)
            for bar, chord in enumerate(chords) for step in BASS_STEPS]


def held(chords, velocity, first_bar=0):
    return [(bar * 16, 16, key, velocity) for bar, chord in enumerate(chords)
            if bar >= first_bar for key in HARMONY[chord][1]]


def arp_line(chords, shape, velocity):
    pattern = ARPS[shape]
    size = 16 // len(pattern)
    items = []
    for bar, chord in enumerate(chords):
        low, middle, high = (key + 12 for key in HARMONY[chord][1])
        tones = (low, middle, high, low + 12)
        items += [(bar * 16 + n * size, size, tones[tone], velocity + (10 if n * size % 4 == 0 else 0))
                  for n, tone in enumerate(pattern)]
    return items


def parts(section, chords, version):
    """Canal -> notas de una seccion."""
    bars = range(len(chords))
    half = len(chords) // 2
    if section == "Intro":
        return {HAT: every_bar(bars[half:], OFFBEATS, velocity=55),
                PAD: held(chords, 80), ARP: arp_line(chords, version.arp, 74)}
    if section == "Verso":
        return {KICK: every_bar(bars, (0, 4, 8, 12), velocity=100),
                CLAP: every_bar(bars[half:], (4, 12), velocity=85),
                HAT: every_bar(bars, OFFBEATS, velocity=80), BASS: bass_line(chords, 70, .75),
                PAD: held(chords, 72), CHORDS: held(chords, 62, half), ARP: arp_line(chords, version.arp, 72)}
    if section in ("Build", "Build 2"):
        return {KICK: every_bar(bars, (0, 4, 8, 12), velocity=112),
                HAT: every_bar(bars, OFFBEATS, velocity=85) + every_bar(bars, SIXTEENTHS, velocity=50),
                SNARE: every_bar(bars[:-1], (4, 12), velocity=95) + [(48 + n, 1, 60, 55 + n * 4) for n in range(16)],
                BASS: bass_line(chords, 95), BASS2: bass_line(chords, 80), PAD: held(chords, 80),
                ARP: arp_line(chords, version.arp, 78), RISER: [(14, 50, 60, 100)]}
    if section in ("Coro", "Coro 2"):
        return {KICK: every_bar(bars, (0, 4, 8, 12), velocity=118), CLAP: every_bar(bars, (4, 12)),
                SNARE: every_bar(bars, (4, 12), velocity=105),
                HAT: every_bar(bars, OFFBEATS, velocity=90) + every_bar(bars, SIXTEENTHS, velocity=45),
                BASS: bass_line(chords), BASS2: bass_line(chords), PAD: held(chords, 85), CHORDS: held(chords, 85),
                ARP: arp_line(chords, version.arp, 85),
                MELODY: melody_items(version.melody, 100, octave_up=section == "Coro 2"),
                CRASH: [(0, 16, 60, 100)], IMPACT: [(0, 32, 60, 110)]}
    if section == "Break":
        return {PAD: held(chords, 80), CHORDS: held(chords, 58), ARP: arp_line(chords, version.arp, 65),
                MELODY: melody_items(version.melody, 78, bars=8)}
    return {PAD: held(chords, 80), ARP: arp_line(chords[:6], version.arp, 70)}


def layers(version):
    """Un patron por instrumento y seccion. Devuelve (patrones, nombres, clips, compases)."""
    patterns, names, clips, start = {}, {}, [], 0
    for section, chords in SECTIONS:
        for channel, items in sorted(parts(section, chords, version).items()):
            number = len(patterns) + 1
            patterns[number] = [(round(step * song.STEP), flp.note(round(step * song.STEP), channel,
                                                                   round(length * song.STEP), key, velocity))
                                for step, length, key, velocity in items]
            names[number] = f"{TRACKS[channel]} {section}"
            last = max(step + length for step, length, _, _ in items)
            clips.append((start, number, channel, math.ceil(last / 16)))
        start += len(chords)
    return patterns, names, clips, start


def routes_for(reverb, delay):
    table = dict(copia.ROUTES)
    table[LEAD_INSERT] = {SYNTHS: 1, REVERB: reverb, DELAY: delay}
    table[FX_INSERT] = {0: 1, REVERB: .3}
    table[AMBIENT_INSERT] = {SYNTHS: 1, REVERB: .45}  # por el Bus Sintes: bombea con el kick
    return table


def pigments_preset(folder, name, preset):
    import pigments
    header, events = flp.read(PIGMENTS_TEMPLATE)
    source = pigments.locate(preset).path
    events = [(event, flp.set_pigments_preset(value, source) if event == flp.PLUGIN_STATE else value)
              for event, value in events]
    path = Path(folder) / f"{name}.fst"
    flp.write(path, header, events)
    return path


def synth_preset(folder, name, patch):
    if patch.endswith(".fxp"):
        return dune.patched_preset(folder, name, patch)
    return copia.serum_preset(folder, name, patch)


def default_sounds(lead):
    sounds = {**copia.DUNE_PATCHES, **copia.SERUM_PRESETS}
    sounds[MELODY] = lead
    return sounds


def assemble(base, project, sounds, lead_fx, routes, patterns, clips, ambient=False):
    """Escribe el .flp: `sounds` da el patch de cada canal de sintetizador.

    `ambient`: True (o el nombre de un preset de Pigments) agrega el canal Ambiente.
    """
    if fl.fl_running():
        raise SystemExit("Cierra FL Studio primero.")
    header, events = flp.read(base)
    flp.set_sample(events, KICK, song.FACTORY + "Kicks\\Linn Kick.wav")
    flp.set_sample(events, HAT, song.FACTORY + "Hats\\Linn CH.wav")
    flp.set_sample(events, SNARE, song.FACTORY + "Snares\\Linn Snare.wav")
    with tempfile.TemporaryDirectory() as folder:
        for channel, name, insert in copia.INSTRUMENTS:
            preset = synth_preset(folder, name, sounds[channel])
            header, index = flp.add_channel(events, header, name, insert, preset=preset)
            if index != channel:
                raise ValueError(f"{name} quedo en el canal {index}")
    packs = song.FACTORY.rsplit("Drums\\", 1)[0]
    for name, sample in (("Crash", song.FACTORY + "Cymbals\\909 Crash.wav"),
                         ("Riser", packs + "Risers\\Riser Noise Takeoff.wv"),
                         ("Impacto", packs + "SFX\\SFX Big Tom.wav")):
        header, _ = flp.add_channel(events, header, name, FX_INSERT, sample=sample)
    if ambient:
        with tempfile.TemporaryDirectory() as folder:
            preset = pigments_preset(folder, "Ambiente", AMBIENT_PRESET if ambient is True else ambient)
            header, index = flp.add_channel(events, header, "Ambiente", AMBIENT_INSERT, preset=preset)
        if index != AMBIENT:
            raise ValueError(f"Ambiente quedo en el canal {index}")
    flp.set_patterns(events, patterns)
    flp.place(events, clips)
    presets = fl._shared_path("FL Studio").parent / "Data/Patches/Plugin presets/Effects"
    effects = copia.EFFECTS + ((7, 0, EQ), (8, 0, EQ), (LEAD_INSERT, 0, lead_fx))
    for insert, slot, preset in effects:
        flp.add_effect(events, insert, slot, flp.effect_block(presets / preset))
    flp.add_effect(events, SYNTHS, 0, copia.epico.sidechain_limiter())
    for insert, levels in routes.items():
        flp.set_routes(events, insert, levels)
    flp.write(project, header, events)


def main(base, project, version):
    patterns, _, clips, bars = layers(version)
    assemble(base, project, default_sounds(version.lead), version.lead_fx,
             routes_for(version.reverb, version.delay), patterns, clips)
    print(f"{version.name}: {len(patterns)} patrones, {len(clips)} clips, {bars} compases", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), VERSIONS[int(sys.argv[3]) - 1])
