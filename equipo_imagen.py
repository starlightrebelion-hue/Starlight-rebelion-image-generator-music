"""Equipo de imagen: escritor, casting, vestuario, arte, fotografo y productor, con Ollama (ver agentes/README.md).

Reutilizable: recibe un brief (titulo, idea, emocion, identidad del canal, concepto opcional) y devuelve lo que
decidio cada rol y el prompt largo de la imagen. No genera la imagen (eso es fondo_comfy) ni la postproduce
(postproceso.py). Si Ollama no contesta o un rol falla dos veces, devuelve None: nada al azar ni por reglas.
"""
import json
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

AGENTS = Path(__file__).resolve().parent / "agentes"
OLLAMA = "http://127.0.0.1:11434/api/generate"
# contexto fijo: sin esto Ollama reservaba ~39 GB de RAM y el sistema cortaba la tanda por falta de memoria
NUM_CTX = 16384
# una persona menor; "a child's toy train" o "children's book" son objetos y no cuentan; "minor" no (es adjetivo)
MINORS = (r"\b(child|children|kid|kids|teen|teens|teenager|schoolgirl|schoolboy|young girl|little girl|boy|boys)\b"
          r"(?!\s*['’]s?\s+(?:[a-z]+\s+){0,2}(toy|toys|book|books|drawing|drawings|shoe|shoes|game|games|room|bike|doll|dolls|backpack|bag|coat|jacket|hat|ball|bed|blanket|swing|photo|sneakers?)\b)"
          # 2058: Ollama esquivo el control con "child-sized android" y despues con "a small, still humanoid form"
          r"|\bchild-?(sized|like)\b|\bsmall,? (still |quiet |curled )?(humanoid|figure|form|body)\b"
          r"|\b(humanoid|human-?like) (form|figure|shape)\b")
# oraciones que una camara no ve (revision del 2026-11-08): Ollama esquiva los patrones de MAGIC/ABSTRACT con
# otras palabras, asi que en la escena del director se sacan oraciones enteras con estas marcas (no se inventa nada)
NON_CAMERA = (r"\b(breath|breathing|heartbeat)\b.{0,60}\b(pulse|pulses|pulsing|glow|glows|light|sync|synced|rhythm|"
              r"matches|matching)\b|\b(pulse|pulses|pulsing|glow|glows|light|sync|synced|syncs|rhythm|matches|matching)\b"
              r".{0,60}\b(breath|breathing|heartbeat)\b|\bnot\b|n['’]t\b|^\s*no\b|\b(nonexistent|unseen|invisible|"
              r"magic|magical|physical|physically|grounded|purpose|proof|pattern|alive|latent|awakened|reactivated|"
              r"watching|deliberate)\b|\bas if\b|like a heartbeat|\breflect(ion|s|ed)?\b.{0,80}\b(silhouette|figure|"
              r"someone|skyline|woman|man|face)\b")


def literal(text):
    """Deja solo las oraciones que una camara veria (y saca los remates tipo "One purpose.")."""
    kept = [sentence for sentence in re.split(r"(?<=[.;!?])\s+", plain(text))
            if not re.match(r"\s*one \w+\.?$", sentence, re.I) and not re.search(NON_CAMERA, sentence, re.I)
            and not re.search(MAGIC, sentence, re.I) and not re.search(r"\breversed\b", sentence, re.I)]
    return " ".join(kept)
WRITING = r"\b(text|logo|letters|brand|watermark|caption|written|lettering)\b"
NEGATED_WRITING = (r"\b(no|without|free of|devoid of)\s+(readable\s+|legible\s+|visible\s+|any\s+)?"
                   r"(text|logos?|letters|brands?|watermarks?|captions?|lettering)\b")
# (el \b va solo en las palabras: delante de una comilla impedia encontrar 'Calleway, House 37')
READABLE = (r"(\b(labell?ed|reads|reading|says|saying|spells?|countdown|counting down|binary|digits|numbers)\b|"
            r"\b\d{1,2}:\d{2}\b|\"[A-Za-z][^\"]{2,30}\"|(?<![A-Za-z])'[A-Za-z][^']{2,30}'(?![A-Za-z]))")
SPANISH = (r"\b(lana|goma|cuero|gruesa|acolchado|agrietado|gris|negro|negra|rojo|roja|azul|verde|blanco|con|del|una|"
           r"unos|los|las|muy|pero)\b")
SEQUENCE = (r"\b(then|suddenly|moments? later|after that|before that|is gone|vanishes|disappears|stops|stutters|"
            r"slips|begins|starts to|no longer)\b")
SPANISH_WORDS = {"lana": "wool", "goma": "rubber", "cuero": "leather", "gris": "grey", "negro": "black",
                 "negra": "black", "rojo": "red", "roja": "red", "azul": "blue", "verde": "green", "blanco": "white",
                 "con": "with", "del": "of the", "una": "a", "unos": "some", "los": "the", "las": "the", "muy": "very",
                 "pero": "but", "gruesa": "heavy", "acolchado": "quilted", "agrietado": "cracked"}
