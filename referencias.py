"""Almacen de imagenes de referencia con versiones, aprobaciones y cascada (plan StoryForge + referencias).

Nodos (id = "<tipo>/<nombre>"):
  retrato/<personaje>              Z-Image, desde el aspecto del universo
  vista/<personaje>__<vista>       Kontext desde el retrato: giro de frente, 3/4, perfil, 3/4 espalda, espalda   (a pedido)
  expresion/<personaje>__<gesto>   Kontext desde el retrato: estudios de cara                                     (a pedido)
  cinematico/<personaje>           Kontext desde el vestuario: retrato de cine en luz de escena                   (a pedido)
  tela/<personaje>__<n>            Kontext desde el vestuario: primer plano de un material                        (a pedido)
  hoja/<personaje>                 ffmpeg: la ficha completa armada como una hoja de produccion                   (a pedido)
  vestuario/<personaje>            Kontext desde el retrato, con la ropa del universo (referencia de persona en tomas)
  objeto/<personaje>__<n>          Z-Image, objeto de firma
  lugar/<lugar>                    Z-Image, desde la locacion del universo
  toma/<semilla>                   Kontext (vestuario + lugar [+ objeto]) -> estilo Z-Image -> acabado

Cada nodo vive en universo/referencias/<tipo>/<nombre>/ (las tomas en <tema>/toma/) con:
  ficha.json     lo escribe el que genera: receta y versiones (cada version con sus candidatos y su hash)
  revision.json  lo escribe StoryForge: {hash_imagen: {estado, nota, accion, fecha}, "elegido": {...}}
Una aprobacion queda atada al hash de la imagen: una imagen nueva nunca hereda la aprobacion vieja.

Los nodos "a pedido" (la ficha completa del personaje) no se generan con lo pendiente: esperan a que se pida la
ficha de ese personaje en StoryForge (`pedir_ficha`), asi no se gastan ~15 imagenes por personaje sin querer.

Estados: a pedido, pendiente (sin version), bloqueado (un padre sin aprobar), desactualizado (cambio su receta: un texto del
universo, una imagen aprobada de un padre o los ajustes), rechazado, generado (sin revisar), aprobado.
`cascada(id)` lista todo lo que depende de un nodo; `planificar()` arma los trabajos en orden.

  python referencias.py estado            resumen por tipo
  python referencias.py cascada retrato/kaito_veyra
  python referencias.py migrar            congela el elenco de los temas e importa los fondos existentes
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import decoupage_sf
import universo

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "universo" / "referencias"
SONGS = ROOT / "Agente Frequency"
SETTINGS = STORE / "ajustes.json"
VIEWS = ("frente", "tres_cuartos", "perfil", "tres_cuartos_espalda", "espalda")
EXPRESSIONS = ("neutral", "determinada", "sonrisa", "enojo", "preocupacion", "sorpresa")
FABRICS = 3
ON_REQUEST = ("vista", "expresion", "cinematico", "tela", "hoja", "clip")

# subir el numero de un tipo invalida a proposito todas sus imagenes (cambio el workflow o el prompt base)
WORKFLOW_VERSION = {"retrato": 1, "vista": 1, "expresion": 1, "cinematico": 1, "tela": 1, "hoja": 2, "vestuario": 1,
                    "objeto": 2, "lugar": 2, "toma": 1, "plano": 1, "clip": 1}   # 2: estilo sin personaje (2026-11-08)
ORDER = ("retrato", "lugar", "objeto", "vista", "expresion", "vestuario", "cinematico", "tela", "hoja", "toma",
         "plano", "clip")   # orden para generar
DEFAULT_SETTINGS = {"modo": "stitch", "lora": "glif90", "persona_ref": "vestuario", "denoise": .4,
                    "hires_denoise": .3, "_nota": "valores provisorios hasta elegir en el piloto"}


# --- utilidades --------------------------------------------------------------------------------
def _plain(value):
    if isinstance(value, str):
        value = value.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def sha_json(value):
    """Resumen estable de un texto o estructura (espacios y comillas tipograficas no cuentan como cambio)."""
    return hashlib.sha1(json.dumps(_plain(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sha_file(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path, value):
    """Escritura atomica: StoryForge y la cola pueden leer mientras se escribe."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def settings():
    return {**DEFAULT_SETTINGS, **(read_json(SETTINGS, {}) or {})}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


