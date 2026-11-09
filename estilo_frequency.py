"""Estetica del agente: todo lo que puede sortear o elegir sin salirse del sonido.

Del video de referencia salen: unos 100 BPM, tonalidad menor, bombo en negras, bajo entre bombos,
pad largo, arpegio agudo de corcheas, reverb de 4 s, bombeo por sidechain y mucho grave. El video
muestra un solo loop de 8 compases: las demas escalas, progresiones y estructuras son extensiones
del genero para dar variedad.
"""
SCALES = {
    "menor natural": (0, 2, 3, 5, 7, 8, 10),
    "dorica": (0, 2, 3, 5, 7, 9, 10),
    "menor armonica": (0, 2, 3, 5, 7, 8, 11),
    "frigia": (0, 1, 3, 5, 7, 8, 10),
}
PENTATONIC_DEGREES = (0, 2, 3, 4, 6)
# Medido en un mix de 85 min del canal (universo_frequency.json): casi todo menor natural, tempos redondos
SCALE_WEIGHTS = {"menor natural": 85, "dorica": 7, "menor armonica": 4, "frigia": 4}
TONICS = {"C": 0, "C#": 1, "D": 2, "E": 4, "F": 5, "G": 7, "G#": 8, "A": 9}
TEMPOS = (86, 90, 95, 100, 110)

# escala -> nombre -> grados desde 0. "i-i-III-VII" queda afuera: es la armonia del video.
VERSES = {
    "menor natural": {"i-VI-III-VII": (0, 5, 2, 6), "i-iv-VI-VII": (0, 3, 5, 6), "i-VII-VI-VII": (0, 6, 5, 6),
                      "i-III-VII-iv": (0, 2, 6, 3), "i-VI-iv-VII": (0, 5, 3, 6),
                      "i-VI-i-VI": (0, 5, 0, 5), "VI-III-i-i": (5, 2, 0, 0), "i-III-VI-i": (0, 2, 5, 0)},
    "dorica": {"i-IV-i-VII": (0, 3, 0, 6), "i-VII-IV-i": (0, 6, 3, 0), "i-III-IV-VII": (0, 2, 3, 6)},
    "menor armonica": {"i-VI-iv-V": (0, 5, 3, 4), "i-iv-V-i": (0, 3, 4, 0), "i-VI-V-V": (0, 5, 4, 4)},
    "frigia": {"i-II-i-vii": (0, 1, 0, 6), "i-II-III-II": (0, 1, 2, 1), "i-vii-II-i": (0, 6, 1, 0)},
}
CHORUSES = {
    "menor natural": {"VI-VII-i-i": (5, 6, 0, 0), "VI-VII-i-III": (5, 6, 0, 2), "III-VII-i-VI": (2, 6, 0, 5),
                      "iv-VI-VII-i": (3, 5, 6, 0), "VI-i-VI-i": (5, 0, 5, 0), "VI-III-VII-iv": (5, 2, 6, 3),
                      "III-VI-i-i": (2, 5, 0, 0)},
    "dorica": {"IV-VII-i-i": (3, 6, 0, 0), "III-IV-i-VII": (2, 3, 0, 6)},
    "menor armonica": {"VI-iv-V-i": (5, 3, 4, 0), "iv-i-V-VI": (3, 0, 4, 5)},
    "frigia": {"II-III-i-i": (1, 2, 0, 0), "VI-vii-II-i": (5, 6, 1, 0)},
}

# (seccion, compases)
STRUCTURES = {
    "clasica": (("Intro", 8), ("Verso", 16), ("Build", 4), ("Coro", 16), ("Break", 8), ("Build", 4),
                ("Coro", 16), ("Outro", 8)),
    "directa": (("Intro", 4), ("Verso", 8), ("Build", 4), ("Coro", 16), ("Verso", 8), ("Build", 4),
                ("Coro", 16), ("Outro", 4)),
    "capas": (("Intro", 8), ("Verso", 8), ("Verso", 8), ("Coro", 8), ("Coro", 8), ("Break", 8), ("Coro", 16),
              ("Outro", 8)),
    "cinematica": (("Intro", 16), ("Verso", 8), ("Build", 4), ("Coro", 8), ("Break", 16), ("Build", 4),
                   ("Coro", 16), ("Outro", 8)),
}

