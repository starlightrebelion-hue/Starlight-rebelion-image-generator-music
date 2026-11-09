"""Ficha de un tema: historia, direccion visual coherente con la musica, imagen de fondo y SEO para YouTube.

Dos pasos con Ollama. Primero el director creativo arma el concepto con el metodo de historia de Doble Fondo
adaptado al canal (`narrativa_starlight.md`): la imagen no ilustra el titulo, muestra una situacion paralela con dos
planos en el mismo cuadro y un detalle que se descubre. Despues se eligen paleta, procedurales y SEO a partir de ese
concepto. Python revisa todo contra reglas (opciones segun la energia, limites de YouTube, sin artistas ni obras,
personas adultas, sin texto) y anota lo que corrige. La imagen sale de ComfyUI con Flux dev: se generan varias y
queda la mas vistosa.
Deja en la carpeta del tema `ficha.json`, `fondo.png` y `<tema> ficha.md`. No renderiza audio ni video.

Uso: python ficha_tema.py 2048 2049 ...   (o --todas; --sin-imagen para no usar ComfyUI)
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


import agente_musical as agent
import estilo_frequency as style
import equipo_imagen as equipo
import universo
import estudio_imagen as estudio
import fondo_comfy
import seo_youtube as seo
import visual_estilo as visual

OLLAMA_OPTIONS = {"temperature": .7, "num_predict": 900}
# energia de 0 a 1 segun lo que suena
DRUM_ENERGY = {"seca": .3, "corrida": .6, "empuje": 1}
BASS_ENERGY = {"pulso": .2, "contratiempo": .5, "octavas": .7, "galope": 1}
DENSITY_ENERGY = {"espaciada": 0, "media": .5, "activa": 1}
# lo procedural acompana la energia: un tema calmo no gira como un tunel
WARPS_BY_ENERGY = {"calma": ("Marea", "Ascenso"), "media": ("Ascenso", "Caleido", "Tunel"),
                   "alta": ("Tunel", "Vortice", "Caleido")}
SHAPES_BY_ENERGY = {"calma": ("horizonte", "onda"), "media": ("onda", "anillo", "horizonte"),
                    "alta": ("anillo", "corona")}
USES_BY_ENERGY = {"calma": ("estudiar", "relajarse", "trabajar"), "media": ("manejar de noche", "trabajar", "estudiar"),
                  "alta": ("manejar de noche", "gaming")}
# paletas que pide cada imagen de inspiracion, ademas de la del ensamble
IMAGE_PALETTES = {
    "autopista vacia a las tres de la manana": ("Noche", "Plasma"), "ciudad de neon bajo la lluvia": ("Plasma", "Nebula"),
    "ultima nave saliendo de la luna": ("Cristal", "Nebula"), "faros en la niebla costera": ("Cristal", "Cuantico"),
    "arcade cerrado con una maquina encendida": ("Plasma", "Noche"),
    "tormenta electrica en el desierto": ("Supernova", "Plasma"), "tren nocturno cruzando la frontera": ("Noche", "Supernova"),
    "amanecer rojo sobre un puerto": ("Supernova", "Noche"), "rebelion en una estacion orbital": ("Noche", "Cuantico"),
    "cinta vieja de un verano perdido": ("Supernova", "Nebula"), "persecucion por tuneles iluminados": ("Plasma", "Cuantico"),
    "mar quieto bajo dos lunas": ("Nebula", "Cristal"), "torre de control abandonada": ("Cuantico", "Noche"),
    "ruta recta hacia un horizonte violeta": ("Nebula", "Plasma"),
    "ciudad apagada que vuelve a encenderse": ("Noche", "Plasma"),
}
MOOD_BY_SCALE = {"menor natural": "melancolico", "dorica": "esperanzado", "menor armonica": "dramatico",
                 "frigia": "oscuro"}
IMAGE_MODEL = "zimage"  # Z-Image Turbo: look de OVA de los 90 y rapido (9 pasos); schnell y dev daban anime generico
NARRATIVE = Path(__file__).resolve().parent / "narrativa_starlight.md"
SYMBOLS = Path(__file__).resolve().parent / "simbolos_starlight.json"
PHOTOGRAPHER = Path(__file__).resolve().parent / "agentes" / "fotografo.md"
PAUSE = Path(__file__).resolve().parent / "PAUSA_FICHAS"
MINORS = equipo.MINORS  # la misma regla que el equipo de imagen
NOT_DRAWABLE = equipo.NOT_DRAWABLE  # la misma regla que el equipo
# adulto: la palabra o una edad de 25 a 59 ("in his early 40s", "a 35-year-old", "thirties")
ADULT = r"\b(adult|(?:2[5-9]|[3-6][0-9])s?\b|(?:late )?twenties|thirties|forties|fifties|sixties|middle-aged|elderly|old)"
WRITING = r"\b(text|sign|signs|logo|letters|brand|watermark|caption|words|written)\b"
IMAGE_MIN_SCORE = estudio.MIN_SCORE


def energy(plan):
    value = (DRUM_ENERGY[plan["bateria"]] + BASS_ENERGY[plan["bajo"]] + DENSITY_ENERGY[plan["densidad"]]
             + (plan["bpm"] - min(style.TEMPOS)) / (max(style.TEMPOS) - min(style.TEMPOS))) / 4
    label = "calma" if value < .4 else "alta" if value > .65 else "media"
    return round(value, 2), label


def allowed(plan):
    """Lo que la ficha puede elegir para este tema."""
    level = energy(plan)[1]
    palettes = list(dict.fromkeys((visual.BY_ENSEMBLE[plan["ensamble"]], *IMAGE_PALETTES[plan["imagen"]])))
    return {"paleta": palettes, "deformacion": list(WARPS_BY_ENERGY[level]), "forma": list(SHAPES_BY_ENERGY[level]),
            "uso": list(USES_BY_ENERGY[level]),
            "genero": list(seo.SONG_GENRES)}


def prompt_for(plan, choices, concept=None):
    value, level = energy(plan)
    story = json.dumps({key: (concept or {}).get(key) for key in ("tesis", "plano_A", "plano_B", "tension", "motivos",
                                                                   "protagonista", "fotograma", "se_descubre")},
                       ensure_ascii=False)
    return f"""Sos director de arte y responsable de SEO de un canal de YouTube de synthwave instrumental con