# --- elenco congelado de los temas ----------------------------------------------------------------
def song_folder(seed):
    found = [path for path in SONGS.glob(f"* {seed}") if (path / f"{path.name}.json").is_file()]
    return found[0] if found else None


def song_seeds():
    seeds = []
    for path in SONGS.glob("* 20*"):
        try:
            seed = int(path.name.rsplit(" ", 1)[1])
        except ValueError:
            continue
        if (path / f"{path.name}.json").is_file():
            seeds.append(seed)
    return sorted(seeds)


# --- nodos y dependencias ---------------------------------------------------------------------------
def nodos(data=None):
    """{id: {tipo, nombre, fuente, padres}} de todo el universo y de los temas con toma."""
    data = data or universo.load()
    result = {}
    for pid, person in data["personajes"].items():
        result[f"retrato/{pid}"] = {"tipo": "retrato", "personaje": pid, "padres": []}
        portrait, wardrobe = f"retrato/{pid}", f"vestuario/{pid}"
        result[portrait] = {"tipo": "retrato", "personaje": pid, "padres": []}
        result[wardrobe] = {"tipo": "vestuario", "personaje": pid, "padres": [portrait]}
        sheet_parts = [portrait, wardrobe]
        for view in VIEWS:
            result[f"vista/{pid}__{view}"] = {"tipo": "vista", "personaje": pid, "vista": view, "padres": [portrait]}
            sheet_parts.append(f"vista/{pid}__{view}")
        for face in EXPRESSIONS:
            result[f"expresion/{pid}__{face}"] = {"tipo": "expresion", "personaje": pid, "expresion": face,
                                                  "padres": [portrait]}
            sheet_parts.append(f"expresion/{pid}__{face}")
        result[f"cinematico/{pid}"] = {"tipo": "cinematico", "personaje": pid, "padres": [wardrobe]}
        sheet_parts.append(f"cinematico/{pid}")
        for index in range(FABRICS):
            result[f"tela/{pid}__{index}"] = {"tipo": "tela", "personaje": pid, "indice": index, "padres": [wardrobe]}
            sheet_parts.append(f"tela/{pid}__{index}")
        for index, _ in enumerate(person.get("objetos", [])):
            result[f"objeto/{pid}__{index}"] = {"tipo": "objeto", "personaje": pid, "indice": index, "padres": []}
            sheet_parts.append(f"objeto/{pid}__{index}")
        result[f"hoja/{pid}"] = {"tipo": "hoja", "personaje": pid, "padres": sheet_parts}
    for lid in data["locaciones"]:
        result[f"lugar/{lid}"] = {"tipo": "lugar", "lugar": lid, "padres": []}
    frozen = universo.frozen()
    for seed in song_seeds():
        cast = frozen.get(str(seed))
        if not cast:
            continue
        parents = [f"vestuario/{cast['id']}", f"lugar/{cast['lugar_id']}"]
        if cast.get("objeto") is not None:
            parents.append(f"objeto/{cast['id']}__{cast['objeto']}")
        result[f"toma/{seed}"] = {"tipo": "toma", "semilla": seed, "personaje": cast["id"], "padres": parents}
        result[f"clip/t{seed}__p1"] = {"tipo": "clip", "escena": f"t{seed}", "plano": "p1", "semilla": seed,
                                       "padres": [f"toma/{seed}"]}
    _script_nodes(result, data)
    return result


def script_scenes():
    """Escenas del guion del proyecto (proyectos nuevos: guion.json al lado del almacen). [] en Ejemplo 1."""
    saved = read_json(STORE.parent / "guion.json", {}) or {}
    return [scene for sequence in saved.get("secuencias") or [] for scene in sequence.get("escenas", [])
            if scene.get("estado") != "oculta" and not scene.get("tema")]