# lo que solo describe el casting: si vestuario o arte lo repiten, el prompt se duplica
PERSON = r"\b(in (her|his|their) (early|mid|late) \d0s|years? old|eye is|eyes are|her face|his face|cheekbones)\b"
NOT_DRAWABLE = r"\b(procedural|visuali[sz]er|spectrum|soundwaves?|waveform|equali[sz]er bars|melody (glows|flows|shines|made visible))\b"  # lo abstracto; un microfono o una radio se dibujan
ADULT = r"\b(adult|(?:2[5-9]|[3-6][0-9])s?\b|(?:late )?twenties|thirties|forties|fifties|sixties|middle-aged|elderly|old)"
MACHINES = r"\b(mecha|robot|android|exosuit|walker|tank|machine)\b"
FAMOUS = ("gundam", "evangelion", "macross", "akira", "ghost in the shell", "blade runner", "tron", "bubblegum crisis",
          "armitage", "cowboy bebop", "patlabor", "transformers", "star wars", "alien")
# rol: (archivo, campos de texto, campos lista, campo que va al prompt y su largo en palabras)
ROLES = {
    "escritor": ("escritor.md", ("logline", "momento", "accion_fisica", "mirada", "conflicto_visible", "objeto_clave",
                                 "planos", "escena"), (), ("escena", 50, 170)),
    "director": ("director.md", ("veredicto", "que_hace", "escena"), ("problemas",), ("escena", 40, 160)),
    "casting": ("casting.md", ("nombre", "prompt_visual"), (), ("prompt_visual", 25, 140)),
    "vestuario": ("vestuario.md", ("prompt_visual",), ("prendas", "objetos", "tecnologia"), ("prompt_visual", 45, 180)),
    "arte": ("arte.md", ("lugar", "atmosfera", "prompt_visual"), ("utileria",), ("prompt_visual", 60, 200)),
    "fotografo": ("fotografo.md", ("plano", "angulo", "lente", "luz", "expresion", "segundo_plano", "acento", "encuadre",
                                   "foco", "prompt_camara"), (), ("prompt_camara", 40, 170)),
}
ORDER = ("escritor", "director", "casting", "vestuario", "arte", "fotografo")
# Dados visuales: Ollama repetia siempre la misma persona (mujer, pelo corto oscuro, tapado violeta), el mismo lugar
# (sala tecnica oscura) y la linea laser. Como con la musica, lo que se repite sale de los dados y el equipo arma el
# resto alrededor. El casting y el fotografo tienen que respetarlos (se revisa).
GENDERS = {"woman": r"\b(woman|she|her)\b", "man": r"\b(man|he|his)\b"}
AGES = ((18, 30),)  # el usuario pidio edad al azar entre 18 y 30; siempre adultos (casting y revision lo cuidan)
SKINS = ("pale skin", "olive skin", "light brown skin", "deep brown skin", "dark skin", "freckled tan skin")
HAIR = ("shaved head with a scar", "long black braid", "messy red curls", "short platinum crew cut",
        "black dreadlocks tied back", "bleached mohawk grown out", "short curly afro", "long straight dark hair",
        "undercut with a dyed teal streak", "slicked back black hair", "shaved sides with a short ponytail",
        "wavy shoulder-length auburn hair")
PLACES = ("night market stall under tarps", "late night train carriage", "aircraft hangar", "clandestine street clinic",
          "rooftop water tanks in the rain", "flooded subway tunnel", "truck cabin on a highway", "laundromat at 3 am",
          "bridge maintenance catwalk", "noodle bar counter", "radio tower control hut", "junkyard of crashed drones",
          "elevator stuck between floors", "greenhouse on a megatower", "pawn shop full of old electronics",
          "motel room with a window to the city")
# prenda principal: (texto para el vestuario, palabra que tiene que aparecer). Sin esto todos llevaban campera de
# cuero violeta: la paleta del canal empujaba siempre a lo mismo.
GARMENTS = (("a yellow vinyl raincoat", "raincoat"), ("an orange flight jumpsuit", "jumpsuit"),
            ("an olive military poncho", "poncho"), ("a stained white lab coat", "lab coat"),
            ("a grey suit with a loosened tie", "suit"), ("mechanic overalls in faded red", "overalls"),
            ("a hooded parka with a fur trim", "parka"), ("a long camel wool coat", "coat"),
            ("a quilted bomber jacket in sage green", "bomber"), ("a sleeveless tank top and cargo pants", "tank top"),
            ("a padded motorcycle suit in white and black", "motorcycle suit"),
            ("a knitted fisherman sweater", "sweater"), ("a hospital gown under a borrowed jacket", "gown"),
            ("a tailored crimson blazer", "blazer"))
# accion y objeto: todas eran "alguien con un cable rojo tocando una pantalla CRT"
ACTIONS = ("reading a folded handwritten letter", "loading a cassette into a battered walkman",
           "stitching a cut on their own forearm", "opening an umbrella under a dripping leak",
           "lighting a cigarette with a dying lighter", "handing cash to someone just off frame",
           "pulling a bullet-shaped data chip from behind their ear", "feeding coins into a vending machine",
           "pressing a palm against a rain-streaked window", "tying a red thread around their wrist",
           "taking off a heavy helmet", "holding a polaroid photo up to the light",
           "zipping a duffel bag full of circuit boards", "pouring tea from a dented thermos",
           "kneeling to pick up a dropped key", "tuning an old handheld radio")