ilustraciones de anime cyberpunk de los 90 (una imagen fija con visuales procedurales que reaccionan a la musica).

TEMA
Titulo: {plan['titulo']}
Idea del compositor: {plan['idea']}
Imagen de inspiracion: {plan['imagen']} ({visual.IDEAS.get(plan['imagen'], '')})
{plan['tonica']} {plan['escala']} (caracter {MOOD_BY_SCALE[plan['escala']]}), {plan['bpm']} BPM, energia {level} ({value}),
bateria {plan['bateria']}, bajo {plan['bajo']}, melodia {plan['densidad']} con contorno {plan['contorno']}.

CONCEPTO DE LA IMAGEN (ya decidido por el director creativo)
{story}

OPCIONES PERMITIDAS (usa solo estas)
{json.dumps(choices, ensure_ascii=False)}

QUE DEVOLVES (JSON)
- paleta, deformacion, forma: de las opciones. La paleta va con la luz del concepto; la deformacion y la
  forma acompanan la energia.
- uso: para que se escucha (de las opciones).
- genero: el genero principal para el titulo de YouTube.
- gancho: una frase en ingles, de menos de 110 caracteres, que abra la descripcion con el genero y la emocion.
- descripcion: 2 o 3 frases en ingles que cuenten la situacion del concepto como el comienzo de una historia (sin
  explicar el simbolo ni el detalle que se descubre) y digan para que sirve el tema.
- palabras_clave: 5 a 8 busquedas en ingles, en minuscula, que alguien escribiria para encontrar este tema.
No nombres artistas, canales, peliculas, series ni juegos.
"""


def symbols_used(seed):
    data = json.loads(SYMBOLS.read_text(encoding="utf-8")) if SYMBOLS.is_file() else {}
    return sorted({motif for key, motifs in data.items() if key != str(seed) for motif in motifs})


def register_symbols(seed, motifs):
    data = json.loads(SYMBOLS.read_text(encoding="utf-8")) if SYMBOLS.is_file() else {}
    data[str(seed)] = [motif for motif in motifs if isinstance(motif, str)]
    SYMBOLS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def recent_shots(seed, window=6):
    """Luz y angulo de las ultimas tomas, para que el fotografo no repita siempre la misma."""
    found = []
    for path in agent.OUTPUT.glob("*/ficha.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            number = int(path.parent.name.rsplit(" ", 1)[1])
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        shot = record.get("toma") or {}
        if number < seed and shot.get("luz"):
            found.append((number, f"{shot.get('luz')} / {shot.get('angulo')} / {shot.get('plano')}"))
    return [item for _, item in sorted(found)[-window:]]


def universe_brief(seed):
    """El personaje y el lugar del universo para este tema, con lo que le paso antes (para la historia)."""
    try:
        chosen = universo.cast(seed)
    except (FileNotFoundError, KeyError, ValueError):
        return None
    person, place = chosen["personaje"], chosen["lugar"]
    keys = ("nombre", "alias", "arquetipo", "oficio", "historia", "deseo", "miedo", "contradiccion", "secreto",
            "relaciones")
    return {"personaje": {key: person.get(key) for key in keys}, "aparicion": chosen["aparicion"],
            "lo_que_le_paso_antes": chosen["arco"], "gesto_de_hoy": chosen["gesto"],
            "lugar": {key: place.get(key) for key in ("nombre", "que_pasa", "atmosfera", "utileria")},
            "reglas_del_mundo": universo.load()["reglas"]}


def previous_shots(seed):
    """Resumen de cada imagen ya hecha, para el revisor de continuidad (que no se repitan las tomas)."""
    shots = []
    for path in sorted(agent.OUTPUT.glob("*/ficha.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            number = int(path.parent.name.rsplit(" ", 1)[1])
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        team = (record.get("equipo") or {}).get("equipo") or {}
        if number == seed or not team:
            continue
        scene = (team.get("director") or team.get("escritor") or {}).get("escena", "")
        shots.append({"titulo": path.parent.name, "que_hace": (team.get("director") or {}).get("que_hace", ""),
                      "escena": " ".join(scene.split()[:60]), "lugar": (team.get("arte") or {}).get("lugar", ""),
                      "persona": " ".join((team.get("casting") or {}).get("prompt_visual", "").split()[:14]),
                      "luz": (team.get("fotografo") or {}).get("luz", "")})
    return shots


def recent_people(seed, window=6):
    """Personas y ropa de las ultimas fichas: el equipo tiene que hacer otras (no siempre una chica de campera azul)."""
    found = []
    for path in agent.OUTPUT.glob("*/ficha.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            number = int(path.parent.name.rsplit(" ", 1)[1])
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        team = (record.get("equipo") or {}).get("equipo") or {}
        if number != seed and team.get("casting"):
            person = " ".join(team["casting"].get("prompt_visual", "").split()[:18])
            clothes = "; ".join(team.get("vestuario", {}).get("prendas", [])[:3])
            found.append((number, {"persona": person, "ropa": clothes,
                                   "lugar": team.get("arte", {}).get("lugar", "")}))
    return [item for _, item in sorted(found)[-window:]]


def concept_prompt(plan):
    value, level = energy(plan)
    return f"""=== METODO (obligatorio) ===
{NARRATIVE.read_text(encoding="utf-8")}

