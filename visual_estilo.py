"""Direccion de arte del video: paletas, imagen, deformaciones y formas del espectro.

Cada video del canal de referencia usa una sola ilustracion de anime cyberpunk de los 80-90, fija de
principio a fin; lo que se mueve aca es lo procedural. Las paletas vienen de Cosmos.
"""
import random
from typing import NamedTuple

PALETTES = {  # colores de los universos de C:\\cosmos vr trip; las palabras guian a Flux
    "Nebula": (((.1, .4, 1), (.6, .1, .9), (1, .2, .5)), "deep ultramarine, electric violet and hot pink"),
    "Cuantico": (((0, 1, .8), (0, .5, 1), (.1, .9, .4)), "teal, cyan and emerald glow over deep navy"),
    "Supernova": (((1, .5, 0), (1, .1, .1), (1, .9, .2)), "molten orange, crimson and gold over dark indigo"),
    "Cristal": (((.8, .9, 1), (.4, .7, 1), (1, 1, 1)), "icy white, pale blue and silver over midnight blue"),
    "Plasma": (((.9, 0, .6), (.5, 0, .9), (.2, .8, 1)), "magenta, ultraviolet and cyan neon"),
    "Noche": (((.15, .25, .9), (.9, .1, .25), (.3, .8, 1)), "deep indigo shadows, one crimson accent and pale cyan neon"),
}
BY_ENSEMBLE = {"Neon": "Plasma", "Medianoche": "Noche", "Retro": "Supernova", "Cristal": "Cristal", "Cine": "Cuantico"}

MOTIFS = (  # personajes propios: el patron del canal, sin ningun personaje ni obra concreta
    "close-up of an adult woman wearing a heavy VR visor, lips parted, head tilted up, cables behind her",
    "adult cyborg woman with a cracked metal jaw, eyes closed, rain on her face, black hair floating",
    "adult woman pilot in a dark flight suit looking over her shoulder, city lights behind her",
    "adult woman with short dark hair and one glowing cybernetic eye, three quarter portrait, night skyline",
    "adult android woman with pale hair, neck ports and neon tubes, gazing upward with sadness",
    "adult man with a cybernetic eye implant, neon tubes running from his temple, holding a glowing sphere",
    "adult woman sitting at a wall of old CRT monitors, seen from the side, tired eyes, soft screen light",
    "adult woman in a red armored jacket in front of a giant dark tower, wind in her hair",
    "adult woman in a long coat in front of a huge dormant mecha under a starry sky",
    "two adult silhouettes facing each other above a sea of clouds at violet dusk",
)
IDEAS = {  # Flux entiende mejor el ingles; las claves son las imagenes de estilo_frequency.py
    "autopista vacia a las tres de la manana": "an empty highway at three in the morning",
    "ciudad de neon bajo la lluvia": "a neon city in the rain",
    "ultima nave saliendo de la luna": "the last ship leaving the moon",
    "faros en la niebla costera": "lighthouses in coastal fog",
    "arcade cerrado con una maquina encendida": "a closed arcade with one machine still lit",
    "tormenta electrica en el desierto": "a lightning storm over the desert",
    "tren nocturno cruzando la frontera": "a night train crossing the border",
    "amanecer rojo sobre un puerto": "a red dawn over a harbor",
    "rebelion en una estacion orbital": "a rebellion on an orbital station",
    "cinta vieja de un verano perdido": "an old tape of a lost summer",
    "persecucion por tuneles iluminados": "a chase through lit tunnels",
    "mar quieto bajo dos lunas": "a still sea under two moons",
    "torre de control abandonada": "an abandoned control tower",
    "ruta recta hacia un horizonte violeta": "a straight road to a violet horizon",
    "ciudad apagada que vuelve a encenderse": "a dark city coming back to light",
}
# 2026-11-07: el estilo anterior ("flat cel shading, faded") daba imagenes insipidas; este pide luz, profundidad y
# detalle. Comparado con la misma escena en Flux schnell.
# El usuario pidio despues "clima" y "calidad de poster": un solo foco, contraste de escala, espacio vacio, paleta
# corta con un acento y atmosfera. Se saco "lleno de lucecitas", que llenaba la imagen sin hacerla atractiva.
# 2026-11-07, tercera version: el usuario paso referencias (referencias/fotografo/) y pidio un agente fotografo
# (agentes/fotografo.md). Lo que funciona ahi: el personaje adulto llena el cuadro, contrapicado, una luz dura, tinta
# de novela grafica y un solo acento. Las pruebas con "poster" daban figuras chicas y caras de anime moderno.
STYLE = ("still frame from a late 1980s to 1990s seinen cyberpunk anime OVA crossed with a retro graphic novel, "
         "mature adult character with realistic proportions and sharp angular features, small realistic eyes, "
         "bold black ink linework with fine hatching in the shadows, two-tone cel shading with hard-edged shadows, "
         "airbrushed gradients on skin, glossy specular highlights on hair and metal, one hard key light and deep black "
         "shadows, cold blue and violet palette with one warm or vivid accent, detailed industrial background kept in one "
         "tone, film grain, no text, no letters, no logo, no watermark")
