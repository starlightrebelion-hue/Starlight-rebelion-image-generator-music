"""Guion de StoryForge: premisa -> secuencias -> escenas -> planos, con texto Fountain editable, versiones, .fdx y
generacion encadenada con Ollama (cada paso es una propuesta que se acepta o se descarta, nunca se pisa sola).

Modelo (guion.json del proyecto, clave "secuencias"):
  {"premisa": "...", "secuencias": [{"id": "s1", "titulo", "sinopsis", "escenas": [
      {"id": "e1", "int_ext": "EXT.", "lugar": "MERCADO", "lugar_id": "mercado_nocturno", "momento": "NOCHE",
       "accion": "...", "dialogos": [{"personaje", "parentetico", "texto"}], "elenco": [ids], "estado": "guardada",
       "notas": "...", "tema": 2051 (si la escena es un tema de musica), "planos": [
           {"id": "p1", "tipo": "PM", "que_se_ve": "...", "accion": "...", "duracion": 3.0, "estado": "pendiente"}]}]}]}
Los guiones viejos de Ejemplo 1 (actos -> secuencias -> temas) se convierten al leerlos.

El parser Fountain y el .fdx son los de Doble Fondo (scripts/guion_literario.py), portados.
"""
import datetime
import json
import re
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

import decoupage_sf as dc
import equipo_imagen as equipo
import referencias as ref
import universo

AGENTS = Path(__file__).resolve().parent / "agentes"
SHOT_TYPES = ("PG", "PC", "PA", "PM", "PP", "PPP", "escorzo", "inserto", "POV")
STATES = ("guardada", "revision", "oculta")
HEADING = re.compile(r"^(\.(?!\.)|(INT|EXT|EST|INT\./EXT|INT/EXT|I/E)[.\s])", re.I)
TRANSITION = re.compile(r"^(>(?!.*<\s*$)|[A-ZÁÉÍÓÚÑ\s]+(TO|A):$|FUNDIDO.*|CORTE.*:$)")
CHARACTER = re.compile(r"^@?[A-ZÁÉÍÓÚÑÜ0-9][A-ZÁÉÍÓÚÑÜ0-9 .'\-]*(\s*\([^)]*\))?\s*\^?$")


# lo mismo que equipo_imagen.NON_CAMERA pero en castellano (el guion se escribe en castellano): cosas que laten con la
# respiracion o el corazon, "como si", magia. Sin la regla del "no", que en castellano saca acciones reales.
NON_CAMERA_ES = (r"\b(respiraci[oó]n|respira|latidos?|coraz[oó]n)\b.{0,60}\b(late|laten|pulsa|pulsan|brilla|brillan|"
                 r"ritmo|sincron\w*)\b|\b(late|laten|pulsa|pulsan|brilla|brillan|ritmo|sincron\w*)\b.{0,60}"
                 r"\b(respiraci[oó]n|respira|latidos?|coraz[oó]n)\b|\bcomo si\b|\bm[aá]gic\w*|\binvisible\b|"
                 r"\binexistente\b|\bflota(n)? en el aire\b")


def literal_es(text):
    """Solo las oraciones del guion que una camara puede filmar."""
    kept = [sentence for sentence in re.split(r"(?<=[.;!?])\s+", (text or "").strip())
            if sentence and not re.search(NON_CAMERA_ES, _plain(sentence), re.I)]
    return " ".join(kept)