ACCENTS = ("amber", "teal", "magenta", "lime green", "gold", "crimson", "cyan", "orange")
LIGHTS = ("Aureola", "Cenital dura", "Lateral de pantalla", "Chispa", "Contraluz de ventana", "Mira laser")
LIGHT_WEIGHTS = (3, 3, 3, 3, 3, 1)  # la linea laser es un recurso de vez en cuando, no la firma de cada imagen


def dice(seed):
    """Lo que tiene que variar de imagen en imagen, sacado de la semilla (la misma semilla da lo mismo).

    Si hay universo (universo/universo.json), la persona, la ropa, el lugar y el gesto son de un personaje del
    universo (rotan entre temas y tienen historia). Si no, salen al azar de las listas de aca.
    """
    import random
    rng = random.Random(f"imagen-{seed}")
    rolled = {"acento": rng.choice(ACCENTS), "luz": rng.choices(LIGHTS, weights=LIGHT_WEIGHTS)[0]}
    try:
        import universo
        chosen = universo.cast(seed)
    except (ImportError, FileNotFoundError, KeyError, ValueError):
        chosen = None
    if chosen:
        person, place = chosen["personaje"], chosen["lugar"]
        return {**rolled, "personaje": chosen["id"], "nombre": person["nombre"], "genero": person["genero"],
                "edad": person["edad"], "aspecto": person["aspecto"], "vestuario": person["vestuario"],
                "objetos": person["objetos"], "implantes": person["implantes"], "lugar": place["prompt"],
                "lugar_id": chosen["lugar_id"], "lugar_nombre": place["nombre"], "accion": chosen["gesto"],
                "aparicion": chosen["aparicion"]}
    low, high = rng.choice(AGES)
    return {**rolled, "genero": rng.choice(list(GENDERS)), "edad": rng.randint(low, high), "piel": rng.choice(SKINS),
            "pelo": rng.choice(HAIR), "lugar": rng.choice(PLACES), "prenda": rng.choice(GARMENTS)[0],
            "accion": rng.choice(ACTIONS)}


def _shared(text, reference):
    """Cuantas palabras de contenido de la referencia aparecen en el texto."""
    words = lambda value: {word for word in re.findall(r"[a-z]{4,}", value.lower())} - STOPWORDS_SHORT
    return len(words(text) & words(reference))


LIGHT_TEXT = {  # el esquema del fotografo en palabras que entiende el modelo de imagen
    "Aureola": "a cold ring of light behind the head like a halo, face in soft shadow with highlights on cheekbones",
    "Cenital dura": "a hard warm beam from directly above, eyes in shadow, cold blue rim light on the hair",
    "Lateral de pantalla": "lit from one side by a glowing screen or visor, half of the face in deep black shadow",
    "Chispa": "lit from below by sparks or a glowing surface, face illuminated from under the chin",
    "Contraluz de ventana": "backlit by a bright window, silhouette with a glowing rim, face barely readable",
    "Mira laser": "blue night, vertical city lights behind, one thin red laser line crossing the frame at eye level",
}
STOPWORDS_SHORT = {"with", "from", "into", "over", "under", "that", "this", "their", "while", "like", "very", "behind"}
# frases que no se pueden pintar y lo magico (el usuario: 'no tiene sentido')
ABSTRACT = (r"\b(the past|the future|is alive|is aware|is real\b|not real|one (second|moment)\b|he is real|she is real|cannot trust|not supposed to|the moment (before|is)|the signal is|the system is|it'?s waiting|is listening|the silence is|does ?n[o']t belong|the action is|no objects|no text|no holograms|no floating|all physical|grounded in the world|serves? no purpose|is focused on the|synthwave|the beat\b|the track\b|the music\b"
            r"|no nonsense|(he|she|they) (is|are) not (waiting|listening|alone|fleeing)|is about to be found"
            r"|not in the mind|in response, but|the tool is functional|responds to (pressure|touch), not)")
MAGIC = (r"\b(floats?|floating|hovers?|hovering) (in )?mid-?air|floats? (above|without)|not on any map|"
         r"(does not|doesn'?t|should not|shouldn'?t) exist|that never (was|were)|in the reflection,? (a|an|the|his|her)|"
         # luces o cables que laten con el cuerpo o "saben" cosas (revision del 2026-11-08: 8 de 15 escenas)
         r"(in (rhythm|sync|time) with|syncs? (with|to)|synced (with|to)) (the |her |his |their |a )?(\w+'s )?"
         r"(breath|breathing|heartbeat|pulse of (her|his))|as if (breathing|alive|it knew)|knows (him|her|them)\b|"
         r"not of this world|(rain|light) that never|hands? moving backward|(image|reflection) (is not|isn'?t) of|"
         r"shadow is not (his|hers|theirs)")
UNWANTED = {"crt": r"\bcrt\b", "cable": r"\bred (cable|wire|cord)s?\b", "laser": r"\blaser\b"}
UNWANTED["ojos cerrados"] = r"\b(eyes (are |half )?closed|closed eyes|eyes shut)\b"  # el usuario: sin ojos cerrados sin motivo