Sos el director creativo de un canal de YouTube de synthwave instrumental. Cada tema lleva UNA ilustracion fija estilo
anime cyberpunk de los 90, con visuales que reaccionan a la musica encima. Inventa el concepto de esa imagen.

TEMA
Titulo: {plan['titulo']}
Idea del compositor: {plan['idea']}
Imagen de inspiracion del compositor: {plan['imagen']}
Caracter: {MOOD_BY_SCALE[plan['escala']]}, energia {level} ({value}), {plan['bpm']} BPM.
Simbolos ya usados en otros temas (busca otros distintos): {', '.join(symbols_used(plan['semilla'])) or '(ninguno todavia)'}

DADOS DE ESTA IMAGEN (obligatorios, el concepto se arma alrededor de esto):
{json.dumps(equipo.dice(plan['semilla']), ensure_ascii=False)}
La persona hace la accion de los dados, en el lugar de los dados, y se entiende para que la hace.
PERSONAJE Y LUGAR DEL UNIVERSO DEL CANAL (la historia es de este personaje, con su deseo y su secreto):
{json.dumps(universe_brief(plan['semilla']), ensure_ascii=False)} Nada de pantallas CRT ni cables rojos salvo que los
dados los nombren: ya aparecieron en todos los temas.

Nada de ilustrar el titulo: traduci lo literal. Devolve JSON con:
tesis, traducciones [{{literal, alusivo}}], plano_A {{lugar, luz, objeto, significa}}, plano_B {{lugar, luz, objeto,
significa}}, tension, motivos (1 a 3), ancla_literal, prohibido (lista), protagonista, fotograma, se_descubre,
clima, acento.
protagonista: en ingles, 15 a 60 palabras, adulto joven con la edad escrita (por ejemplo "24 years old"), entre 18 y 30, persona original (nunca un
personaje existente), ropa y peinado, y que esta haciendo.
clima: en ingles, 4 a 12 palabras: hora, tiempo y emocion. Ejemplos: {'; '.join(visual.MOODS)}.
acento: en ingles, el unico color vivo y sobre que objeto cae (el objeto del plano B).
fotograma: en ingles, 30 a 100 palabras: la situacion que se ve (no la camara, de eso se ocupa el fotografo): que
esta haciendo el protagonista, que tecnologia o que objeto le toca el cuerpo y lo conecta con el plano B, que hay
detras (el plano B: una maquina, un robot, una ciudad en una ventana, una pantalla) y de donde viene la luz. Solo cosas
que se ven, en frases cortas y concretas: nada de frases abstractas como "the weight of time". Sin texto, carteles,
logos, marcas ni obras existentes; nada de musica ni efectos. Solo una persona salvo que la historia necesite otra, y
siempre adultas.
"""


def ask_concept(plan, model, feedback=""):
    side = {"type": "object", "properties": {key: {"type": "string"} for key in ("lugar", "luz", "objeto", "significa")},
            "required": ["lugar", "luz", "objeto", "significa"]}
    properties = {"tesis": {"type": "string"},
                  "traducciones": {"type": "array", "items": {"type": "object", "properties": {
                      "literal": {"type": "string"}, "alusivo": {"type": "string"}}}},
                  "plano_A": side, "plano_B": side, "tension": {"type": "string"},
                  "motivos": {"type": "array", "items": {"type": "string"}}, "ancla_literal": {"type": "string"},
                  "prohibido": {"type": "array", "items": {"type": "string"}}, "protagonista": {"type": "string"},
                  "fotograma": {"type": "string"}, "se_descubre": {"type": "string"},
                  "clima": {"type": "string"},
                  "acento": {"type": "string"}}
    body = {"model": model, "prompt": concept_prompt(plan) + feedback, "stream": False, "keep_alive": 0,
            "format": {"type": "object", "properties": properties, "required": list(properties)},
            "options": {"temperature": .9, "num_predict": 1400, "seed": plan["semilla"], "num_ctx": equipo.NUM_CTX}}
    request = urllib.request.Request(agent.OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(json.loads(response.read())["response"])


def check_concept(concept):
    """Problemas del concepto que impiden usarlo. Usa las mismas reglas que el equipo de imagen.

    La edad y la persona las fija despues el casting con los dados: aca solo se revisa que no haya menores.
    """
    problems = []
    for name, low, high in (("protagonista", 10, 110), ("fotograma", 30, 170)):
        text = equipo.plain(concept.get(name, ""))
        problems += [f"{problem.replace(name + ': ', name + ' ')}" for problem in equipo.check_text(name, text, low, high)
                     if "maquina sin" not in problem]
        if seo.banned(text):
            problems.append(f"{name} nombra obras: {seo.banned(text)}")
    mood, accent = equipo.plain(concept.get("clima", "")), equipo.plain(concept.get("acento", ""))
    if not 3 <= len(mood.split()) <= 16 or not equipo.mostly_english(mood):
        problems.append("clima vacio, largo o no en ingles")
    if not accent or not equipo.mostly_english(accent) or len(accent.split()) > 14:
        problems.append("acento vacio o no en ingles")
    if not concept.get("motivos"):
        problems.append("sin motivos")
    return problems


def shot_prompt(plan, concept):
    keys = ("tesis", "plano_A", "plano_B", "tension", "motivos", "protagonista", "fotograma", "se_descubre", "clima", "acento")
    recent = recent_shots(plan["semilla"])
    return f"""{PHOTOGRAPHER.read_text(encoding="utf-8")}