def _script_nodes(result, data):
    """Planos de las escenas del guion: imagen de inicio y de fin (con su elenco y su lugar) y el clip a pedido."""
    for scene in script_scenes():
        cast = [pid for pid in scene.get("elenco", []) if pid in data["personajes"]]
        parents = [f"vestuario/{pid}" for pid in cast[:1]]
        if scene.get("lugar_id") in data["locaciones"]:
            parents.append(f"lugar/{scene['lugar_id']}")
        for index, shot in enumerate(scene.get("planos", [])):
            base = f"{scene['id']}__{shot['id']}"
            for moment in ("ini", "fin"):
                result[f"plano/{base}_{moment}"] = {"tipo": "plano", "escena": scene["id"], "plano": shot["id"],
                                                    "indice": index, "momento": moment, "padres": list(parents)}
            result[f"clip/{base}"] = {"tipo": "clip", "escena": scene["id"], "plano": shot["id"], "indice": index,
                                      "padres": [f"plano/{base}_ini", f"plano/{base}_fin"]}


def shot_text(node):
    """Lo que define la imagen de un plano o un clip: el texto de la escena y del plano, la camara (inicio o fin),
    la puesta, el movimiento, el texto en ingles que preparo Ollama y el cuadro de previz."""
    folder = plan_folder(node["escena"])
    plan = decoupage_sf.load(folder)
    index = node.get("indice", 0)
    shot = (plan or {}).get("planos", [])[index] if plan and index < len(plan.get("planos", [])) else {}
    scene = next((item for item in script_scenes() if item["id"] == node["escena"]), {})
    value = {"accion": scene.get("accion"), "plano": next((item for item in scene.get("planos", [])
                                                           if item["id"] == node["plano"]), {}),
             "puesta": decoupage_sf.staging(plan, index) if plan else "",
             "movimiento": decoupage_sf.movimiento(plan, shot) if shot else "",
             "ingles": read_json(STORE / "plano" / f"{node['escena']}__{node['plano']}_prompt.json")}
    if node["tipo"] == "plano" and shot:
        t = 0.0 if node["momento"] == "ini" else 1.0
        value["camara"] = {key: (round(val, 2) if isinstance(val, float) else val)
                           for key, val in decoupage_sf.camera(plan, shot, t).items()}
        sketch = folder / "toma" / "previz" / f"{node['plano']}_{node['momento']}.png"
        value["previz"] = sha_file(sketch) if sketch.is_file() else None
    return value


def plan_folder(scene_id):
    """Carpeta de la planta de una escena: el tema si es una escena-tema; si no, direccion/<escena> del proyecto."""
    if scene_id.startswith("t") and scene_id[1:].isdigit() and song_folder(int(scene_id[1:])):
        return song_folder(int(scene_id[1:]))
    return STORE.parent / "direccion" / scene_id


def clip_pedido(node_id):
    return node_id in (read_json(STORE / "clips_pedidos.json", []) or [])


def pedir_clip(node_id):
    requested = read_json(STORE / "clips_pedidos.json", []) or []
    if node_id not in requested:
        write_json(STORE / "clips_pedidos.json", requested + [node_id])


def requested(node):
    return clip_pedido(node["_id"]) if node["tipo"] == "clip" else ficha_pedida(node["personaje"])


def hijos(node_id, graph=None):
    graph = graph or nodos()
    return [other for other, node in graph.items() if node_id in node["padres"]]


def cascada(node_id, graph=None):
    """Todo lo que depende de un nodo, en orden de generacion (lo que se rehace si se rechaza)."""
    graph = graph or nodos()
    seen, pending = [], [node_id]
    while pending:
        current = pending.pop(0)
        for child in hijos(current, graph):
            if child not in seen:
                seen.append(child)
                pending.append(child)
    return sorted(seen, key=lambda item: (ORDER.index(item.split("/")[0]), item))


def node_dir(node_id):
    kind, name = node_id.split("/", 1)
    if kind == "toma":
        folder = song_folder(int(name))
        if not folder:
            raise ValueError(f"No hay carpeta para el tema {name}")
        return folder / "toma"
    return STORE / kind / name