def _plain(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


# --- leer y guardar --------------------------------------------------------------------------------
def path(folder):
    return Path(folder) / "guion.json"


def _from_songs(saved, data):
    """Ejemplo 1: actos -> secuencias -> temas pasa a secuencias -> escenas (un plano por tema)."""
    overlay = saved.get("escenas", {})
    frozen = universo.frozen()
    acts = saved.get("actos") or []
    if not acts:
        groups = {}
        for seed in ref.song_seeds():
            if not (ref.song_folder(seed) / "equipo").is_dir():   # temas sin escena todavia (solo musica)
                continue
            cast = frozen.get(str(seed)) or {}
            groups.setdefault(cast.get("id") or "sin_elenco", []).append(seed)
        acts = [{"titulo": "Temporada 1", "secuencias": [
            {"titulo": data["personajes"].get(pid, {}).get("nombre", "Sin elenco"), "sinopsis": "", "temas": seeds}
            for pid, seeds in groups.items()]}]
    sequences = []
    for act in acts:
        for number, sequence in enumerate(act.get("secuencias", []), 1):
            scenes = []
            for seed in sequence.get("temas", []):
                folder = ref.song_folder(seed)
                if not folder or not (folder / "equipo").is_dir():
                    continue
                cast = frozen.get(str(seed)) or {}
                writer = ref.read_json(folder / "equipo" / "escritor.json", {}) or {}
                director = ref.read_json(folder / "equipo" / "director.json", {}) or {}
                photographer = ref.read_json(folder / "equipo" / "fotografo.json", {}) or {}
                place = data["locaciones"].get(cast.get("lugar_id"), {})
                plan = dc.load(folder)
                kind = plan["planos"][0]["tipo"] if plan and plan.get("planos") else dc.shot_type(photographer.get("plano"))
                scenes.append({
                    "id": f"t{seed}", "tema": seed, "int_ext": "EXT.", "lugar": (place.get("nombre") or "LUGAR").upper(),
                    "lugar_id": cast.get("lugar_id"), "momento": "NOCHE", "titulo": folder.name.rsplit(" ", 1)[0],
                    "accion": overlay.get(str(seed), {}).get("sinopsis") or writer.get("logline") or "",
                    "dialogos": [], "elenco": [cast["id"]] if cast.get("id") else [], "estado": "guardada",
                    "notas": director.get("que_hace", ""),
                    "planos": [{"id": "p1", "tipo": kind, "que_se_ve": ", ".join(
                        value for value in (photographer.get("plano"), photographer.get("angulo")) if value),
                        "accion": director.get("que_hace", ""), "duracion": None, "estado": "toma"}]})
            sequences.append({"id": f"s{len(sequences) + 1}", "titulo": sequence.get("titulo", f"Secuencia {number}"),
                              "acto": act.get("titulo", ""), "sinopsis": sequence.get("sinopsis", ""), "escenas": scenes})
    return {"premisa": saved.get("premisa", ""), "secuencias": sequences, "convertido_de_temas": True}


def load(folder):
    saved = ref.read_json(path(folder), {}) or {}
    if saved.get("secuencias") is not None:
        return {"premisa": saved.get("premisa", ""), "secuencias": saved["secuencias"], "version": saved.get("version", 0)}
    return _from_songs(saved, universo.load())


def scenes(structure):
    return [scene for sequence in structure["secuencias"] for scene in sequence["escenas"]]


def find_scene(structure, scene_id):
    for sequence in structure["secuencias"]:
        for scene in sequence["escenas"]:
            if scene["id"] == scene_id:
                return sequence, scene
    raise ValueError(f"No hay escena {scene_id}")


def _next_id(prefix, used):
    number = 1
    while f"{prefix}{number}" in used:
        number += 1
    return f"{prefix}{number}"


def clean(structure):
    """Ids unicos, estados validos y planos con tipo conocido (lo que manda la pagina o Ollama)."""
    used_s, used_e = set(), set()
    for sequence in structure["secuencias"]:
        if not sequence.get("id") or sequence["id"] in used_s:
            sequence["id"] = _next_id("s", used_s)
        used_s.add(sequence["id"])
        sequence["titulo"] = str(sequence.get("titulo", ""))[:160]
        sequence["sinopsis"] = str(sequence.get("sinopsis", ""))[:2000]
        for scene in sequence.setdefault("escenas", []):
            if not scene.get("id") or scene["id"] in used_e:
                scene["id"] = _next_id("e", used_e)
            used_e.add(scene["id"])
            scene["estado"] = scene.get("estado") if scene.get("estado") in STATES else "guardada"
            scene["accion"] = str(scene.get("accion", ""))[:6000]
            scene.setdefault("dialogos", [])
            scene.setdefault("elenco", [])
            used_p = set()
            for shot in scene.setdefault("planos", []):
                if not shot.get("id") or shot["id"] in used_p:
                    shot["id"] = _next_id("p", used_p)
                used_p.add(shot["id"])
                shot["tipo"] = shot.get("tipo") if shot.get("tipo") in SHOT_TYPES else "PM"
    return structure


def save(folder, structure, reason="manual"):
    """Guarda la estructura nueva y deja la anterior en versiones/ (las escenas-tema actualizan su sinopsis)."""
    folder = Path(folder)
    current = ref.read_json(path(folder), {}) or {}
    if current:
        versions = folder / "versiones"
        versions.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        ref.write_json(versions / f"guion_{stamp}_{reason}.json", current)
    structure = clean(structure)
    current["premisa"] = structure.get("premisa", current.get("premisa", ""))
    current["secuencias"] = structure["secuencias"]
    current["version"] = int(current.get("version", 0)) + 1
    for scene in scenes(structure):
        if scene.get("tema"):
            current.setdefault("escenas", {}).setdefault(str(scene["tema"]), {})["sinopsis"] = scene["accion"]
    ref.write_json(path(folder), current)
    return current


def versions(folder):
    return sorted((item.name for item in (Path(folder) / "versiones").glob("guion_*.json")), reverse=True)


def restore(folder, name):
    source = (Path(folder) / "versiones" / name).resolve()
    if not source.is_relative_to((Path(folder) / "versiones").resolve()) or not source.is_file():
        raise ValueError("version desconocida")
    saved = ref.read_json(source)
    structure = load_from(saved)
    return save(folder, structure, "restaurada")


def load_from(saved):
    if saved.get("secuencias") is not None:
        return {"premisa": saved.get("premisa", ""), "secuencias": saved["secuencias"]}
    return _from_songs(saved, universo.load())


# --- Fountain ------------------------------------------------------------------------------------
def parse(text):
    """(tipo, linea) por renglon: escena, accion, personaje, parentetico, dialogo, transicion, vacia, titulo, nota, seccion."""
    lines = text.split("\n")
    out, previous = [], "vacia"
    in_title = bool(lines) and re.match(r"^(Title|Título|Titulo|Author|Autor|Credit|Draft date)\s*:", lines[0], re.I)
    for index, line in enumerate(lines):
        stripped = line.strip()
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if in_title:
            if not stripped:
                in_title = False
                out.append(("vacia", line))
            else:
                out.append(("titulo", line))
            continue
        if not stripped:
            kind = "vacia"
        elif stripped.startswith("[[") or stripped.startswith("/*"):
            kind = "nota"
        elif stripped.startswith("#"):
            kind = "seccion"
        elif stripped.startswith("!"):
            kind = "accion"
        elif previous == "vacia" and HEADING.match(stripped):
            kind = "escena"
        elif previous == "vacia" and TRANSITION.match(stripped) and not following:
            kind = "transicion"
        elif previous in ("personaje", "parentetico", "dialogo") and stripped.startswith("(") and stripped.endswith(")"):
            kind = "parentetico"
        elif previous in ("personaje", "parentetico", "dialogo"):
            kind = "dialogo"
        elif previous == "vacia" and following and (stripped.startswith("@") or (
                CHARACTER.match(stripped) and any(char.isalpha() for char in stripped) and stripped == stripped.upper())):
            kind = "personaje"
        else:
            kind = "accion"
        out.append((kind, line))
        previous = kind
    return out


def to_fountain(structure, title="Neo-Kansai Delta"):
    """Texto Fountain con la estructura: '# Secuencia [[s1]]' y encabezados con '#e1#' para volver a la escena."""
    lines = [f"Title: {title}", f"Draft date: {datetime.date.today().isoformat()}", ""]
    for sequence in structure["secuencias"]:
        lines += [f"# {sequence['titulo']} [[{sequence['id']}]]", ""]
        if sequence.get("sinopsis"):
            lines += [f"= {sequence['sinopsis']}", ""]
        for scene in sequence["escenas"]:
            if scene.get("estado") == "oculta":
                continue
            heading = f"{scene.get('int_ext') or 'INT.'} {scene.get('lugar') or 'LUGAR'} - {scene.get('momento') or 'NOCHE'}"
            lines += [f"{heading.upper()} #{scene['id']}#", ""]
            if scene.get("accion"):
                lines += [scene["accion"].strip(), ""]
            for line in scene.get("dialogos", []):
                if not str(line.get("texto", "")).strip():
                    continue
                lines.append(str(line.get("personaje", "")).strip().upper() or "VOZ")
                if line.get("parentetico"):
                    lines.append("(" + str(line["parentetico"]).strip("() ") + ")")
                lines += [str(line["texto"]).strip(), ""]
    return "\n".join(lines).rstrip() + "\n"


def from_fountain(text, structure):
    """Aplica el texto editado a la estructura: secuencias (# ... [[id]]), escenas (#id#) con su accion y dialogos.
    Lo que el texto no tiene (planos, elenco, lugar_id, tema, notas) se conserva por id; las escenas nuevas se crean."""
    old_sequences = {sequence["id"]: sequence for sequence in structure["secuencias"]}
    old_scenes = {scene["id"]: scene for scene in scenes(structure)}
    hidden = {scene["id"]: scene for scene in old_scenes.values() if scene.get("estado") == "oculta"}
    places = {_plain(place["nombre"]): place_id for place_id, place in universo.load()["locaciones"].items()}
    sequences, current_sequence, current_scene, speaker = [], None, None, None
    for kind, line in parse(text):
        stripped = line.strip()
        if kind == "seccion":
            match = re.search(r"\[\[([^\]]+)\]\]\s*$", stripped)
            title = re.sub(r"\s*\[\[[^\]]+\]\]\s*$", "", stripped).lstrip("#").strip()
            base = dict(old_sequences.get(match.group(1).strip(), {})) if match else {}
            current_sequence = {**base, "id": base.get("id", ""), "titulo": title, "escenas": []}
            current_sequence.setdefault("sinopsis", "")
            sequences.append(current_sequence)
            current_scene = None
        elif kind == "accion" and stripped.startswith("= ") and current_sequence is not None and current_scene is None:
            current_sequence["sinopsis"] = stripped[2:].strip()
        elif kind == "escena":
            if current_sequence is None:
                current_sequence = {"id": "", "titulo": "Secuencia", "sinopsis": "", "escenas": []}
                sequences.append(current_sequence)
            match = re.search(r"#([^#]+)#\s*$", stripped)
            heading = re.sub(r"\s*#[^#]+#\s*$", "", stripped).lstrip(".").strip()
            parts = re.split(r"\s+[-–—]\s+", heading)
            prefix = re.match(r"^(INT\./EXT\.?|INT/EXT\.?|I/E\.?|INT\.?|EXT\.?|EST\.?)\s*", parts[0], re.I)
            place = parts[0][prefix.end():].strip() if prefix else parts[0]
            base = dict(old_scenes.get(match.group(1).strip(), {})) if match else {}
            place_id = base.get("lugar_id") if _plain(base.get("lugar", "")) == _plain(place) else places.get(_plain(place))
            current_scene = {**base, "id": base.get("id", ""), "int_ext": (prefix.group(1) if prefix else "INT.").upper(),
                             "lugar": place.upper(), "lugar_id": place_id, "momento": parts[1].strip() if len(parts) > 1 else "",
                             "accion": "", "dialogos": []}
            current_scene.setdefault("planos", [])
            current_scene.setdefault("elenco", [])
            current_sequence["escenas"].append(current_scene)
            speaker = None
        elif current_scene is None:
            continue
        elif kind == "accion":
            current_scene["accion"] = (current_scene["accion"] + " " + stripped.lstrip("!")).strip()
        elif kind == "personaje":
            speaker = {"personaje": re.sub(r"\s*\(.*\)|\^|@", "", stripped).strip(), "parentetico": "", "texto": ""}
            current_scene["dialogos"].append(speaker)
        elif kind == "parentetico" and speaker:
            speaker["parentetico"] = stripped.strip("()")
        elif kind == "dialogo" and speaker:
            speaker["texto"] = (speaker["texto"] + " " + stripped).strip()
    for scene in hidden.values():   # las ocultas no estan en el texto: vuelven a su secuencia
        owner = next((sequence for sequence in sequences
                      if any(old_scene["id"] == scene["id"] for old_scene in
                             old_sequences.get(sequence.get("id"), {}).get("escenas", []))), sequences[-1] if sequences else None)
        if owner is not None and all(item["id"] != scene["id"] for item in owner["escenas"]):
            owner["escenas"].append(scene)
    return clean({"premisa": structure.get("premisa", ""), "secuencias": sequences})


def to_fdx(text):
    """Final Draft XML (.fdx) con los tipos de parrafo estandar (de Doble Fondo)."""
    kinds = {"escena": "Scene Heading", "accion": "Action", "personaje": "Character", "parentetico": "Parenthetical",
             "dialogo": "Dialogue", "transicion": "Transition"}
    paragraphs, title = [], ""
    for kind, line in parse(text):
        stripped = line.strip()
        if kind == "titulo":
            if re.match(r"^(Title|Título)\s*:", stripped, re.I):
                title = stripped.split(":", 1)[1].strip()
            continue
        if kind in ("vacia", "nota", "seccion"):
            continue
        number = ""
        if kind == "escena":
            match = re.search(r"#([^#]+)#\s*$", stripped)
            number = f' Number="{escape(match.group(1))}"' if match else ""
            stripped = re.sub(r"\s*#[^#]+#\s*$", "", stripped).lstrip(".")
        if kind == "transicion":
            stripped = stripped.lstrip("> ").strip()
        if kind == "accion":
            stripped = stripped.lstrip("!")
        if kind == "personaje":
            stripped = stripped.lstrip("@").rstrip("^ ").strip()
        paragraphs.append(f'    <Paragraph Type="{kinds[kind]}"{number}>\n      <Text>{escape(stripped)}</Text>\n'
                          "    </Paragraph>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<FinalDraft DocumentType="Script" Template="No" '
            'Version="5">\n  <Content>\n' + "\n".join(paragraphs) + "\n  </Content>\n  <TitlePage>\n    <Content>\n"
            f'      <Paragraph Alignment="Center" Type="Text">\n        <Text>{escape(title)}</Text>\n      </Paragraph>\n'
            "    </Content>\n  </TitlePage>\n</FinalDraft>\n")


# --- generacion encadenada (Ollama, por la cola) ---------------------------------------------------------
STEPS = {
    "premisa": ("guion_premisa.md", {"type": "object", "properties": {
        key: {"type": "string"} for key in ("titulo", "logline", "tema", "genero", "tono", "formato", "concepto")},
        "required": ["titulo", "logline", "tema", "genero", "tono"]}),
    "secuencias": ("guion_secuencias.md", {"type": "object", "properties": {"secuencias": {"type": "array", "items": {
        "type": "object", "properties": {"titulo": {"type": "string"}, "sinopsis": {"type": "string"}},
        "required": ["titulo", "sinopsis"]}}}, "required": ["secuencias"]}),
    "escenas": ("guion_escenas.md", {"type": "object", "properties": {"escenas": {"type": "array", "items": {
        "type": "object", "properties": {"int_ext": {"type": "string"}, "lugar": {"type": "string"},
                                         "momento": {"type": "string"}, "accion": {"type": "string"},
                                         "personajes": {"type": "array", "items": {"type": "string"}},
                                         "dialogos": {"type": "array", "items": {"type": "object", "properties": {
                                             "personaje": {"type": "string"}, "parentetico": {"type": "string"},
                                             "texto": {"type": "string"}}, "required": ["personaje", "texto"]}}},
        "required": ["lugar", "momento", "accion"]}}}, "required": ["escenas"]}),
    "planos": ("guion_planos.md", {"type": "object", "properties": {"planos": {"type": "array", "items": {
        "type": "object", "properties": {"tipo": {"type": "string"}, "que_se_ve": {"type": "string"},
                                         "accion": {"type": "string"}, "duracion": {"type": "number"},
                                         "movimiento": {"type": "string"}},
        "required": ["tipo", "que_se_ve", "accion"]}}}, "required": ["planos"]}),
}


def proposals_path(folder):
    return Path(folder) / "propuestas_guion.json"


def proposals(folder):
    return ref.read_json(proposals_path(folder), {}) or {}


def _context(project, structure, kind, target):
    """Lo que el agente recibe: idea, premisa, intencion, universo y la parte del guion que toca."""
    data = universo.load()
    people = {pid: f"{person['nombre']} ({person.get('edad', '?')}): {person.get('arquetipo', '')}. "
                   f"Quiere: {person.get('deseo', '')}" for pid, person in data["personajes"].items()}
    places = {lid: place["nombre"] for lid, place in data["locaciones"].items()}
    premise = {**(project.get("premisa") or {})}
    context = {"idea": project.get("idea", ""), "premisa": premise, "intencion": project.get("intencion", {}),
               "personajes": people, "lugares": places, "reglas": data.get("reglas", "")}
    if kind == "escenas":
        sequence = next(item for item in structure["secuencias"] if item["id"] == target)
        context["secuencia"] = {"titulo": sequence["titulo"], "sinopsis": sequence.get("sinopsis", "")}
        context["secuencias"] = [{"titulo": item["titulo"], "sinopsis": item.get("sinopsis", "")}
                                 for item in structure["secuencias"]]
    if kind == "planos":
        _, scene = find_scene(structure, target)
        context["escena"] = {key: scene.get(key) for key in ("int_ext", "lugar", "momento", "accion", "dialogos", "elenco")}
    if kind == "secuencias":
        context["secuencias_actuales"] = [item["titulo"] for item in structure["secuencias"]]
    return context


def generate(folder, project, kind, target, model, ask=None, books=""):
    """Pide a Ollama el paso `kind` y lo deja como propuesta. Devuelve la propuesta o None (si fallo, nada se inventa)."""
    method_file, schema = STEPS[kind]
    structure = load(folder)
    method = (AGENTS / method_file).read_text(encoding="utf-8")
    context = _context(project, structure, kind, target)
    prompt = (f"{method}\n\n{('REFERENCIA DE TONO (libros, no copiar): ' + books) if books else ''}\n"
              f"CONTEXTO: {json.dumps(context, ensure_ascii=False)}\nDevolve solo el JSON pedido.")
    answer = (ask or equipo.ask)(prompt, schema, model, 17)
    text = json.dumps(answer, ensure_ascii=False)
    if re.search(equipo.MINORS, text, re.I):
        raise ValueError("la propuesta puede mostrar menores: no se guarda")
    items = proposals(folder)
    key = f"{kind}:{target or ''}"
    items[key] = {"tipo": kind, "objetivo": target, "propuesta": answer,
                  "fecha": datetime.datetime.now().isoformat(timespec="seconds")}
    ref.write_json(proposals_path(folder), items)
    return items[key]


def accept(folder, key, save_project=None):
    """Aplica una propuesta: premisa al proyecto; secuencias, escenas y planos al guion (se agregan, no se pisa)."""
    items = proposals(folder)
    if key not in items:
        raise ValueError("no hay esa propuesta")
    item = items.pop(key)
    answer = item["propuesta"]
    if item["tipo"] == "premisa":
        if save_project:
            save_project(lambda data: data.setdefault("premisa", {}).update(
                {k: str(v)[:4000] for k, v in answer.items() if isinstance(v, str)}))
    else:
        structure = load(folder)
        places = {_plain(place["nombre"]): lid for lid, place in universo.load()["locaciones"].items()}
        people = {_plain(person["nombre"]): pid for pid, person in universo.load()["personajes"].items()}
        if item["tipo"] == "secuencias":
            for sequence in answer.get("secuencias", []):
                structure["secuencias"].append({"id": "", "titulo": sequence["titulo"],
                                                "sinopsis": sequence.get("sinopsis", ""), "escenas": []})
        elif item["tipo"] == "escenas":
            sequence = next(entry for entry in structure["secuencias"] if entry["id"] == item["objetivo"])
            for scene in answer.get("escenas", []):
                sequence["escenas"].append({
                    "id": "", "int_ext": (scene.get("int_ext") or "INT.").upper(), "lugar": scene["lugar"].upper(),
                    "lugar_id": places.get(_plain(scene["lugar"])), "momento": scene.get("momento", "NOCHE").upper(),
                    "accion": literal_es(scene["accion"]) or scene["accion"], "dialogos": scene.get("dialogos", []),
                    "elenco": [people[_plain(name)] for name in scene.get("personajes", []) if _plain(name) in people],
                    "estado": "revision", "planos": []})
        elif item["tipo"] == "planos":
            _, scene = find_scene(structure, item["objetivo"])
            for shot in answer.get("planos", []):
                scene["planos"].append({"id": "", "tipo": shot.get("tipo", "PM"), "que_se_ve": literal_es(shot["que_se_ve"]),
                                        "accion": shot["accion"], "duracion": shot.get("duracion"),
                                        "movimiento": shot.get("movimiento", ""), "estado": "pendiente"})
        save(folder, structure, f"propuesta_{item['tipo']}")
    ref.write_json(proposals_path(folder), items)
    return item


def discard(folder, key):
    items = proposals(folder)
    items.pop(key, None)
    ref.write_json(proposals_path(folder), items)