D2, D3 = "DUNE 2 Factory/", "DUNE 3 Factory/"
# niveles: dB sobre la mezcla base, por canal (4 Bajo, 5 Bajo 2, 6 Pad, 7 Acordes, 8 Arpegio)
ENSEMBLES = {
    "Neon": {"sonidos": {4: D2 + "Bass/32 Osc RH.fxp", 5: "Bass/Retro Analog/BA - Neon Drive.SerumPreset",
                         6: D2 + "Pads/Airy Voice Pad RL.fxp", 7: "Synth/SY - Hybrid Synthwave Poly.SerumPreset",
                         8: D3 + "Plucked/Mellow Phased ST.fxp"}, "niveles": {}},
    "Medianoche": {"sonidos": {4: D2 + "Bass/Deep Bass RH.fxp", 5: "Bass/Retro Analog/BA - Analog Classics 2.SerumPreset",
                               6: D3 + "Pads/Big Night EDT.fxp", 7: "Synth/SY - Neon Streets Poly.SerumPreset",
                               8: D2 + "Plucked/Tokyo Pluck JB.fxp"}, "niveles": {}},
    "Retro": {"sonidos": {4: D2 + "Bass/Octave 80s MK.fxp", 5: "Bass/Retro Analog/BA - Analog Classics 4.SerumPreset",
                          6: D3 + "Pads/80s Pad XS.fxp", 7: "Synth/SY - Analog VCO Poly.SerumPreset",
                          8: D2 + "Plucked/Synth Pluck RH.fxp"}, "niveles": {}},
    "Cristal": {"sonidos": {4: D2 + "Bass/Synbass RH.fxp", 5: "Bass/Retro Analog/BA - Analog SQ.SerumPreset",
                            6: D3 + "Pads/Cirrus Sunset EDT.fxp", 7: "Synth/SY - Liquid Square Poly.SerumPreset",
                            8: D3 + "Plucked/Shimmer Me Kindly ST.fxp"}, "niveles": {}},
    "Cine": {"sonidos": {4: D2 + "Bass/Massive SynBas RL.fxp", 5: "Bass/Retro Analog/BA - Analog Classics 1.SerumPreset",
                         6: D3 + "Pads/Cinema Strings MC.fxp", 7: "Synth/SY - Dual PWM Poly.SerumPreset",
                         8: D3 + "Plucked/Bell Pluck RH.fxp"}, "niveles": {}},
}

# lead -> (patch, dB para sobresalir unos 2 dB de la mezcla, medido en Starlight Rebellion)
LEADS = {
    "80s Upbeat": (D3 + "Leads/80s Upbeat Lead XS.fxp", 2.9),
    "Analog Glow": ("Lead/LD - Analog Glow.SerumPreset", 7.3),
    "Stars": (D3 + "Leads/Stars DH.fxp", 2.4),
    "Bold Voyage": ("Lead/LD - Bold Voyage.SerumPreset", 10.5),
    "Sync Me": (D3 + "Leads/Sync Me MK.fxp", 2.3),
    "Dream Sunset": (D3 + "Leads/Dream Sunset RH.fxp", 5),
    "Lush Vintage": ("Lead/LD - Lush and Vintage.SerumPreset", 10.2),
    "Analog Brass": (D3 + "Leads/Eighties Analog Brass BT.fxp", 11.1),
    "Euphoria": ("Lead/LD - Euphoria.SerumPreset", 7.1),
    "Prophetic Brass": (D3 + "Leads/Prophetic Brass IW.fxp", 9.3),
}
LEAD_EFFECTS = {
    "chorus juno": "Vintage Chorus/Juno 6 Mode I.fst",
    "chorus juno 106": "Vintage Chorus/Juno 106 Mode I.fst",
    "chorus retro": "Vintage Chorus/Retro Chorus MKI.fst",
    "phaser lento": "Vintage Phaser/Slow and simple.fst",
    "phaser estereo": "Vintage Phaser/Classic cycle stereo.fst",
    "flanger suave": "Fruity Flanger/Subtle.fst",
    "flanger lento": "Fruity Flanger/Slow Flanger.fst",
    "delay difuso": "Fruity Delay 3/Diffused.fst",
}