def source_text(node_id, node, data):
    """Los textos del universo que definen la imagen de un nodo (si cambian, la imagen queda desactualizada)."""
    kind = node["tipo"]
    if kind in ("plano", "clip"):
        return shot_text(node)
    if "personaje" in node and kind != "toma":
        person = data["personajes"][node["personaje"]]
        if kind == "retrato":
            return {key: person.get(key) for key in ("genero", "edad", "aspecto", "implantes")}
        if kind == "vista":
            return {"vista": node["vista"]}
        if kind == "expresion":
            return {"expresion": node["expresion"]}
        if kind == "tela":
            return {"tela": fabric_text(person, node["indice"])}
        if kind == "hoja":
            return {key: person.get(key) for key in ("nombre", "alias", "arquetipo", "edad", "aspecto")}
        if kind == "vestuario":
            return {"vestuario": person.get("vestuario")}
        if kind == "objeto":
            return {"objeto": person["objetos"][node["indice"]]}
        return {}
    if kind == "lugar":
        place = data["locaciones"][node["lugar"]]
        return {key: place.get(key) for key in ("prompt", "luz", "atmosfera", "utileria")}
    if kind == "toma":
        folder = song_folder(node["semilla"])
        team = {path.stem: read_json(path) for path in sorted((folder / "equipo").glob("*.json"))
                if path.stem in ("escritor", "director", "casting", "vestuario", "arte", "fotografo")}
        sheet = read_json(folder / "ficha.json", {}) or {}
        return {"equipo": sha_json(team), "prompt": sha_json(sheet.get("prompt_imagen", "")),
                "paleta": sheet.get("paleta"), "asignacion": universo.frozen().get(str(node["semilla"])),
                "puesta": decoupage_sf.staging(decoupage_sf.load(folder))}
    return {}


def fabric_text(person, index):
    """La prenda n del vestuario (las prendas van separadas por coma o punto y coma en el universo)."""
    garments = [part.strip() for part in re.split(r"[;,]", person.get("vestuario", "")) if len(part.strip()) > 3]
    return garments[index] if index < len(garments) else ""


# --- ficha a pedido -------------------------------------------------------------------------------
def ficha_pedida(person_id):
    return bool((read_json(STORE / "ficha_pedida" / f"{person_id}.json", {}) or {}).get("pedido"))


def pedir_ficha(person_id, graph=None):
    """Pide la ficha completa de un personaje: sus nodos a pedido pasan a pendientes. Devuelve sus ids."""
    graph = graph or nodos()
    if f"retrato/{person_id}" not in graph:
        raise ValueError(f"No existe el personaje {person_id}")
    write_json(STORE / "ficha_pedida" / f"{person_id}.json", {"pedido": True,
                                                "fecha": datetime.datetime.now().isoformat(timespec="seconds")})
    return [node_id for node_id, node in graph.items()
            if node["tipo"] in ON_REQUEST and node.get("personaje") == person_id]


def recipe(node_id, graph=None, data=None):
    """Receta actual: textos de origen + imagen aprobada de cada padre + ajustes + version del workflow."""
    graph = graph or nodos(data)
    data = data or universo.load()
    node = graph[node_id]
    parents = {parent: approved_hash(parent) for parent in node["padres"]}
    tuning = settings() if node["tipo"] == "toma" else {}
    value = {"tipo": node["tipo"], "workflow": WORKFLOW_VERSION[node["tipo"]], "texto": source_text(node_id, node, data),
             "padres": parents, "ajustes": {key: item for key, item in tuning.items() if not key.startswith("_")}}
    return value, sha_json(value)


# --- versiones y revision ------------------------------------------------------------------------
def ficha(node_id):
    return read_json(node_dir(node_id) / "ficha.json", {"id": node_id, "versiones": []})


def revision(node_id):
    return read_json(node_dir(node_id) / "revision.json", {"imagenes": {}, "elegido": None})