def _drop_clauses(text, pattern):
    """Saca las frases (o partes entre comas) que nombran algo que no va."""
    kept = []
    for sentence in re.split(r"(?<=[.;])\s+", plain(text)):
        clauses = [clause for clause in re.split(r",\s+", sentence) if not re.search(pattern, clause, re.I)]
        if clauses:
            kept.append(", ".join(clauses))
    return " ".join(kept)


def enforce(role, answer, rolled):
    """Aplica los dados a lo que entrego el rol (Ollama no los respetaba). Devuelve notas de lo que se cambio."""
    if not rolled:
        return []
    key = ROLES[role][3][0]
    text, notes = plain(answer.get(key, "")), []
    for name, pattern in UNWANTED.items():  # el CRT, el cable rojo y el laser estaban en todos los temas
        wanted = (name == "laser" and rolled["luz"] == "Mira laser") or name in rolled["accion"]
        if not wanted and re.search(pattern, text, re.I):
            text = _drop_clauses(text, pattern)
            notes.append(f"{role}: saque '{name}'")
    if role == "casting":
        other = [gender for gender in GENDERS if gender != rolled["genero"]][0]
        if re.search(GENDERS[other], text, re.I) and not re.search(r"\b" + rolled["genero"] + r"\b", text, re.I):
            text = _drop_clauses(text, GENDERS[other])
        if rolled.get("aspecto"):  # personaje del universo: su cara es siempre la misma
            # solo la del universo: lo que escribia Ollama era casi siempre OTRA persona inventada con nombre propio
            # ("Another woman, about 30, ...") y el modelo de imagen mezclaba las dos (revision del 2026-11-08)
            text = (f"A young adult {rolled['genero']}, {rolled['edad']} years old, clearly a grown adult: "
                    f"{rolled['aspecto']}. {', '.join(rolled['implantes'])}.")
            answer["nombre"] = rolled["nombre"]
            notes.append(f"casting: personaje del universo ({rolled['nombre']})")
        else:
            text = (f"A young adult {rolled['genero']}, {rolled['edad']} years old, clearly a grown adult with adult "
                    f"proportions and features, {rolled['piel']}, {rolled['pelo']}. {text}")
            notes.append("casting: dados aplicados (genero, edad, piel, pelo)")
    other_person = (r"\b(woman|girl|lady|she)\b" if rolled["genero"] == "man" else r"\b(man|guy|he)\b")
    second = r"\b(woman|girl|lady)\b" if rolled["genero"] == "man" else r"\b(man|guy)\b"
    # si en la escena hay otra persona del otro genero, los pronombres pueden ser de ella: no se tocan
    if (role in ("escritor", "director", "vestuario", "arte", "fotografo") and not re.search(second, text, re.I)
            and other_person):  # pronombres al genero de los dados
        swaps = ({"she": "he", "her": "his", "hers": "his", "herself": "himself"}
                 if rolled["genero"] == "man" else
                 {"he": "she", "his": "her", "him": "her", "himself": "herself"})
        swapped = re.sub(r"\b(" + "|".join(swaps) + r")\b",
                         lambda match: swaps[match.group(0).lower()].capitalize() if match.group(0)[0].isupper()
                         else swaps[match.group(0).lower()], text, flags=re.I)
        if swapped != text:
            text = swapped
            notes.append(f"{role}: pronombres al genero de los dados")
    if role == "vestuario" and rolled.get("vestuario") and _shared(text, rolled["vestuario"]) < 4:
        text = f"Main outfit: {rolled['vestuario']}. Signature objects: {', '.join(rolled['objetos'])}. {text}"
        notes.append("vestuario: ropa y objetos del personaje agregados")
    elif role == "vestuario" and rolled.get("prenda") and dict(GARMENTS)[rolled["prenda"]] not in text.lower():
        text = f"Main garment: {rolled['prenda']}. {text}"
        notes.append("vestuario: prenda de los dados agregada")
    # el director adapta el gesto al lugar (su regla 11): pegarle el gesto crudo delante dejaba dos acciones que se
    # contradicen ("holding an umbrella" + "conecta un cable en la barra"). Solo el escritor, y si falta del todo.
    if role == "escritor" and _shared(text, rolled["accion"]) < 2:
        text = f"The person is {rolled['accion']}. {text}"
        notes.append(f"{role}: accion de los dados agregada")
    if role == "arte" and rolled.get("lugar_id") and _shared(text, rolled["lugar"]) < 4:
        text = f"The place: {rolled['lugar']}. {text}"
        notes.append(f"arte: lugar del universo agregado ({rolled['lugar_nombre']})")
    elif role == "arte" and not rolled.get("lugar_id") and rolled["lugar"].split()[0] not in text.lower():
        text = f"The place is a {rolled['lugar']}. {text}"
        notes.append("arte: lugar de los dados agregado")
    if role == "fotografo":
        answer["luz"] = rolled["luz"]
        text = f"{LIGHT_TEXT[rolled['luz']]}, one {rolled['acento']} accent. {text}"
        notes.append("fotografo: luz y acento de los dados aplicados")
    answer[key] = text
    return notes