# el piloto del 2026-11-07 salio oscuro y monocromo (brillo 0,10, contraste 0,08): sin una fuente de luz grande y
# colores complementarios, "moody" y "deep shadows" hacian imagenes azules y apagadas.
# composiciones de poster: el director creativo elige una por tema
LAYOUTS = (
    "tiny lone figure against a colossal object in the sky, low horizon, vast empty sky as negative space",
    "figure backlit in a frame of light (doorway, hatch, window), strong leading lines converging on the figure",
    "extreme close-up profile filling one side of the frame, the whole world reflected in a visor or glass on the other",
    "split composition divided by a horizon, water line or glass: calm surface world above, the hidden world below",
    "low angle hero shot, figure towering against a storm sky, hard rim light",
    "top-down view, small figure in a vast geometric pattern of lights and shadows",
    "symmetrical one-point perspective, figure walking away down a long corridor, bridge or road toward a glowing light",
    "silhouette on a high ledge in the foreground, an immense city or landscape glowing far below in haze",
)
# clima: tiempo, hora y temperatura emocional
MOODS = ("rain at blue hour, wet and lonely", "thick fog after midnight, quiet and suspicious",
         "heat haze at dawn, exhausted hope", "snow falling through neon, cold and tender",
         "storm about to break, electric tension", "dust and wind at dusk, restless",
         "humid summer night, warm and nostalgic", "clear frozen night under stars, vast and silent")


class Warp(NamedTuple):
    """Deformacion por cuadro, a la manera de un preset de MilkDrop."""
    zoom: float     # >1 acerca: el dibujo huye hacia afuera
    spin: float     # radianes por segundo
    wave: float     # ondulacion
    decay: float    # cuanto queda del cuadro anterior a 60 cuadros por segundo
    lift: float     # corrimiento vertical
    fold: float     # 1 = caleidoscopio


WARPS = {
    "Tunel": Warp(1.018, .10, .0012, .965, 0, 0),
    "Vortice": Warp(1.012, .55, .0022, .96, 0, 0),
    "Marea": Warp(1.004, .03, .0060, .955, 0, 0),
    "Ascenso": Warp(1.006, 0, .0018, .95, .0022, 0),
    "Caleido": Warp(1.014, .22, .0016, .955, 0, 1),
}
SHAPES = ("anillo", "horizonte", "onda", "corona")  # el orden es el indice que usa el shader
PLANET_TYPES = 4


class Direction(NamedTuple):
    palette: str
    colors: tuple
    prompt: str
    warps: tuple    # una por escena, se recorren en orden
    shapes: tuple
    planet: int
    seed: int


def wallpaper_prompt(motif, palette, idea=None):
    theme = f"inspired by {IDEAS.get(idea, idea)}, " if idea else ""
    return f"{motif}, {theme}{PALETTES[palette][1]}, {STYLE}"


def direct(seed, palette=None, idea=None):
    """Tira los dados de la puesta visual. La misma semilla da el mismo video."""
    rng = random.Random(f"video-{seed}")
    palette = palette or rng.choice(list(PALETTES))
    motif = rng.choice(MOTIFS)
    warps = rng.sample(list(WARPS), len(WARPS))
    shapes = rng.sample(SHAPES, len(SHAPES))
    return Direction(palette, PALETTES[palette][0], wallpaper_prompt(motif, palette, idea), tuple(warps), tuple(shapes),
                     rng.randrange(PLANET_TYPES), seed)


def from_ficha(ficha, seed):
    """La puesta que eligio la ficha del tema: su paleta, y su deformacion y forma primero."""
    rng = random.Random(f"video-{seed}")
    warps = [ficha["deformacion"]] + rng.sample([w for w in WARPS if w != ficha["deformacion"]], len(WARPS) - 1)
    shapes = [ficha["forma"]] + rng.sample([s for s in SHAPES if s != ficha["forma"]], len(SHAPES) - 1)
    return Direction(ficha["paleta"], PALETTES[ficha["paleta"]][0], ficha["prompt_imagen"], tuple(warps), tuple(shapes),
                     rng.randrange(PLANET_TYPES), seed)


# Z-Image Turbo (2026-11-07): con este estilo dio el look de OVA de los 90 que buscaba el usuario, sin LoRA.
STYLE_ZIMAGE = ("comic book cover composition: one dramatic story moment, dynamic pose with energy, bold "
                "perspective and foreshortening, the character's hands and the key object clearly readable, "
                "polished anime key visual, late 1980s and 1990s cyberpunk OVA aesthetic, retro science fiction illustration, "
                "clean confident linework, cel shading with soft painted gradients, glossy reflections on metal and hair, "
                "cinematic lighting with warm key light and cold rim light, rich atmosphere, deep blue and violet palette "
                "with one vivid accent, highly detailed original mechanical design, young adult characters (18 to 30) with "
                "clearly grown-up adult features and proportions, "
                "no text, no letters, no logo")

# Para las imagenes de referencia (retrato, lugar, objeto): el mismo dibujo de OVA de los 90 sin "portada de comic"
# ni "pose con energia", que arruinarian una hoja de personaje neutra.
# lugares y objetos NO usan el estilo de personaje: "character design ... young adult characters" metia una persona
# en cada imagen de lugar (y Z-Image Turbo con cfg 1 no usa el negativo). Fondos pintados vacios y objetos sueltos.
STYLE_ZIMAGE_PLACE = ("anime background art, painted environment plate, late 1980s and 1990s cyberpunk OVA aesthetic, "
                      "detailed architecture and props, cel shading with soft painted gradients, atmospheric depth, "
                      "an empty place with nobody in it, no people, no figures, no text, no letters, no logo")
STYLE_ZIMAGE_OBJECT = ("anime prop design, a single object on its own, late 1980s and 1990s cyberpunk OVA aesthetic, clean "
                       "confident linework, cel shading, glossy reflections on metal, plain grey background, no people, "
                       "no hands, no text, no letters, no logo")
STYLE_ZIMAGE_REF = ("polished anime character design reference, late 1980s and 1990s cyberpunk OVA aesthetic, clean "
                    "confident linework, cel shading with soft painted gradients, glossy reflections on metal and hair, "
                    "even soft studio light, highly detailed original design, young adult characters (18 to 30) with "
                    "clearly grown-up adult features and proportions, no text, no letters, no logo")