def record_version(node_id, files, recipe_value, recipe_hash, model, extra=None):
    """Registra una version nueva (la escribe el que genera). `files`: candidatos, el primero es el sugerido."""
    folder = node_dir(node_id)
    sheet = ficha(node_id)
    number = len(sheet["versiones"]) + 1
    candidates = []
    for index, path in enumerate(files, 1):
        path = Path(path)
        target = folder / f"v{number:03d}_{index}{path.suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        candidates.append({"archivo": target.name, "hash": sha_file(target)})
    sheet["versiones"].append({"v": number, "candidatos": candidates, "receta": recipe_value, "receta_hash": recipe_hash,
                               "modelo": model, "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
                               **(extra or {})})
    write_json(folder / "ficha.json", sheet)
    review = revision(node_id)
    if review.get("elegido"):  # la version nueva pasa a ser la actual y espera revision (lo que depende, tambien)
        review["elegido"] = None
        write_json(folder / "revision.json", review)
    return sheet["versiones"][-1]


def chosen_image(node_id):
    """(version, candidato) elegidos: el que eligio el usuario o, si no eligio, el primero de la ultima version."""
    sheet, review = ficha(node_id), revision(node_id)
    if not sheet["versiones"]:
        return None, None
    pick = review.get("elegido")
    if pick:
        version = next((item for item in sheet["versiones"] if item["v"] == pick["v"]), None)
        if version and 0 <= pick["candidato"] < len(version["candidatos"]):
            return version, version["candidatos"][pick["candidato"]]
    version = sheet["versiones"][-1]
    return version, version["candidatos"][0]


def approved_hash(node_id):
    """Hash de la imagen aprobada de un nodo, o None."""
    _, candidate = chosen_image(node_id)
    if not candidate:
        return None
    verdict = revision(node_id)["imagenes"].get(candidate["hash"], {})
    return candidate["hash"] if verdict.get("estado") == "aprobado" else None


def review_image(node_id, image_hash, verdict, note="", action=""):
    """Aprueba o rechaza una imagen (lo usa StoryForge). Al aprobar, esa imagen pasa a ser la elegida."""
    if verdict not in ("aprobado", "rechazado"):
        raise ValueError("estado tiene que ser aprobado o rechazado")
    sheet, review = ficha(node_id), revision(node_id)
    location = next(((version["v"], index) for version in sheet["versiones"]
                     for index, candidate in enumerate(version["candidatos"]) if candidate["hash"] == image_hash), None)
    if not location:
        raise ValueError(f"{node_id} no tiene una imagen con ese hash")
    review["imagenes"][image_hash] = {"estado": verdict, "nota": note, "accion": action,
                                      "fecha": datetime.datetime.now().isoformat(timespec="seconds")}
    if verdict == "aprobado":
        review["elegido"] = {"v": location[0], "candidato": location[1]}
    write_json(node_dir(node_id) / "revision.json", review)
    if verdict == "aprobado" and node_id.startswith("toma/") and action != "legado":
        publish_shot(node_id)
    return review


def publish_shot(node_id):
    """La toma aprobada pasa a ser el fondo del tema; el anterior queda como fondo_anterior.png."""
    version, candidate = chosen_image(node_id)
    if not candidate or version.get("legado"):
        return None
    song = node_dir(node_id).parent
    background = song / "fondo.png"
    if background.is_file():
        shutil.copy2(background, song / "fondo_anterior.png")
    shutil.copy2(node_dir(node_id) / candidate["archivo"], background)
    return background


def choose(node_id, version, candidate):
    review = revision(node_id)
    review["elegido"] = {"v": version, "candidato": candidate}
    write_json(node_dir(node_id) / "revision.json", review)


def estado(node_id, graph=None, data=None):
    """Estado del nodo y el motivo."""
    graph = graph or nodos(data)
    node = graph[node_id]
    blocked = [parent for parent in node["padres"] if not approved_hash(parent)]
    version, candidate = chosen_image(node_id)
    if not version and node["tipo"] in ON_REQUEST and not requested({**node, "_id": node_id}):
        return "a pedido", ("se genera al pedirlo (clip de Wan)" if node["tipo"] == "clip"
                            else "se genera al pedir la ficha completa del personaje")
    if not version:
        return ("bloqueado", f"falta aprobar {', '.join(blocked)}") if blocked else ("pendiente", "sin imagen")
    if version.get("legado"):
        verdict = revision(node_id)["imagenes"].get(candidate["hash"], {}).get("estado")
        return (verdict or "aprobado", "fondo anterior al sistema de referencias")
    if blocked:
        return "bloqueado", f"falta aprobar {', '.join(blocked)}"
    _, current = recipe(node_id, graph, data)
    latest = ficha(node_id)["versiones"][-1]
    if latest["receta_hash"] != current:
        return "desactualizado", why_stale(latest["receta"], recipe(node_id, graph, data)[0])
    verdict = revision(node_id)["imagenes"].get(candidate["hash"], {}).get("estado")
    if verdict == "rechazado":
        return "rechazado", revision(node_id)["imagenes"][candidate["hash"]].get("nota", "")
    return (verdict or "generado"), ""