# identidad por defecto de este canal: el usuario pidio que sea "mas cyberpunk"
CYBERPUNK = ("Canal de synthwave instrumental. Una sola ilustracion de portada estilo OVA de anime cyberpunk de fines de los "
             "80 y los 90, que se mira mucho tiempo. Cyberpunk de verdad: cuerpos aumentados con implantes, protesis y "
             "puertos; hackers, mercenarios, mensajeros y pilotos de la calle contra corporaciones; megaciudades verticales "
             "con lluvia constante, neones, hologramas y pantallas gigantes (sin texto legible), torres corporativas que "
             "tapan el cielo, cables por todos lados, mercados nocturnos, chatarra de alta tecnologia. Tensiones: rebeldes "
             "contra un sistema que brilla, la noche como escape, nostalgia de un futuro que no llego, romance peligroso "
             "bajo neon. Paleta azul profundo y violeta con un solo acento calido o vivo. Tecnologia retrofuturista: "
             "cables enrulados, relojes de aguja, cintas, cromo gastado.")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
                            "—": " - ", "…": "...", " ": " "})


def plain(text):
    """Comillas tipograficas a ASCII y acentos sueltos sin acento (Ollama mete "é", "×", "°" en textos en ingles)."""
    text = unicodedata.normalize("NFKD", str(text).translate(TYPOGRAPHY))
    text = "".join(char for char in text if char.isascii() or not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.replace("×", "x").replace("°", " degrees")).strip()


def mostly_english(text):
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and sum(char.isascii() for char in letters) / len(letters) > .98


def ask(prompt, schema, model, seed, timeout=600):
    body = {"model": model, "prompt": prompt, "stream": False, "keep_alive": "5m", "format": schema,
            "options": {"temperature": .8, "num_predict": 1500, "seed": seed, "num_ctx": NUM_CTX}}
    request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(json.loads(response.read())["response"])


def check_text(name, text, low, high):
    """Problemas de un texto que va al prompt de imagen."""
    problems = []
    text = plain(text)
    words = len(text.split())
    # "no logos", "without readable text": decir que no haya texto no es pedirlo
    text = re.sub(NEGATED_WRITING, " ", text, flags=re.I)
    if not low <= words <= high * 1.2:  # margen: el recorte de Ollama no siempre llega justo
        problems.append(f"{name}: {words} palabras (entre {low} y {high})")
    if not mostly_english(text):
        problems.append(f"{name}: no esta en ingles")
    for pattern, message in ((WRITING, "pide texto o logos"), (NOT_DRAWABLE, "describe musica o efectos"),
                             (MINORS, "puede mostrar menores")):
        if re.search(pattern, text, re.I):
            problems.append(f"{name}: {message}")
    famous = [title for title in FAMOUS if re.search(r"\b" + re.escape(title) + r"\b", text, re.I)]  # no "electronic"
    if famous:
        problems.append(f"{name}: nombra obras existentes {famous}")
    return problems


def check(role, answer, rolled=None):
    _, texts, lists, (key, low, high) = ROLES[role]
    problems = [f"{role}: falta {field}" for field in texts if not plain(answer.get(field, ""))]
    problems += [f"{role}: {field} vacio" for field in lists if field in ("prendas", "utileria") and not answer.get(field)]
    problems += check_text(f"{role}.{key}", answer.get(key, ""), low, high)
    if role == "casting" and not re.search(ADULT, plain(answer.get("prompt_visual", "")), re.I):
        problems.append("casting: no dice que es adulto ni su edad")
    text = re.sub(NEGATED_WRITING, " ", plain(answer.get(key, "")), flags=re.I)
    if re.search(READABLE, text, re.I):
        problems.append(f"{role}: hay texto o numeros legibles ({re.search(READABLE, text, re.I).group(0)})")
    if re.search(SPANISH, text, re.I):
        problems.append(f"{role}: palabras en castellano en el prompt ({re.search(SPANISH, text, re.I).group(0)})")
    if role in ("escritor", "director", "arte") and re.search(MAGIC, text, re.I):
        problems.append(f"{role}: algo magico o imposible ({re.search(MAGIC, text, re.I).group(0)}); todo tiene que ser fisico")
    if role in ("escritor", "director") and len(re.findall(SEQUENCE, text, re.I)) >= 2:
        problems.append("escritor: cuenta una secuencia en el tiempo; tiene que ser un solo instante")
    if role in ("vestuario", "arte") and re.search(PERSON, text, re.I):
        problems.append(f"{role}: repite a la persona (cara, edad, ojos): describi solo lo tuyo")
    return problems


def role_prompt(role, brief, team, feedback=""):
    method = (AGENTS / ROLES[role][0]).read_text(encoding="utf-8")
    shared = (AGENTS / "README.md").read_text(encoding="utf-8").split("## Reglas comunes a todos los roles", 1)[-1]
    key, low, high = ROLES[role][3]
    return (f"{method}\n\nIMPORTANTE: el campo {key} tiene entre {low} y {high} palabras, en ingles, y describe SOLO "
            f"lo que le toca a tu rol ({role}); no repitas lo que ya decidio el equipo.\n"
            f"\n=== REGLAS COMUNES ==={shared}\n=== BRIEF ===\n{json.dumps(brief, ensure_ascii=False)}\n\n"
            f"=== LO QUE YA DECIDIO EL EQUIPO ===\n{json.dumps(team, ensure_ascii=False)}\n{feedback}\n"
            "Devolve solo el JSON pedido.")