=== CONCEPTO DEL DIRECTOR CREATIVO ===
Tema: {plan['titulo']} ({MOOD_BY_SCALE[plan['escala']]}, energia {energy(plan)[1]})
{json.dumps({key: concept.get(key) for key in keys}, ensure_ascii=False)}

Tomas de los ultimos temas (luz / angulo / plano), varia: {recent or 'ninguna todavia'}
Saca la foto. Devolve el JSON pedido.
"""


def ask_shot(plan, concept, model, feedback=""):
    keys = ("plano", "angulo", "lente", "luz", "expresion", "segundo_plano", "acento", "encuadre", "prompt")
    properties = {key: {"type": "string"} for key in keys}
    properties["en_el_cuerpo"] = {"type": "array", "items": {"type": "string"}}
    body = {"model": model, "prompt": shot_prompt(plan, concept) + feedback, "stream": False, "keep_alive": 0,
            "format": {"type": "object", "properties": properties, "required": list(properties)},
            "options": {"temperature": .8, "num_predict": 900, "seed": plan["semilla"], "num_ctx": equipo.NUM_CTX}}
    request = urllib.request.Request(agent.OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(json.loads(response.read())["response"])


def check_shot(shot):
    """Problemas de la toma del fotografo."""
    problems = []
    prompt = equipo.plain(shot.get("prompt", ""))
    words = len(prompt.split())
    if not 25 <= words <= 900:  # el equipo arma prompts largos a proposito
        problems.append(f"prompt de {words} palabras")
    prompt = re.sub(equipo.NEGATED_WRITING, " ", prompt, flags=re.I)  # "no text" no es pedir texto
    if not equipo.mostly_english(prompt):
        problems.append("prompt con caracteres que no son ingles")
    for pattern, message in ((equipo.WRITING, "pide texto o logos"), (NOT_DRAWABLE, "describe musica o efectos"),
                             (MINORS, "puede mostrar menores")):
        if re.search(pattern, prompt, re.I):
            problems.append(f"prompt {message}")
    if not re.search(ADULT, prompt, re.I):
        problems.append("el prompt no dice que la persona es adulta")
    if seo.banned(prompt):
        problems.append(f"prompt nombra obras: {seo.banned(prompt)}")
    if re.search(r"(mecha|robot|android|machine|exosuit)", prompt, re.I) and "original" not in prompt.lower():
        problems.append("hay un robot o maquina sin 'original machine design' (el modelo dibuja uno famoso)")
    for key in ("plano", "angulo", "luz", "expresion"):
        if not plain(shot.get(key, "")):
            problems.append(f"falta {key}")
    return problems


def ask(plan, choices, model, concept=None):
    properties = {"paleta": {"enum": choices["paleta"]}, "deformacion": {"enum": choices["deformacion"]},
                  "forma": {"enum": choices["forma"]}, "uso": {"enum": choices["uso"]},
                  "genero": {"enum": choices["genero"]}, "gancho": {"type": "string"},
                  "descripcion": {"type": "string"}, "palabras_clave": {"type": "array", "items": {"type": "string"}}}
    body = {"model": model, "prompt": prompt_for(plan, choices, concept), "stream": False, "keep_alive": 0,
            "format": {"type": "object", "properties": properties, "required": list(properties)},
            "options": {**OLLAMA_OPTIONS, "seed": plan["semilla"], "num_ctx": equipo.NUM_CTX}}
    request = urllib.request.Request(agent.OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(json.loads(response.read())["response"])


TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": " - ",
                            "…": "...", " ": " "})


def plain(text):
    """Comillas y guiones tipograficos a ASCII, espacios simples."""
    return re.sub(r"\s+", " ", str(text).translate(TYPOGRAPHY)).strip()


def review(plan, answer, choices, concept=None, shot=None):
    """Ficha revisada y lista de correcciones."""
    rng = random.Random(f"ficha-{plan['semilla']}")
    fixed = []
    ficha = {}
    for key in ("paleta", "deformacion", "forma", "uso", "genero"):
        if answer.get(key) in choices[key]:
            ficha[key] = answer[key]
        else:
            ficha[key] = rng.choice(choices[key])
            fixed.append(f"{key} fuera de las opciones")
    if concept and not check_concept(concept):
        hero, frame = plain(concept["protagonista"]).strip("."), plain(concept["fotograma"]).strip(".")
    else:  # sin concepto valido: un personaje del canal en la imagen de inspiracion
        hero = rng.choice(visual.MOTIFS)
        frame = f"{visual.IDEAS.get(plan['imagen'], plan['imagen'])}, seen at night, rich neon city lights, fog and rain"
        fixed.append("sin concepto valido: imagen por reglas")
    ficha["protagonista"], ficha["fotograma"] = hero, frame
    hook = plain(answer.get("gancho", ""))
    if not hook or len(hook) > 140 or seo.banned(hook) or not hook.isascii():
        hook = f"{ficha['genero']} for {seo.USES[ficha['uso']][0]}: {visual.IDEAS.get(plan['imagen'], '')}."
        fixed.append("gancho reemplazado")
    if not any(genre.lower() in hook.lower() for genre in seo.SONG_GENRES):
        hook = f"{ficha['genero']} · {hook}"
        fixed.append("genero agregado al gancho")
    story = plain(answer.get("descripcion", ""))
    if not story or seo.banned(story) or not story.isascii() or len(story) > 700:
        story = ""
        fixed.append("descripcion descartada")
    keywords = [str(word).strip().lower() for word in answer.get("palabras_clave", []) if isinstance(word, str)]
    keywords = [word for word in keywords if 2 < len(word) <= seo.TAG_LIMIT and word.isascii() and not seo.banned(word)]
    if len(keywords) < 3:
        fixed.append("pocas palabras clave validas")
    year = 2026
    ficha["titulo_youtube"] = seo.song_title(plan["titulo"], ficha["genero"], ficha["uso"], year)
    ficha["descripcion"] = (f"{hook}\n\n{story}\n\n{plan['titulo']} · {plan['bpm']} BPM · {plan['tonica']} "
                            f"{plan['escala'].replace('menor', 'minor').replace('natural', '').replace('armonica', 'harmonic').replace('dorica', 'dorian').replace('frigia', 'phrygian').strip()}"
                            f"\n\n{seo.HASHTAGS}\n").replace("\n\n\n", "\n\n")
    ficha["etiquetas"] = seo.song_tags(plan["titulo"], ficha["genero"], ficha["uso"], keywords)
    ficha["palabras_clave"] = keywords
    problems = seo.check(ficha["titulo_youtube"], ficha["descripcion"], ficha["etiquetas"], plan["titulo"])
    if problems:
        fixed += [f"seo: {problem}" for problem in problems]
    if concept and not check_concept(concept):
        mood, accent = plain(concept["clima"]).strip("."), plain(concept["acento"]).strip(".")
    else:
        mood, accent = rng.choice(visual.MOODS), "one vivid neon accent"
    ficha["clima"], ficha["acento"] = mood, accent
    if shot and not check_shot(shot):
        ficha["toma"] = {key: shot.get(key) for key in ("plano", "angulo", "lente", "luz", "expresion", "en_el_cuerpo",
                                                        "segundo_plano", "acento", "encuadre")}
        picture = plain(shot["prompt"]).strip(".")
    else:
        ficha["toma"] = {}
        picture = f"low angle medium close-up, {hero}, {frame}"
        fixed.append("sin toma del fotografo: imagen con el concepto")
    # Flux pesa mas lo que va primero: la toma del fotografo antes que el estilo
    ficha["prompt_imagen"] = (f"{picture}. Mood: {mood}. Accent: {accent}. {visual.PALETTES[ficha['paleta']][1]}. "
                              f"{visual.STYLE_ZIMAGE if IMAGE_MODEL == 'zimage' else visual.STYLE}")
    return ficha, fixed


def make_image(ficha, seed, folder):
    """El fondo del tema con el estudio de imagen: 3 candidatas, la mejor en grande y postproducida."""
    final, candidates = estudio.render_one(ficha["prompt_imagen"], seed, folder, ficha.get("paleta"), "fondo")
    return final, candidates


def markdown(plan, ficha, fixed, images, concept=None):
    value, level = energy(plan)
    lines = [f"# {plan['titulo']} ({plan['semilla']})", "",
             f"> {plan['idea']}", "",
             "## Musica", "",
             f"- {plan['tonica']} {plan['escala']}, {plan['bpm']} BPM, {plan.get('duracion_seg', '?')} s, estructura {plan['estructura']}",
             f"- Ensamble {plan['ensamble']}, lead {plan['lead']}, ambiente Pigments: {plan.get('ambiente', 'Starlight Ambiente')}",
             f"- Bateria {plan['bateria']}, bajo {plan['bajo']}, arpegio {plan['arpegio']}, melodia {plan['densidad']} ({plan['contorno']})",
             f"- Energia {level} ({value}); caracter {MOOD_BY_SCALE[plan['escala']]}",
             "", "## Direccion visual", "",
             f"- Paleta **{ficha['paleta']}** ({visual.PALETTES[ficha['paleta']][1]})",
             f"- Deformacion principal **{ficha['deformacion']}**, espectro **{ficha['forma']}** (acompanan la energia {level})",
             "- Toma del fotografo: " + "; ".join(f"{key} {value if isinstance(value, str) else ', '.join(value)}"
                                                    for key, value in (ficha.get("toma") or {}).items() if value),
             f"- Clima: {ficha['clima']}; acento: {ficha['acento']}",
             f"- Protagonista: {ficha['protagonista']}",
             f"- Fotograma: {ficha['fotograma']}", ""]
    if concept:
        lines[lines.index("## Direccion visual"):lines.index("## Direccion visual")] = [
            "## Historia (metodo Doble Fondo)", "",
            f"**Tesis:** {concept.get('tesis', '')}", "",
            f"- **Plano A (superficie):** {concept['plano_A'].get('lugar', '')}; luz {concept['plano_A'].get('luz', '')}; "
            f"objeto {concept['plano_A'].get('objeto', '')}. {concept['plano_A'].get('significa', '')}",
            f"- **Plano B (lo que se esconde):** {concept['plano_B'].get('lugar', '')}; luz {concept['plano_B'].get('luz', '')}; "
            f"objeto {concept['plano_B'].get('objeto', '')}. {concept['plano_B'].get('significa', '')}",
            f"- **Tension:** {concept.get('tension', '')}",
            f"- **Motivos:** {', '.join(concept.get('motivos', []))}",
            f"- **Ancla literal:** {concept.get('ancla_literal', '')}",
            f"- **Se descubre:** {concept.get('se_descubre', '')}",
            "- **Traducciones:** " + "; ".join(f"{item.get('literal', '')} -> {item.get('alusivo', '')}"
                                              for item in concept.get("traducciones", []) if isinstance(item, dict)),
            "- **Prohibido:** " + "; ".join(str(item) for item in concept.get("prohibido", [])), ""]
    if images:
        lines += ["![fondo](fondo.png)", "", "| intento | brillo | contraste | color | detalle | puntaje | elegido |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| {item['archivo']} | {item['brillo']} | {item['contraste']} | {item['color']} | {item['detalle']} | "
                  f"{item['puntaje']} | {'si' if item['elegido'] else ''} |" for item in images]
        lines.append("")
    lines += ["## YouTube", "", f"**Titulo:** {ficha['titulo_youtube']}", "", "**Descripcion:**", "", "```",
              ficha["descripcion"].strip(), "```", "", f"**Etiquetas:** {', '.join(ficha['etiquetas'])}", "",
              f"**Palabras clave de Ollama:** {', '.join(ficha['palabras_clave']) or '(ninguna valida)'}", "",
              f"**Uso:** {ficha['uso']}", "",
              "## Revision", ""]
    lines += [f"- {item}" for item in fixed] or ["- Sin correcciones: la respuesta de Ollama paso todas las reglas."]
    lines += ["", "Datos del canal usados: ver `seo_youtube.py` (CTR y horas de las estadisticas de abril 2025). "
              "Son hipotesis: medir CTR y retencion al publicar.", ""]
    return "\n".join(lines)


def folder_of(seed):
    # solo carpetas con su plan: una tanda cortada puede dejar otra carpeta con el mismo numero y sin .json
    found = [path for path in agent.OUTPUT.glob(f"* {seed}") if (path / f"{path.name}.json").is_file()]
    if not found:
        raise SystemExit(f"No hay carpeta con plan para la semilla {seed}")
    return found[0]


def make(seed, model, with_image=True):
    folder = folder_of(seed)
    # la ficha vieja se borra al empezar: si esta falla, la fase de imagenes no tiene que usar la anterior
    (folder / "ficha.json").unlink(missing_ok=True)
    plan_path = folder / f"{folder.name}.json"  # la carpeta tambien tiene ficha.json
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    choices = allowed(plan)
    fixed, concept = [], None
    feedback = ""
    if with_image and fondo_comfy.running():  # Ollama y Flux no entran juntos en 12 GB de video
        fondo_comfy.call("/free", {"unload_models": True, "free_memory": True}, timeout=60)
    for attempt in (1, 2):  # el concepto se rehace una vez, diciendole a Ollama que fallo
        try:
            candidate = ask_concept(plan, model, feedback)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
            fixed.append(f"Ollama no respondio el concepto ({error})")
            break
        problems = check_concept(candidate)
        if not problems:
            concept = candidate
            if attempt == 2:
                fixed.append("concepto rehecho por Ollama")
            break
        fixed.append(f"concepto {attempt} con problemas: {'; '.join(problems)}")
        rejected = folder / "concepto_rechazado.json"
        rejected.write_text(json.dumps({"intento": attempt, "problemas": problems, "concepto": candidate},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        feedback = (f"\nTU CONCEPTO ANTERIOR NO SIRVIO: {'; '.join(problems)}. Era: "
                    f"{json.dumps({k: candidate.get(k) for k in ('protagonista', 'fotograma')}, ensure_ascii=False)}. "
                    "Rehacelo cumpliendo todo.\n")
    if concept is None:  # sin concepto de Ollama no se arma la ficha (nada por reglas ni al azar)
        print(f"[{seed}] {plan['titulo']}: sin ficha, {'; '.join(fixed)}", flush=True)
        return None
    # el equipo de imagen (agentes/README.md) piensa la escena, la persona, la ropa, el lugar y la camara
    brief = {"titulo": plan["titulo"], "idea": plan["idea"], "imagen_de_inspiracion": plan["imagen"],
             "emocion": MOOD_BY_SCALE[plan["escala"]], "energia": energy(plan)[1], "bpm": plan["bpm"],
             "identidad": equipo.CYBERPUNK, "concepto": concept,
             "ya_usado_en_otros_temas": recent_people(plan["semilla"]),
             "dados": equipo.dice(plan["semilla"]),
             "tomas_anteriores": previous_shots(plan["semilla"]),
             "universo": universe_brief(plan["semilla"]),
             "formato": "1920x1080, la persona en el tercio izquierdo o al centro, abajo a la derecha zona tranquila"}
    # ficha completa: el concepto es nuevo, asi que los departamentos se hacen de cero (--mejorar es el que reusa)
    shutil.rmtree(folder / "equipo", ignore_errors=True)
    team = equipo.make(brief, model, seed=plan["semilla"], folder=folder)  # guarda cada departamento
    fixed += [f"equipo: {item}" for item in team["registro"]]
    if not team["prompt"]:
        print(f"[{seed}] {plan['titulo']}: sin ficha, {'; '.join(fixed)}", flush=True)
        return None
    shot = {**team["equipo"]["fotografo"], "prompt": team["prompt"]}
    try:
        answer = ask(plan, choices, model, concept)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
        print(f"[{seed}] {plan['titulo']}: sin ficha, Ollama no respondio ({error})", flush=True)
        return None
    ficha, corrections = review(plan, answer, choices, concept, shot)
    if concept:
        register_symbols(plan["semilla"], concept.get("motivos", []))
    fixed += corrections
    images = []
    if with_image:
        _, images = make_image(ficha, seed, folder)
        best = max(item["puntaje"] for item in images)
        if best < IMAGE_MIN_SCORE:
            fixed.append(f"fondo poco vistoso (puntaje {best}): revisar o regenerar")
    record = {**ficha, "energia": energy(plan), "concepto": concept, "equipo": team, "corregido": fixed,
              "respuesta_ollama": answer,
              "imagenes": images}
    (folder / "ficha.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    rolled = brief.get("dados") or {}
    if rolled.get("personaje"):  # el arco del personaje: lo que hizo en este tema, para que la historia siga
        universo.register(plan["semilla"], plan["titulo"], rolled["personaje"],
                          (team["equipo"].get("director") or {}).get("que_hace", ""), rolled.get("lugar_id"))
    (folder / f"{folder.name} ficha.md").write_text(markdown(plan, ficha, fixed, images, concept), encoding="utf-8")
    print(f"[{seed}] {plan['titulo']}: {ficha['paleta']}/{ficha['deformacion']}/{ficha['forma']}, "
          f"{len(fixed)} correcciones", flush=True)
    return record


def improve(seed, notes, model):
    """Rehace solo los departamentos de `notes` ({rol: "que mejorar"}) y actualiza el prompt de la ficha.

    El concepto, los demas departamentos y el SEO quedan como estaban. Despues hay que correr la fase de imagenes
    (`--solo-imagen`): como el prompt cambio, se generan imagenes nuevas.
    """
    folder = folder_of(seed)
    sheet = folder / "ficha.json"
    if not sheet.is_file():
        print(f"[{seed}] sin ficha.json: hace primero la ficha completa", flush=True)
        return None
    record = json.loads(sheet.read_text(encoding="utf-8"))
    plan = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    saved = folder / "equipo"
    for role, answer in ((record.get("equipo") or {}).get("equipo") or {}).items():
        if not (saved / f"{role}.json").is_file():  # fichas de antes de guardar por departamento
            saved.mkdir(parents=True, exist_ok=True)
            (saved / f"{role}.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
    brief = {"titulo": plan["titulo"], "idea": plan["idea"], "imagen_de_inspiracion": plan["imagen"],
             "emocion": MOOD_BY_SCALE[plan["escala"]], "energia": energy(plan)[1], "bpm": plan["bpm"],
             "identidad": equipo.CYBERPUNK, "concepto": record.get("concepto"),
             "ya_usado_en_otros_temas": recent_people(plan["semilla"]),
             "dados": equipo.dice(plan["semilla"]),
             "tomas_anteriores": previous_shots(plan["semilla"]),
             "universo": universe_brief(plan["semilla"]),
             "formato": "1920x1080, la persona en el tercio izquierdo o al centro, abajo a la derecha zona tranquila"}
    team = equipo.make(brief, model, seed=plan["semilla"], folder=folder, redo=notes)
    if not team["prompt"]:
        print(f"[{seed}] {plan['titulo']}: no se pudo mejorar ({'; '.join(team['registro'][-2:])})", flush=True)
        return None
    shot = {**team["equipo"]["fotografo"], "prompt": team["prompt"]}
    problems = check_shot(shot)
    if problems:
        print(f"[{seed}] {plan['titulo']}: la mejora no paso la revision ({'; '.join(problems)})", flush=True)
        return None
    record["prompt_imagen"] = (f"{equipo.plain(team['prompt']).rstrip('.')}. Mood: {record.get('clima', '')}. "
                               f"Accent: {record.get('acento', '')}. {visual.PALETTES[record['paleta']][1]}. "
                               f"{visual.STYLE_ZIMAGE}")
    record["equipo"] = team
    record["toma"] = {key: shot.get(key) for key in ("plano", "angulo", "lente", "luz", "expresion", "segundo_plano",
                                                     "acento", "encuadre")}
    record.setdefault("mejoras", []).append(notes)
    sheet.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / f"{folder.name} ficha.md").write_text(
        markdown(plan, record, record.get("corregido", []), record.get("imagenes", []), record.get("concepto")),
        encoding="utf-8")
    print(f"[{seed}] {plan['titulo']}: mejorado {', '.join(notes)}; corre --solo-imagen para la imagen nueva", flush=True)
    return record


def images_for(seed):
    """Segunda fase: el fondo de una ficha ya hecha (sin Ollama), y actualiza ficha.json y el .md."""
    folder = folder_of(seed)
    sheet = folder / "ficha.json"
    if not sheet.is_file():
        print(f"[{seed}] sin ficha.json: corre primero la fase de concepto", flush=True)
        return None
    record = json.loads(sheet.read_text(encoding="utf-8"))
    plan = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    _, images = make_image(record, seed, folder)
    fixed = [item for item in record.get("corregido", []) if not item.startswith("fondo poco vistoso")]
    best = max(item["puntaje"] for item in images)
    if best < IMAGE_MIN_SCORE:
        fixed.append(f"fondo poco vistoso (puntaje {best}): revisar o regenerar")
    record.update(imagenes=images, corregido=fixed)
    sheet.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / f"{folder.name} ficha.md").write_text(markdown(plan, record, fixed, images, record.get("concepto")),
                                                    encoding="utf-8")
    print(f"[{seed}] {plan['titulo']}: fondo con puntaje {best}", flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("semillas", nargs="*", type=int)
    parser.add_argument("--todas", action="store_true", help="todos los temas de Agente Frequency")
    parser.add_argument("--sin-imagen", action="store_true",
                        help="fase 1: concepto, visual y SEO con Ollama, sin ComfyUI")
    parser.add_argument("--solo-imagen", action="store_true",
                        help="fase 2: los fondos de fichas ya hechas, con ComfyUI y sin Ollama")
    parser.add_argument("--mejorar", nargs=2, action="append", metavar=("DEPARTAMENTO", "PEDIDO"),
                        help=f"rehace solo ese departamento ({', '.join(equipo.ORDER)}) con ese pedido; se puede "
                             "repetir. Despues correr --solo-imagen")
    parser.add_argument("--modelo", default=agent.DEFAULT_MODEL)
    args = parser.parse_args()
    if args.mejorar:
        unknown = {role for role, _ in args.mejorar} - set(equipo.ORDER)
        if unknown:
            parser.error(f"departamentos que no existen: {sorted(unknown)}; son {', '.join(equipo.ORDER)}")
        sys.stdout.reconfigure(encoding="utf-8")
        notes = {role: note for role, note in args.mejorar}
        try:
            failed = [seed for seed in args.semillas if improve(seed, notes, args.modelo) is None]
        finally:
            equipo.unload(args.modelo)
        if failed:
            print(f"Sin mejorar: {failed}", flush=True)
        return
    if args.solo_imagen and args.sin_imagen:
        parser.error("--solo-imagen y --sin-imagen se excluyen")
    sys.stdout.reconfigure(encoding="utf-8")
    if PAUSE.exists():  # para frenar una tanda encadenada sin cortarla a mitad de un tema
        print(f"Fichas en pausa: borra {PAUSE.name} para seguir.", flush=True)
        return
    seeds = args.semillas or sorted(int(path.name.rsplit(" ", 1)[1]) for path in agent.OUTPUT.glob("* 20*")
                                    if path.is_dir())
    process = None
    if not args.sin_imagen:
        process = fondo_comfy.start(agent.OUTPUT / "comfyui.log")
    try:
        if args.solo_imagen:
            skipped = [seed for seed in seeds if images_for(seed) is None]
        else:
            skipped = [seed for seed in seeds if make(seed, args.modelo, not args.sin_imagen) is None]
        if skipped:
            print(f"Temas sin ficha: {skipped}", flush=True)
    finally:
        if not args.sin_imagen:
            fondo_comfy.call("/free", {"unload_models": True, "free_memory": True}, timeout=60)
        if process:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)


if __name__ == "__main__":
    main()