def why_stale(old, new):
    reasons = []
    if old.get("texto") != new.get("texto"):
        reasons.append("cambio el texto del universo o del equipo")
    for parent, image in new.get("padres", {}).items():
        if old.get("padres", {}).get(parent) != image:
            reasons.append(f"{parent} tiene otra imagen aprobada")
    if old.get("ajustes") != new.get("ajustes"):
        reasons.append("cambiaron los ajustes")
    if old.get("workflow") != new.get("workflow"):
        reasons.append("cambio el workflow")
    return "; ".join(reasons) or "cambio la receta"


def planificar(alcance="pendientes", graph=None):
    """Trabajos a generar, en orden: pendientes, desactualizados y rechazados (con su nota) que no esten bloqueados.

    alcance: "pendientes" (todo lo que falta o esta mal) o una lista de ids (esos y su cascada).
    """
    graph = graph or nodos()
    if isinstance(alcance, (list, tuple)):
        wanted = []
        for node_id in alcance:
            wanted += [node_id] + cascada(node_id, graph)
    else:
        wanted = list(graph)
    jobs = []
    for node_id in sorted(set(wanted), key=lambda item: (ORDER.index(item.split("/")[0]), item)):
        status, reason = estado(node_id, graph)
        if status in ("pendiente", "desactualizado", "rechazado"):
            jobs.append({"nodo": node_id, "motivo": status, "detalle": reason})
        elif status == "bloqueado" and node_id in wanted:
            jobs.append({"nodo": node_id, "motivo": "esperando", "detalle": reason})  # se hace cuando aprueben al padre
    return jobs


# --- migracion de los temas existentes ------------------------------------------------------------
def migrar():
    """Congela el elenco de cada tema con plan y trae los fondos ya hechos como version 'legado' aprobada."""
    backup = universo.FILE.with_name(f"universo.backup-{datetime.date.today().isoformat()}.json")
    if not backup.exists():
        shutil.copy2(universo.FILE, backup)
    report = []
    for seed in song_seeds():
        folder = song_folder(seed)
        if not (folder / "equipo").is_dir():   # temas de antes del universo (2038-2047) o sin equipo todavia
            continue
        cast = universo.freeze(seed)
        node_id = f"toma/{seed}"
        background = folder / "fondo.png"
        if background.is_file() and not ficha(node_id)["versiones"]:
            version = record_version(node_id, [background], {"legado": True}, "legado", "anterior", {"legado": True})
            review_image(node_id, version["candidatos"][0]["hash"], "aprobado", "fondo anterior al sistema", "legado")
        has_sheet = (folder / "ficha.json").is_file()
        report.append(f"{seed}: {cast['id']} en {cast['lugar_id']}"
                      f"{' (fondo legado)' if background.is_file() else ''}{'' if has_sheet else ' (sin ficha)'}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", choices=("estado", "cascada", "migrar", "plan"))
    parser.add_argument("nodo", nargs="?")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.accion == "migrar":
        print("\n".join(migrar()))
        return
    graph = nodos()
    if args.accion == "cascada":
        print("\n".join(cascada(args.nodo, graph)))
        return
    if args.accion == "plan":
        for job in planificar("pendientes" if not args.nodo else [args.nodo], graph):
            print(f"{job['nodo']}: {job['motivo']} {job['detalle']}")
        return
    counts = {}
    for node_id in graph:
        status, _ = estado(node_id, graph)
        counts.setdefault(node_id.split("/")[0], {}).setdefault(status, 0)
        counts[node_id.split("/")[0]][status] += 1
    for kind in ORDER:
        print(kind, counts.get(kind, {}))


if __name__ == "__main__":
    main()