def schema_for(role):
    _, texts, lists, _ = ROLES[role]
    properties = {field: {"type": "string"} for field in texts}
    properties.update({field: {"type": "array", "items": {"type": "string"}} for field in lists})
    return {"type": "object", "properties": properties, "required": list(properties)}


def scrub(role, text):
    """Saca en Python las frases que no le tocan al rol: la persona en vestuario/arte, texto legible, castellano.

    Ollama las repite aunque se le pida que no; cortarlas aca es seguro y no depende de que obedezca.
    """
    patterns = [READABLE, WRITING] + ([PERSON] if role in ("vestuario", "arte") else []) + [ABSTRACT]
    kept = []
    for sentence in re.split(r"(?<=[.;])\s+", plain(text)):
        # el texto entre comillas puede tener comas: se busca en la oracion entera antes de partirla
        if re.search(READABLE, re.sub(NEGATED_WRITING, " ", sentence, flags=re.I), re.I):
            continue
        clauses = [clause for clause in re.split(r",\s+", sentence)
                   if not any(re.search(pattern, re.sub(NEGATED_WRITING, " ", clause, flags=re.I), re.I)
                              for pattern in patterns)]
        if clauses:
            kept.append(", ".join(clauses))
    cleaned = " ".join(kept)
    if role == "director":
        cleaned = literal(cleaned)
    return re.sub(SPANISH, lambda match: SPANISH_WORDS.get(match.group(0).lower(), ""), cleaned, flags=re.I)


def trim(text, high):
    """Ultimo recurso si Ollama no logra acortar: se queda con las oraciones enteras que entran en el largo."""
    kept, words = [], 0
    for sentence in re.split(r"(?<=[.;])\s+", plain(text)):
        size = len(sentence.split())
        if words + size > high and kept:
            break
        kept.append(sentence)
        words += size
    return " ".join(kept)


def condense(text, high, model, seed):
    """Ollama escribe de mas cuando se le pide detalle: lo recorta sin perder lo concreto."""
    schema = {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}
    prompt = (f"Recorta esta descripcion en ingles a {int(high * .7)} palabras como maximo. Conserva todos los objetos, "
              "materiales, colores y marcas concretas; saca adjetivos repetidos, frases que explican sentimientos y "
              'cualquier mencion de texto o logos. Devolve JSON {"texto": ...}.\n\n' + text)
    return ask(prompt, schema, model, seed).get("texto", text)


def repair(text, problems, high, model, seed):
    """Arregla el texto de un rol sin rehacerlo entero: saca lo que no va y lo deja dentro del largo."""
    schema = {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}
    prompt = ("Reescribi esta descripcion en ingles corrigiendo estos problemas: " + "; ".join(problems) + ". "
              f"Maximo {int(high * .8)} palabras. Saca relojes con hora, etiquetas con palabras, numeros, cuentas "
              "regresivas, palabras en castellano, la cara o la edad de la persona si no sos el casting, y cualquier "
              "musica o efecto. Si cuenta una secuencia en el tiempo, deja un solo instante en presente. Si hay una "
              "maquina o robot, termina con 'original machine design'. Conserva todo lo "
              'concreto que sirve. Devolve JSON {"texto": ...}.\n\n' + text)
    return ask(prompt, schema, model, seed).get("texto", text)


def run_role(role, brief, team, model, seed, log, feedback=""):
    """Un rol con un reintento si no pasa la revision; antes de rehacer, intenta reparar. Devuelve su JSON o None."""
    key, _, high = ROLES[role][3]
    for attempt in (1, 2):
        answer = ask(role_prompt(role, brief, team, feedback), schema_for(role), model, seed + attempt)
        log += enforce(role, answer, brief.get("dados"))
        answer[key] = scrub(role, answer.get(key, ""))
        if len(plain(answer.get(key, "")).split()) > high:
            answer[key] = condense(answer[key], high, model, seed)
            log.append(f"{role}: {key} recortado a {len(plain(answer[key]).split())} palabras")
        problems = check(role, answer, brief.get("dados"))
        fixable = not any("falta" in problem or "vacio" in problem for problem in problems)
        if problems and fixable:
            answer[key] = scrub(role, repair(answer[key], problems, high, model, seed))
            log.append(f"{role}: reparado ({'; '.join(problems)})")
            if len(plain(answer[key]).split()) > high * 1.2:
                answer[key] = trim(answer[key], high)
                log.append(f"{role}: cortado en {len(answer[key].split())} palabras")
            problems = check(role, answer, brief.get("dados"))
        if not problems:
            return answer
        log.append(f"{role} intento {attempt}: {'; '.join(problems)}")
        feedback = f"\nTU RESPUESTA ANTERIOR NO SIRVIO: {'; '.join(problems)}. Rehacela cumpliendo todo.\n"
    return None


