"""Ruta Neon Epica: el mismo tema, armado como en el video de referencia. FL debe estar cerrado.

Cada instrumento va en su propia pista de la playlist, con un patron por seccion.
En el mixer los instrumentos pasan por buses y comparten retornos de reverb y delay.
"""
import struct
import sys
from pathlib import Path

import build_synthwave as song
import flbridge as fl
import flp_edit as flp

SECTION_NAMES = {1: "Intro", 2: "Verso", 3: "Build", 4: "Coro", 5: "Break", 6: "Outro"}
TRACKS = ("Kick", "Clap", "Hat", "Snare", "Bajo", "Arpegio", "Pad", "Lead", "Crash", "Riser", "Impacto")
CHANNELS = {"bass": 4, "arp": 5, "pad": 6, "lead": 7, "crash": 8}
RISER, IMPACT = 9, 10
RISER_TICKS = 1200  # 7.5 s a 100 BPM
RISER_BARS, IMPACT_BARS = 4, 2
BUILD_ENDS = (32, 72)  # compases donde arranca cada Coro
VERSE = 2
VERSE_VELOCITY = {4: .75, 5: .8, 6: .75}  # bajo, arpegio y pad mas suaves: el Coro crece al entrar

DRUMS, SYNTHS, REVERB, DELAY = 12, 13, 14, 15
BUSES = {DRUMS: "Bus Bateria", SYNTHS: "Bus Sintes", REVERB: "Reverb", DELAY: "Delay"}
# pista del mixer -> {destino: nivel}. Kick llega a Sintes en 0: solo dispara el sidechain.
ROUTES = {
    1: {DRUMS: 1, SYNTHS: 0}, 2: {DRUMS: 1, REVERB: .2}, 3: {DRUMS: 1}, 4: {DRUMS: 1, REVERB: .25},
    5: {SYNTHS: 1}, 6: {SYNTHS: 1, REVERB: .3, DELAY: .5}, 7: {SYNTHS: 1, REVERB: .35},
    8: {SYNTHS: 1, REVERB: .4, DELAY: .4}, 9: {DRUMS: 1, REVERB: .3},
    10: {0: 1, REVERB: .3}, 11: {0: 1, REVERB: .5},
    DRUMS: {0: 1}, SYNTHS: {0: 1}, REVERB: {SYNTHS: 1}, DELAY: {REVERB: .3, SYNTHS: 1},
}
# (pista, slot, preset dentro de Plugin presets/Effects)
EFFECTS = (
    (0, 0, "Fruity Parametric EQ 2/Default.fst"),
    (1, 0, "Fruity Parametric EQ 2/Default.fst"), (1, 1, "Fruity Soft Clipper/Default.fst"),
    (4, 0, "LuxeVerb/Envelope/Gated Drum Room.fst"),
    (5, 0, "Fruity Parametric EQ 2/Default.fst"),
    (6, 0, "Vintage Chorus/Juno 6 Mode I.fst"),
    (7, 0, "Vintage Chorus/Juno 6 Mode II.fst"), (7, 1, "Fruity Stereo Enhancer/Default.fst"),
    (8, 0, "Vintage Chorus/Juno 6 Mode I.fst"),
    (DRUMS, 0, "Fruity Compressor/External/Light.fst"),
    (REVERB, 0, "LuxeVerb/Hall/Lush Pad Hall.fst"), (REVERB, 1, "Fruity Parametric EQ 2/Default.fst"),
    (DELAY, 0, "Fruity Delay 3/Ping pong.fst"), (DELAY, 1, "Fruity Parametric EQ 2/Default.fst"),
)


def sidechain_limiter():
    """Copia de un demo de FL un Limiter que escucha su entrada de sidechain 1.

    El numero de entrada no es un parametro: va al final del estado del plugin.
    """
    data = fl._shared_path("FL Studio").parent / "Data/Demo projects/Demo songs"
    _, events = flp.read(next(data.glob("Adam Szabo*Knock Me Out.flp")))
    for n, (event, value) in enumerate(events):
        if event == flp.PLUGIN_STATE and len(value) == 169 and value[-5:-1] == struct.pack("<I", 1):
            start = max(m for m in range(n) if events[m][0] == flp.PLUGIN_NAME)
            return events[start:n + 1]
    raise ValueError("El demo no trae un Limiter con sidechain")