ARPS = {
    "sube": (0, 1, 2, 3, 2, 1, 2, 3),
    "rebote": (0, 2, 1, 3, 0, 2, 1, 3),
    "cascada": (3, 2, 1, 0, 3, 2, 1, 2),
    "doble": (0, 1, 2, 3, 2, 3, 1, 2, 0, 1, 2, 3, 2, 3, 1, 3),
}
BASS_STYLES = {
    "galope": (1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15),
    "contratiempo": (2, 3, 6, 7, 10, 11, 14, 15),
    "pulso": (2, 6, 10, 14),
    "octavas": (2, 19, 6, 23, 10, 27, 14, 31),  # 16 o mas = octava arriba; el 27 % de los saltos medidos son octavas
}
DRUM_STYLES = {
    "seca": {"kick": (0, 4, 8, 12), "hats": (2, 6, 10, 14), "fills": ()},
    "corrida": {"kick": (0, 4, 8, 12), "hats": (2, 6, 10, 14), "fills": (1, 3, 5, 7, 9, 11, 13, 15)},
    "empuje": {"kick": (0, 4, 8, 12, 14), "hats": (2, 6, 10), "fills": (3, 7, 11, 15)},
}
CHORD_STYLES = {"sostenidos": ((0, 16),), "golpes": ((0, 3), (6, 3), (12, 3)), "pulso": ((2, 2), (6, 2), (10, 2), (14, 2))}

# (inicio, largo) de un compas: el motivo de la melodia sale de estas celdas
RHYTHMS = {
    "espaciada": (((0, 12), (12, 4)), ((0, 8), (8, 8)), ((0, 6), (8, 8)), ((0, 8), (8, 4), (12, 4))),
    "media": (((0, 6), (6, 2), (8, 4), (12, 4)), ((0, 4), (4, 4), (8, 8)), ((0, 3), (3, 3), (6, 2), (8, 8)),
              ((2, 2), (4, 4), (10, 2), (12, 4))),
    "activa": (((0, 3), (3, 3), (6, 2), (8, 3), (11, 3), (14, 2)), ((0, 2), (2, 2), (4, 4), (8, 2), (10, 2), (12, 4)),
               ((0, 1), (1, 1), (2, 2), (4, 2), (6, 2), (8, 4), (12, 4))),
}
CONTOURS = ("arco", "sube", "baja", "pendulo", "saltos")
MELODY_POOLS = ("escala", "pentatonica")
DECAYS = (2.5, 3, 4, 5, 6)
SENDS = (.25, .35, .5, .7)

IMAGES = ("autopista vacia a las tres de la manana", "ciudad de neon bajo la lluvia", "ultima nave saliendo de la luna",
          "faros en la niebla costera", "arcade cerrado con una maquina encendida", "tormenta electrica en el desierto",
          "tren nocturno cruzando la frontera", "amanecer rojo sobre un puerto", "rebelion en una estacion orbital",
          "cinta vieja de un verano perdido", "persecucion por tuneles iluminados", "mar quieto bajo dos lunas",
          "torre de control abandonada", "ruta recta hacia un horizonte violeta", "ciudad apagada que vuelve a encenderse")
TITLE_WORDS = (("Neon", "Midnight", "Chrome", "Violet", "Solar", "Electric", "Silent", "Crimson", "Lunar", "Static"),
               ("Horizon", "Runner", "Signal", "Harbor", "Drift", "Empire", "Voyage", "Mirage", "Skyline", "Pulse"))

# capa de ambiente: presets de Pigments (pads largos, de fabrica) segun el caracter del ensamble.
# "Starlight Ambiente" es el propio, derivado de Space Pad con ataque y release largos.
AMBIENTS = {
    "Cristal": ("Starlight Ambiente", "Future Memories", "Glassy Voice", "Shimmer Prime", "Starfield", "Textural Crystal"),
    "Medianoche": ("Dusk Til Dawn", "Behind Dark Mirrors", "Into The Abysses", "Wide Open Planes", "Sweet Darklings"),
    "Cine": ("Far From Home", "Satellite", "Zero Dawn", "A Place to Rest", "Padology"),
    "Retro": ("Voyage", "5th Sweep", "TH Pad", "Xpadz", "Beach Pad"),
    "Neon": ("Diamond Cutter", "Covenent", "Iktan", "Missing Socks", "Ultrasaw Strings"),
}