STOPWORDS = set("""the a an and or of to in on at by with from into onto over under her his their its is are was
be as that this it while for one two up out off down near behind beside against across through""".split())
REPEATED_COMBOS = ((r"\b(cable|wire|cord|plug)", r"\b(screen|monitor|crt|tv|television)\b"),
                   (r"\b(palm|hand)\b", r"\b(window|glass)\b"))
SIMILAR = .3   # parte de palabras en comun desde la que dos escenas se consideran la misma toma


def words(text):
    return {word for word in re.findall(r"[a-z]{4,}", plain(text).lower()) if word not in STOPWORDS}


def _together(first, second, text):
    """Las dos cosas en la misma oracion (en todo un parrafo aparecen juntas por casualidad)."""
    return any(re.search(first, sentence, re.I) and re.search(second, sentence, re.I)
               for sentence in re.split(r"(?<=[.;!?])\s+", plain(text)))


def similar_shots(scene, previous):
    """Tomas anteriores que se parecen a esta: muchas palabras en comun o el mismo combo de objetos."""
    found = []
    mine = words(scene)
    for shot in previous:
        theirs = words(shot.get("escena", ""))
        overlap = len(mine & theirs) / max(1, min(len(mine), len(theirs)))
        combo = any(_together(a, b, scene) and _together(a, b, shot.get("escena", "")) for a, b in REPEATED_COMBOS)
        if overlap >= SIMILAR or combo:
            found.append({"titulo": shot.get("titulo"), "parecido": round(overlap, 2), "mismo_combo": combo})
    return found


def continuity(brief, team, model, seed):
    """Revisor de continuidad (agentes/continuidad.md): compara la toma nueva con las anteriores."""
    previous = brief.get("tomas_anteriores") or []
    if not previous:
        return {"repetida": False, "se_parece_a": [], "cambios": []}
    shot = {"que_hace": team["director"].get("que_hace"), "escena": team["director"].get("escena"),
            "lugar": team["arte"].get("lugar"), "persona": team["casting"].get("prompt_visual", "")[:160],
            "ropa": team["vestuario"].get("prendas", [])[:2], "luz": team["fotografo"].get("luz"),
            "encuadre": f"{team['fotografo'].get('plano')} / {team['fotografo'].get('angulo')}"}
    measured = similar_shots(shot["escena"] or "", previous)
    schema = {"type": "object", "properties": {"repetida": {"type": "boolean"},
                                               "se_parece_a": {"type": "array", "items": {"type": "string"}},
                                               "cambios": {"type": "array", "items": {"type": "string"}}},
              "required": ["repetida", "se_parece_a", "cambios"]}
    method = (AGENTS / "continuidad.md").read_text(encoding="utf-8")
    text = (f"{method}\n\n=== TOMA NUEVA ===\n{json.dumps(shot, ensure_ascii=False)}\n\n"
            f"=== TOMAS ANTERIORES ===\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"=== MEDICION AUTOMATICA (palabras en comun y combos repetidos) ===\n{json.dumps(measured, ensure_ascii=False)}\n"
            "Si la medicion encontro parecidos, la toma es repetida salvo que veas que de verdad es otra imagen.\n"
            "Devolve solo el JSON pedido.")
    verdict = ask(text, schema, model, seed)
    if measured and not verdict.get("cambios"):  # la medicion manda: si se parece, algo tiene que cambiar
        verdict["repetida"] = True
        verdict["cambios"] = ["director: otra accion con otro objeto, distinta de las tomas parecidas",
                              "fotografo: otro encuadre y otro angulo"]
    verdict["medicion"] = measured
    return verdict


def assemble(team):
    """El prompt largo: camara y luz, la persona, la escena, la ropa y el lugar (lo primero pesa mas)."""
    # la persona va justo despues de la camara: si queda al final, el modelo de imagen la rejuvenece
    parts = (team["fotografo"]["prompt_camara"], f"The person: {team['casting']['prompt_visual']}",
             team["director"]["escena"], f"Wearing: {team['vestuario']['prompt_visual']}",
             f"The place: {team['arte']['prompt_visual']}")
    prompt = " ".join(plain(part).rstrip(".") + "." for part in parts)
    # lo magico tambien se cuela por arte o el fotografo ("rain that never falls", "pulsing with her breath")
    prompt = " ".join(sentence for sentence in re.split(r"(?<=[.;!?])\s+", prompt)
                      if not re.search(MAGIC, sentence, re.I))
    if re.search(MACHINES, prompt, re.I) and "original machine design" not in prompt.lower():
        prompt += " Every machine is an original machine design."  # una vez, al final (cada rol fallaba por esto)
    return prompt


def review(brief, team, prompt, model, seed):
    schema = {"type": "object", "properties": {
        "puntajes": {"type": "object", "properties": {key: {"type": "integer"} for key in
                     ("historia", "coherencia", "detalle", "foco", "identidad", "seguridad")}},
        "aprobado": {"type": "boolean"}, "correcciones": {"type": "array", "items": {"type": "string"}}},
        "required": ["puntajes", "aprobado", "correcciones"]}
    method = (AGENTS / "productor.md").read_text(encoding="utf-8")
    text = (f"{method}\n\n=== BRIEF ===\n{json.dumps(brief, ensure_ascii=False)}\n\n=== EQUIPO ===\n"
            f"{json.dumps(team, ensure_ascii=False)}\n\n=== PROMPT FINAL ===\n{prompt}\n\nDevolve solo el JSON pedido.")
    return ask(text, schema, model, seed)


