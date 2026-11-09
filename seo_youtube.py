"""Ficha de YouTube con la formula de los videos mas vistos del genero: titulo, descripcion y etiquetas.

Copia el patron, no los textos. Las etiquetas no nombran a otros artistas: YouTube lo considera
metadatos enganosos y atrae publico que busca a otro.
"""
import random

BRAND = "STARLIGHT"
YEARS = range(1983, 1995)
GENRES = ("Dreamwave", "Retrowave", "Vaporwave", "Chillsynth", "Cyberwave", "Lovewave", "Spacewave", "Chillwave")
HOOKS = (
    "Neon rain, empty highways and a future that never arrived.",
    "A night transmission from the last rebel station in orbit.",
    "Analog synths, slow pulses and the glow of an old CRT screen.",
    "For late night drives, deep work and the hours nobody remembers.",
)
TAGS = ("synthwave", "retrowave", "dreamwave", "chillwave", "chillsynth", "cyberwave", "cyberpunk", "new synthwave",
        "modern synthwave", "synthwave mix", "space music", "futuristic music", "night drive", "80s music", "anime aesthetic")
HASHTAGS = "#synthwave #retrowave #chillsynth #cyberpunk"


def full_width(text):
    """Letras anchas, el sello visual de estos titulos."""
    return "".join(chr(ord(letter) + 0xFEE0) if "!" <= letter <= "~" else letter for letter in text)


def title(seed):
    rng = random.Random(f"seo-{seed}")
    year = " ".join(str(rng.choice(YEARS)))
    return f"{year}　{full_width(BRAND)} // Synthwave, {', '.join(rng.sample(GENRES, 3))}"


def clock(seconds):
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def description(seed, tracks):
    """tracks: (nombre, segundo de inicio). Con varios temas YouTube arma capitulos solo."""
    hook = random.Random(f"seo-{seed}").choice(HOOKS)
    lines = "\n".join(f"{clock(start)} {name}" for name, start in tracks)
    return f"{hook}\n\nTRACKLIST:\n{lines}\n\n{HASHTAGS}\n"


def tags():
    return list(TAGS)


def sheet(seed, tracks):
    return f"TITULO\n{title(seed)}\n\nDESCRIPCION\n{description(seed, tracks)}\nETIQUETAS\n{', '.join(tags())}\n"


def write(path, name, seed):
    path.write_text(sheet(seed, [(name, 0)]), encoding="utf-8")


# --- ficha de un tema suelto ---------------------------------------------------------------
# Datos observados en el canal del usuario (YouTube Studio, abril 2025; D:/Bandas/Starlight Rebelion/historial canal):
# - las playlists largas "for work" juntaron casi la mitad de las horas vistas (F R E E R I D E 2: 433 de 1233 h);
# - los titulos con genero + "90s anime" + ano rindieron 4,5-5,4 % de CTR; "CYBERPUNK BEATS // NOMBRE" 2-3 %;
# - el titulo en letras separadas (F R E E R I D E) tuvo el CTR mas alto, con pocas impresiones.
# Son pocos datos: hipotesis a medir, no reglas. Al publicar, anotar CTR y retencion para ajustar.
USES = {  # uso -> palabras de busqueda que lo acompanan
    "manejar de noche": ("night drive", "night drive music", "driving music"),
    "trabajar": ("music for work", "focus music", "deep work"),
    "estudiar": ("study music", "music to study", "concentration"),
    "relajarse": ("chill music", "relaxing synth", "late night chill"),
    "gaming": ("gaming music", "cyberpunk gaming", "retro gaming"),
}
SONG_GENRES = ("Synthwave", "Retrowave", "Chillsynth", "Dreamwave", "Spacewave", "Darksynth", "Outrun")
BANNED = ("frequency", "kavinsky", "the midnight", "fm-84", "timecop", "gunship", "perturbator", "carpenter brut",
          "daft punk", "akira", "ghost in the shell", "macross", "robotech", "evangelion", "gundam", "blade runner",
          "tron", "cowboy bebop", "stranger things", "drive soundtrack")
PROPER_ONLY = {"the midnight": "The Midnight", "drive soundtrack": "Drive soundtrack"}
TITLE_LIMIT, TAGS_LIMIT, TAG_LIMIT = 100, 500, 30


def song_title(name, genre, use, year):
    """NOMBRE // Genero · 90s Anime Night Drive Year: el patron que mejor rindio en el canal."""
    words = USES[use][0].title()
    return f"{name.upper()} // {genre} · 90s Anime {words} {year}"


def song_tags(name, genre, use, extra=()):
    tags = [name.lower(), genre.lower(), *USES[use], *extra, *TAGS]
    unique = []
    for tag in tags:
        tag = tag.strip().lower()
        if tag and tag not in unique and len(tag) <= TAG_LIMIT and not banned(tag):
            unique.append(tag)
    while sum(len(tag) + 1 for tag in unique) > TAGS_LIMIT:
        unique.pop()
    return unique


def banned(text):
    """Artistas u obras nombrados, como palabras enteras ("tron" no es "electronics")."""
    import re
    found = []
    for name in BANNED:
        if name in PROPER_ONLY:  # frase comun ("the midnight sky"): solo cuenta escrita como nombre propio
            if PROPER_ONLY[name] in text:
                found.append(name)
        elif re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", text.lower()):
            found.append(name)
    return found


def check(title_text, description_text, tags_list, name):
    """Problemas de una ficha: vacio si esta bien."""
    problems = []
    if len(title_text) > TITLE_LIMIT:
        problems.append(f"titulo de {len(title_text)} caracteres (maximo {TITLE_LIMIT})")
    if name.lower() not in title_text.lower():
        problems.append("el titulo no nombra el tema")
    if not any(genre.lower() in title_text.lower() for genre in SONG_GENRES):
        problems.append("el titulo no dice el genero")
    first = description_text[:150].lower()
    if not any(genre.lower() in first for genre in SONG_GENRES):
        problems.append("el genero no aparece en las primeras lineas de la descripcion")
    if sum(len(tag) + 1 for tag in tags_list) > TAGS_LIMIT:
        problems.append("etiquetas por encima de 500 caracteres")
    for text in (title_text, description_text, " ".join(tags_list)):
        if banned(text):
            problems.append(f"nombra artistas u obras: {banned(text)}")
    return problems