def channel_of(note):
    return struct.unpack("<H", note[1][6:8])[0]


def transpose(note, semitones):
    position, data = note
    key = struct.unpack("<H", data[12:14])[0] + semitones
    return position, data[:12] + struct.pack("<H", key) + data[14:]


def shorten(note, ticks):
    position, data = note
    return position, data[:8] + struct.pack("<I", ticks) + data[12:]


def soften(note, factor):
    position, data = note
    return position, data[:21] + bytes((round(data[21] * factor),)) + data[22:]


def layers():
    """Un patron por instrumento y seccion. Devuelve (patrones, nombres, clips)."""
    patterns, names, used, clips = {}, {}, {}, []
    for section, notes in sorted(song.patterns(CHANNELS).items()):
        for channel in sorted({channel_of(note) for note in notes}):
            number = len(patterns) + 1
            factor = VERSE_VELOCITY.get(channel, 1) if section == VERSE else 1
            patterns[number] = [soften(note, factor) for note in notes if channel_of(note) == channel]
            names[number] = f"{TRACKS[channel]} {SECTION_NAMES[section]}"
            end = max(position + struct.unpack("<I", data[8:12])[0]
                      for position, data in patterns[number])
            used.setdefault(section, []).append((number, channel, -(-end // flp.BAR)))
    bar = 0
    for section, _, bars in song.SECTIONS:
        for start in range(bar, bar + bars, song.PATTERN_BARS):
            clips += [(start, number, channel, length) for number, channel, length in used[section]]
        bar += bars

    riser, impact = len(patterns) + 1, len(patterns) + 2
    position = RISER_BARS * flp.BAR - RISER_TICKS
    patterns[riser] = [(position, flp.note(position, RISER, RISER_TICKS, 60, 100))]
    patterns[impact] = [(0, flp.note(0, IMPACT, IMPACT_BARS * flp.BAR, 60, 110))]
    names.update({riser: "Riser", impact: "Impacto"})
    for end in BUILD_ENDS:
        clips += [(end - RISER_BARS, riser, RISER, RISER_BARS), (end, impact, IMPACT, IMPACT_BARS)]
    return patterns, names, clips


def main(base, project, sounds=None, effects=EFFECTS, pump=None, routes=ROUTES, bass_shift=0, verse_bass_ticks=None):
    if fl.fl_running():
        raise SystemExit("Cierra FL Studio primero.")
    header, events, ch = song.instruments(base, sounds)
    if {key: ch[key] for key in CHANNELS} != CHANNELS:
        raise ValueError(f"Canales inesperados: {ch}")
    packs = song.FACTORY.rsplit("Drums\\", 1)[0]
    header, _ = flp.add_channel(events, header, "Riser", 10, sample=packs + "Risers\\Riser Noise Takeoff.wv")
    header, _ = flp.add_channel(events, header, "Impacto", 11, sample=packs + "SFX\\SFX Big Tom.wav")
    patterns, names, clips = layers()
    if verse_bass_ticks:
        verse = next(number for number, name in names.items() if name == "Bajo Verso")
        patterns[verse] = [shorten(note, verse_bass_ticks) for note in patterns[verse]]
    patterns = {number: [transpose(note, bass_shift) if channel_of(note) == CHANNELS["bass"] else note
                         for note in notes] for number, notes in patterns.items()}
    flp.set_patterns(events, patterns)
    flp.place(events, clips)
    presets = fl._shared_path("FL Studio").parent / "Data/Patches/Plugin presets/Effects"
    for insert, slot, preset in effects:
        flp.add_effect(events, insert, slot, flp.effect_block(presets / preset))
    flp.add_effect(events, SYNTHS, 0, pump or sidechain_limiter())
    for insert, levels in routes.items():
        flp.set_routes(events, insert, levels)
    flp.write(project, header, events)
    print(f"{len(patterns)} patrones, {len(clips)} clips, {len(effects) + 1} efectos: {project}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