def unload(model):
    """Saca el modelo de la memoria: Ollama lo deja cargado (~39 GB) y ComfyUI despues no entra."""
    body = json.dumps({"model": model, "keep_alive": 0}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"}), timeout=60)
    except (urllib.error.URLError, TimeoutError):
        pass


def make(brief, model, seed=1, unload_at_end=True, folder=None, redo=None):
    """Corre el equipo. Devuelve {"equipo", "prompt", "productor", "registro"} (prompt None si no se pudo).

    `folder`: guarda la salida de cada departamento en `folder/equipo/<rol>.json` (mas el prompt y el productor). Si
    ya existe, ese departamento no se vuelve a correr: solo se corre lo que falta.
    `redo`: {rol: "que mejorar"}: esos departamentos se rehacen con ese pedido y viendo lo que habian hecho; el resto
    se reusa. Asi una correccion puntual tarda lo que tarda un rol, no el equipo entero.
    Descarga el modelo al terminar, salvo en tandas (`unload_at_end=False`): ahi descarga quien llama, una sola vez.
    """
    try:
        return _make(brief, model, seed, Path(folder) / "equipo" if folder else None, redo or {})
    finally:
        if unload_at_end:
            unload(model)


def _save(saved, name, data):
    if saved:
        saved.mkdir(parents=True, exist_ok=True)
        (saved / name).write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


def _make(brief, model, seed, saved, redo):
    team, log = {}, []
    unknown = set(redo) - set(ORDER)
    if unknown:
        raise ValueError(f"Departamentos que no existen: {sorted(unknown)}. Son: {', '.join(ORDER)}")
    try:
        for role in ORDER:
            path = saved / f"{role}.json" if saved else None
            previous = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None
            if previous and role not in redo:
                team[role] = previous  # ya estaba hecho y no se pidio mejorarlo
                continue
            feedback = ""
            if role in redo:
                feedback = (f"\nMEJORA PEDIDA PARA TU DEPARTAMENTO: {redo[role]}\n"
                            f"Lo que habias entregado antes (mejoralo, no empieces de cero si no hace falta): "
                            f"{json.dumps(previous, ensure_ascii=False) if previous else '(nada)'}\n")
                log.append(f"{role}: mejora pedida ({redo[role]})")
            answer = run_role(role, brief, team, model, seed + (100 if role in redo else 0), log, feedback)
            if answer is None:
                log.append(f"{role}: fallo dos veces")
                _save(saved, "registro.json", log)
                return {"equipo": team, "prompt": None, "productor": None, "registro": log}
            team[role] = answer
            _save(saved, f"{role}.json", answer)
        for round_number in (1, 2):  # hasta dos vueltas de continuidad
            check_repeat = continuity(brief, team, model, seed + round_number)
            _save(saved, "continuidad.json", check_repeat)
            if not check_repeat.get("repetida"):
                break
            log.append(f"continuidad: se parece a {check_repeat.get('se_parece_a')} -> {check_repeat.get('cambios')}")
            asked = {role: [note for note in check_repeat.get("cambios", []) if note.lower().startswith(role)]
                     for role in ORDER}
            for role in ORDER:
                if asked[role]:
                    fixed = run_role(role, brief, team, model, seed + 20 * round_number, log,
                                     f"\nLA TOMA SE PARECE A OTRAS YA HECHAS ({check_repeat.get('se_parece_a')}). "
                                     f"CAMBIOS PEDIDOS: {'; '.join(asked[role])}\n")
                    if fixed:
                        team[role] = fixed
                        _save(saved, f"{role}.json", fixed)
        prompt = assemble(team)
        verdict = review(brief, team, prompt, model, seed)
        if not verdict.get("aprobado"):  # una vuelta de correcciones: rehacen solo los roles nombrados
            notes = verdict.get("correcciones", [])
            log.append(f"productor: {verdict.get('puntajes')} {notes}")
            for role in ORDER:
                mine = [note for note in notes if note.lower().startswith(role)]
                if mine:
                    fixed = run_role(role, brief, team, model, seed + 10, log,
                                     f"\nCORRECCIONES DEL PRODUCTOR: {'; '.join(mine)}\n")
                    if fixed:
                        team[role] = fixed
                        _save(saved, f"{role}.json", fixed)
            prompt = assemble(team)
            verdict = review(brief, team, prompt, model, seed + 10)
        _save(saved, "prompt.txt", prompt)
        _save(saved, "productor.json", verdict)
        _save(saved, "registro.json", log)
        return {"equipo": team, "prompt": prompt, "productor": verdict, "registro": log}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
        log.append(f"Ollama no respondio ({error})")
        _save(saved, "registro.json", log)
        return {"equipo": team, "prompt": None, "productor": None, "registro": log}
