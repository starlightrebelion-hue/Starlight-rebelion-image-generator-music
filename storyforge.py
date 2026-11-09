"""StoryForge: estudio de preproduccion conectado (guion, personajes, arte, storyboard, guion tecnico y edicion).

Servidor local (solo 127.0.0.1) con la pagina storyforge/ (index.html + css/ + js/) y una API JSON sobre
referencias.py, la cola, el universo y los temas. Multiproyecto (storyforge/proyectos.json); "Ejemplo 1" es este
canal: universo Neo-Kansai Delta y los temas de Agente Frequency (cada tema es una escena con una toma).

  python storyforge.py [--puerto 8765] [--sin-navegador]

Nada de lo que manda la pagina llega a una consola: las ids se validan contra el grafo y el universo, y la cola se
lanza con una lista fija de argumentos. No se renderiza video desde aca.
"""
import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import cola_referencias as cola
import proyecto_sf as sf
import decoupage_sf as dc
import guion_sf
import libros_sf
import revisores_sf
import referencias as ref
import fondo_comfy
import postproceso
import universo

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "storyforge"
PAGE = WEB / "index.html"
PROJECTS = WEB / "proyectos.json"
MAX_BODY = 64 * 1024
MAX_UPLOAD = 16 * 1024 * 1024
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4"}
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8"}
NAMES = {"retrato": "Retratos", "vista": "Giro", "expresion": "Expresiones", "cinematico": "Cine", "tela": "Telas",
         "hoja": "Hojas", "vestuario": "Vestuario", "objeto": "Objetos", "lugar": "Lugares", "toma": "Tomas"}
ROLES = ("escritor", "director", "casting", "vestuario", "arte", "fotografo", "continuidad", "productor")
PERSON_FIELDS = ("alias", "arquetipo", "aspecto", "vestuario", "historia", "deseo", "miedo", "contradiccion", "secreto")
PLACE_FIELDS = ("nombre", "prompt", "luz", "atmosfera", "utileria")
UPLOAD_KINDS = ("retrato", "vestuario", "lugar", "objeto", "vista", "expresion", "cinematico", "tela", "toma")
SIGNATURES = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg"}


AGENTS = ROOT / "agentes"
PIXELSET_AGENTS = Path(r"C:\Pixel-set\agentes")
AGENT_BACKUPS = AGENTS / "_respaldos"
# que etapa usa cada agente (solapa Agentes)
AGENT_STAGES = {"escritor": "Guion / Storyboard (equipo de imagen)", "director": "Direccion (equipo de imagen)",
                "casting": "Casting", "vestuario": "Arte · vestuario", "arte": "Arte · lugares",
                "fotografo": "Direccion · camara y luz", "continuidad": "Storyboard · no repetir tomas",
                "productor": "Revision del prompt", "postproduccion": "Post de la imagen",
                "referencias": "Rechazos con nota (corrige descripciones)", "guionista_storyforge": "Guion · estructura",
                "guion_premisa": "Idea -> Premisa", "guion_secuencias": "Premisa -> Secuencias",
                "sociologia": "Revision (revisor)", "estructuras_narrativas": "Revision (revisor)",
                "artes_combinadas": "Revision (revisor)", "estetica": "Revision (revisor)",
                "coordinador": "Revision (hoja de ruta)", "formato_informe": "Revision (formato comun)",
                "declaracion_intencion": "Premisa (declaracion de intencion)",
                "guion_escenas": "Secuencia -> Escenas", "guion_planos": "Escena -> Planos"}
MUSIC_FIELDS = ("titulo", "idea", "tonica", "escala", "bpm", "duracion_seg", "compases", "estructura", "ensamble", "lead",
                "ambiente", "densidad", "arpegio", "bajo", "bateria", "progresion_verso", "progresion_coro", "contorno",
                "melodia", "acordes", "efecto", "reverb", "delay", "imagen")


def project_dir():
    return Path(sf.STATE["carpeta"] or WEB / "proyectos" / "ejemplo_1")


def allowed_roots():
    return [ref.STORE.resolve(), ref.SONGS.resolve()]


def image_url(path):
    """URL de una imagen con la fecha del archivo: si el archivo cambia (fondo.png nuevo) la URL cambia y el navegador
    no muestra la copia vieja que tenia guardada. La ruta va completa (los proyectos pueden estar en otra carpeta)."""
    path = Path(path).resolve()
    stamp = path.stat().st_mtime_ns if path.is_file() else 0
    return "/img?p=" + quote(str(path).replace("\\", "/")) + f"&t={stamp}"


def chosen_url(node_id):
    """URL de la imagen elegida de un nodo, o None."""
    try:
        _, candidate = ref.chosen_image(node_id)
    except (ValueError, KeyError):
        return None
    if not candidate:
        return None
    path = ref.node_dir(node_id) / candidate["archivo"]
    return image_url(path) if path.is_file() else None


# --- vistas de nodos ------------------------------------------------------------------------------
def describe(node_id, node, data):
    """Nombre y datos de contexto de un nodo para la tarjeta."""
    kind = node["tipo"]
    info = {}
    if "personaje" in node and kind != "toma":
        person = data["personajes"][node["personaje"]]
        info = {"personaje": person["nombre"], "alias": person.get("alias"), "arquetipo": person.get("arquetipo"),
                "edad": person.get("edad")}
        if kind == "retrato":
            info.update(aspecto=person.get("aspecto"))
        if kind in ("vestuario", "cinematico"):
            info.update(vestuario=person.get("vestuario"))
        if kind == "objeto":
            info.update(objeto=person["objetos"][node["indice"]])
        if kind == "tela":
            info.update(tela=ref.fabric_text(person, node["indice"]))
    if kind == "lugar":
        place = data["locaciones"][node["lugar"]]
        # solo el lugar vacio: lo que pasa ahi (acciones) es del guion, no de la imagen del lugar
        info = {"lugar": place["nombre"], "descripcion": place.get("prompt"), "luz": place.get("luz"),
                "atmosfera": place.get("atmosfera"), "utileria": place.get("utileria", [])}
    if kind == "toma":
        folder = ref.song_folder(node["semilla"])
        if not folder:
            return node_id, {"tema": str(node["semilla"])}
        cast = universo.frozen().get(str(node["semilla"]), {})
        director = ref.read_json(folder / "equipo" / "director.json", {}) or {}
        info = {"tema": folder.name, "personaje": data["personajes"].get(cast.get("id"), {}).get("nombre"),
                "lugar": data["locaciones"].get(cast.get("lugar_id"), {}).get("nombre"), "gesto": cast.get("gesto"),
                "que_hace": director.get("que_hace", ""),
                "referencias": [url for url in (chosen_url(parent) for parent in node["padres"]) if url]}
    label = {"vista": node.get("vista", ""), "expresion": node.get("expresion", ""),
             "tela": info.get("tela", ""), "objeto": str(info.get("objeto", ""))[:50]}.get(kind)
    who = info.get("personaje") or info.get("lugar") or info.get("tema") or node_id
    return (f"{who} · {label}" if label else who), info


def node_view(node_id, graph, data):
    node = graph[node_id]
    status, reason = ref.estado(node_id, graph, data)
    sheet, review = ref.ficha(node_id), ref.revision(node_id)
    _, chosen = ref.chosen_image(node_id)
    folder = ref.node_dir(node_id)
    versions = []
    for version in sheet["versiones"]:
        versions.append({"v": version["v"], "fecha": version.get("fecha"), "modelo": version.get("modelo"),
                         "legado": version.get("legado", False),
                         "candidatos": [{"url": image_url(folder / item["archivo"]), "hash": item["hash"],
                                         "revision": review["imagenes"].get(item["hash"])}
                                        for item in version["candidatos"] if (folder / item["archivo"]).is_file()]})
    title, info = describe(node_id, node, data)
    return {"id": node_id, "tipo": node["tipo"], "titulo": title, "info": info, "estado": status, "motivo": reason,
            "versiones": versions, "elegido": chosen["hash"] if chosen else None,
            "cascada": len(ref.cascada(node_id, graph))}


# --- proyecto, guion y escenas ----------------------------------------------------------------------
def song_title(folder):
    return folder.name.rsplit(" ", 1)[0]


def scene_view(seed, data, graph):
    """Una escena (un tema) con su elenco congelado, sinopsis, locacion, camara y estado de la toma."""
    folder = ref.song_folder(seed)
    overlay = (ref.read_json(project_dir() / "guion.json", {}) or {}).get("escenas", {}).get(str(seed), {})
    writer = ref.read_json(folder / "equipo" / "escritor.json", {}) or {}
    director = ref.read_json(folder / "equipo" / "director.json", {}) or {}
    photographer = ref.read_json(folder / "equipo" / "fotografo.json", {}) or {}
    plan = ref.read_json(folder / f"{folder.name}.json", {}) or {}
    cast = universo.frozen().get(str(seed)) or {}
    shot = f"toma/{seed}"
    status = ref.estado(shot, graph, data)[0] if shot in graph else "sin elenco"
    place_id = cast.get("lugar_id")
    person = data["personajes"].get(cast.get("id"), {})
    objects = person.get("objetos", [])
    index = cast.get("objeto")
    background = folder / "fondo.png"
    place_thumb = chosen_url(f"lugar/{place_id}") if place_id else None
    thumb = (chosen_url(shot) if shot in graph else None) or \
        (image_url(background) if background.is_file() else None) or place_thumb
    return {"semilla": seed, "nombre": folder.name, "titulo": song_title(folder),
            # nunca plan["idea"]: es la descripcion musical (va a Audio -> Musica)
            "sinopsis": overlay.get("sinopsis") or writer.get("logline") or writer.get("escena") or "",
            "que_hace": director.get("que_hace") or director.get("escena", ""),
            "personaje": cast.get("id"), "personaje_nombre": person.get("nombre"),
            "lugar": place_id, "lugar_nombre": data["locaciones"].get(place_id, {}).get("nombre"),
            "gesto": cast.get("gesto"), "objeto": index,
            "objeto_texto": objects[index] if index is not None and index < len(objects) else None,
            "plano": photographer.get("plano"), "angulo": photographer.get("angulo"), "lente": photographer.get("lente"),
            "luz": photographer.get("luz"), "paleta": plan.get("paleta"), "duracion": plan.get("duracion_seg"),
            "estado": status, "miniatura": thumb, "miniatura_lugar": place_thumb}


def default_structure(scenes):
    """Sin guion guardado: un acto, una secuencia por personaje (sus temas en orden)."""
    sequences = {}
    for scene in scenes:
        key = scene["personaje"] or "sin_elenco"
        sequences.setdefault(key, {"titulo": scene["personaje_nombre"] or "Sin elenco", "sinopsis": "",
                                   "temas": []})["temas"].append(scene["semilla"])
    return {"premisa": "", "actos": [{"titulo": "Temporada 1", "secuencias": list(sequences.values())}],
            "por_defecto": True}


def fountain(structure, scenes):
    """Guion literario en formato Fountain armado desde las escenas (solo lectura)."""
    by_seed = {scene["semilla"]: scene for scene in scenes}
    lines = [f"Title: {structure.get('premisa') or 'Neo-Kansai Delta'}", ""]
    for act in structure["actos"]:
        lines += [f"# {act['titulo']}", ""]
        for sequence in act["secuencias"]:
            lines += [f"## {sequence['titulo']}", ""]
            for seed in sequence["temas"]:
                scene = by_seed.get(seed)
                if not scene:
                    continue
                lines += [f"EXT. {(scene['lugar_nombre'] or 'LUGAR').upper()} - NOCHE", "", scene["sinopsis"], ""]
                if scene["que_hace"]:
                    lines += [f"{scene['personaje_nombre'] or 'Alguien'}: {scene['que_hace']}", ""]
                lines += [f"[[{scene['titulo']} · {scene['semilla']}]]", ""]
    return "\n".join(lines)


def script_view():
    data, graph = universo.load(), ref.nodos()
    scenes = [scene_view(seed, data, graph) for seed in ref.song_seeds()]
    saved = ref.read_json(project_dir() / "guion.json", {}) or {}
    structure = {"premisa": saved.get("premisa", ""), "actos": saved["actos"]} if saved.get("actos") \
        else default_structure(scenes)
    return {"estructura": structure, "escenas": scenes, "propuesta": ref.read_json(cola.STRUCTURE_PROPOSAL),
            "personajes": [{"id": pid, "nombre": person["nombre"], "objetos": person.get("objetos", []),
                            "gestos": person.get("gestos", []), "retrato": chosen_url(f"retrato/{pid}")}
                           for pid, person in data["personajes"].items()],
            "lugares": [{"id": lid, "nombre": place["nombre"], "miniatura": chosen_url(f"lugar/{lid}")}
                        for lid, place in data["locaciones"].items()],
            "fountain": fountain(structure, scenes)}


def project_view():
    data, graph = universo.load(), ref.nodos()
    saved = ref.read_json(project_dir() / "proyecto.json", {}) or {}
    saved = {**saved, **(saved.get("premisa") or {})}   # la premisa vive en su propio bloque
    shots = [node_id for node_id in graph if node_id.startswith("toma/")]
    states = [ref.estado(node_id, graph, data)[0] for node_id in shots]
    approved = [node_id for node_id, state in zip(shots, states) if state == "aprobado"]
    poster = chosen_url(sorted(approved)[-1]) if approved else None
    if not poster:
        backgrounds = sorted(ref.SONGS.glob("* 20*/fondo.png"))
        poster = image_url(backgrounds[-1]) if backgrounds else None
    return {"titulo": saved.get("titulo", "Neo-Kansai Delta"),
            "logline": saved.get("logline", "Una megaciudad vertical sobre una bahia que se trago la ciudad vieja: "
                                            "cada tema es una noche de alguien que vive ahi."),
            "genero": saved.get("genero", "Synthwave · cyberpunk anime 90s"),
            "formato": saved.get("formato", "Un tema = una escena = una portada 1920x1080"),
            "tono": saved.get("tono", "melancolico, nocturno, lluvioso"),
            "concepto": saved.get("concepto", data.get("_nota", "")),
            "reglas": data.get("reglas", []), "poster": poster, "idea": saved.get("idea", ""),
            "intencion": saved.get("intencion", {}), "nombre": saved.get("nombre"), "id": sf.STATE["id"],
            "metricas": {"escenas": len(ref.song_seeds()), "tomas": len(shots),
                         "aprobadas": states.count("aprobado"), "rechazadas": states.count("rechazado"),
                         "desactualizadas": states.count("desactualizado"),
                         "personajes": len(data["personajes"]), "lugares": len(data["locaciones"])}}


def characters_view():
    data, graph = universo.load(), ref.nodos()
    frozen = universo.frozen()
    return {"personajes": [{"id": pid, "nombre": person["nombre"], "alias": person.get("alias"),
                            "arquetipo": person.get("arquetipo"), "edad": person.get("edad"),
                            "retrato": chosen_url(f"retrato/{pid}"),
                            "estado": ref.estado(f"retrato/{pid}", graph, data)[0],
                            "ficha_pedida": ref.ficha_pedida(pid),
                            "temas": sorted(int(seed) for seed, cast in frozen.items() if cast.get("id") == pid)}
                           for pid, person in data["personajes"].items()]}


def character_view(pid):
    data, graph = universo.load(), ref.nodos()
    if pid not in data["personajes"]:
        raise ValueError("personaje desconocido")
    person = data["personajes"][pid]

    def nodes(prefix):
        return [node_view(node_id, graph, data) for node_id in sorted(graph)
                if node_id.startswith(prefix) and graph[node_id].get("personaje") == pid]
    views = {node["id"].split("__")[1]: node for node in nodes("vista/")}
    faces = {node["id"].split("__")[1]: node for node in nodes("expresion/")}
    return {"id": pid, "datos": {key: person.get(key) for key in
                                 ("nombre", "alias", "arquetipo", "genero", "edad", "oficio", "aspecto", "vestuario",
                                  "implantes", "objetos", "historia", "deseo", "miedo", "contradiccion", "secreto",
                                  "gestos", "lugares", "relaciones", "arco")},
            "ficha_pedida": ref.ficha_pedida(pid),
            "retrato": node_view(f"retrato/{pid}", graph, data),
            "vestuario": node_view(f"vestuario/{pid}", graph, data),
            "vistas": [views[name] for name in ref.VIEWS if name in views],
            "expresiones": [faces[name] for name in ref.EXPRESSIONS if name in faces],
            "cinematico": node_view(f"cinematico/{pid}", graph, data),
            "telas": nodes("tela/"), "objetos": nodes("objeto/"),
            "hoja": node_view(f"hoja/{pid}", graph, data),
            "escenas": [scene_view(int(seed), data, graph) for seed, cast in sorted(universo.frozen().items())
                        if cast.get("id") == pid and ref.song_folder(int(seed))]}


def scene_technical(scene_id):
    """Guion tecnico de una escena del guion (proyectos nuevos): planta + camaras 3D de inicio y fin por plano."""
    data, graph = universo.load(), ref.nodos()
    structure = guion_sf.load(project_dir())
    _, scene = guion_sf.find_scene(structure, scene_id)
    if scene.get("tema"):
        return technical_view(int(scene["tema"]))
    folder = ref.plan_folder(scene_id)
    saved = dc.load(folder)
    plan = saved or dc.initial_scene(scene, data)
    _sync_shots(plan, scene)
    shots = []
    for index, shot in enumerate(plan["planos"]):
        base = f"plano/{scene_id}__{shot.get('id')}"
        shots.append({"id": shot.get("id"), "movimiento": dc.movimiento(plan, shot),
                      "camaras": {"ini": dc.camera(plan, shot, 0.0), "fin": dc.camera(plan, shot, 1.0)},
                      "nodos": {moment: node_view(f"{base}_{moment}", graph, data) for moment in ("ini", "fin")
                                if f"{base}_{moment}" in graph},
                      "clip": node_view(f"clip/{scene_id}__{shot.get('id')}", graph, data)
                      if f"clip/{scene_id}__{shot.get('id')}" in graph else None,
                      "previz": {moment: image_url(folder / "toma" / "previz" / f"{shot.get('id')}_{moment}.png")
                                 for moment in ("ini", "fin")
                                 if (folder / "toma" / "previz" / f"{shot.get('id')}_{moment}.png").is_file()}})
    return {"escena_id": scene_id, "escena": scene, "planta": plan, "guardada": bool(saved), "motivo": "",
            "tipos": dc.SHOT_TYPES, "planos": shots, "set3d": plan.get("set3d") or dc.DEFAULT_SET,
            "puesta": dc.staging(plan), "equipo": {},
            "escenas": [{"id": item["id"], "titulo": f"{item.get('int_ext', '')} {item.get('lugar', '')} - "
                                                      f"{item.get('momento', '')}", "tema": item.get("tema")}
                        for item in guion_sf.scenes(structure) if item.get("estado") != "oculta"]}


def _sync_shots(plan, scene):
    """Los planos de la planta siguen a los del guion (mismo id y tipo; los nuevos entran con camara por defecto)."""
    by_id = {shot.get("id"): shot for shot in plan.get("planos", [])}
    initial = {shot["id"]: shot for shot in dc.initial_scene(scene, universo.load())["planos"]}
    synced = []
    for index, shot in enumerate(scene.get("planos", []), 1):
        current = dict(by_id.get(shot["id"]) or initial.get(shot["id"]) or {"camara": {"x": 5, "y": 8}})
        current.update(id=shot["id"], toma=index, tipo=shot.get("tipo") if shot.get("tipo") in dc.SHOT_TYPES else "PM")
        synced.append(current)
    plan["planos"] = synced
    plan.setdefault("set3d", dc.DEFAULT_SET)


def technical_view(seed):
    data, graph = universo.load(), ref.nodos()
    folder = ref.song_folder(seed)
    if not folder:
        raise ValueError("tema desconocido")
    cast = universo.frozen().get(str(seed))
    saved = dc.load(folder)
    plan = saved
    if not plan and cast:
        person = data["personajes"][cast["id"]]
        photographer = ref.read_json(folder / "equipo" / "fotografo.json", {}) or {}
        text = person["objetos"][cast["objeto"]] if cast.get("objeto") is not None else None
        plan = dc.initial(cast, person, photographer, text)
    shot = f"toma/{seed}"
    reason = "" if plan else ("La escena todavia no tiene elenco congelado (falta correr la migracion)." if not cast
                              else "Falta el plano del fotografo: la planta se arma cuando este, o a mano.")
    shots = []
    if plan:
        for item in plan["planos"]:
            clip_id = f"clip/t{seed}__p1"
            shots.append({"id": item.get("id") or "p1", "movimiento": dc.movimiento(plan, item),
                          "camaras": {"ini": dc.camera(plan, item, 0.0), "fin": dc.camera(plan, item, 1.0)},
                          "nodos": {}, "clip": node_view(clip_id, graph, data) if clip_id in graph else None,
                          "previz": {moment: image_url(folder / "toma" / "previz" / f"{item.get('id') or 'p1'}_{moment}.png")
                                     for moment in ("ini", "fin")
                                     if (folder / "toma" / "previz" / f"{item.get('id') or 'p1'}_{moment}.png").is_file()}})
    return {"semilla": seed, "escena_id": f"t{seed}", "escena": scene_view(seed, data, graph), "planta": plan,
            "guardada": bool(saved), "motivo": reason, "planos": shots,
            "set3d": (plan or {}).get("set3d") or dc.DEFAULT_SET,
            "escenas": [{"id": f"t{item}", "titulo": ref.song_folder(item).name, "tema": item}
                        for item in ref.song_seeds() if (ref.song_folder(item) / "equipo").is_dir()],
            "puesta": dc.staging(plan), "tipos": dc.SHOT_TYPES,
            "toma": node_view(shot, graph, data) if shot in graph else None,
            "equipo": {role: ref.read_json(folder / "equipo" / f"{role}.json") for role in ("director", "fotografo")
                       if (folder / "equipo" / f"{role}.json").is_file()}}


def edit_view():
    data, graph = universo.load(), ref.nodos()
    saved = ref.read_json(project_dir() / "edicion.json", {}) or {}
    seeds = ref.song_seeds()
    order = [seed for seed in saved.get("orden", []) if seed in seeds] + \
        [seed for seed in seeds if seed not in saved.get("orden", [])]
    clips = []
    for seed in order:
        scene = scene_view(seed, data, graph)
        sheet = ref.read_json(ref.song_folder(seed) / "ficha.json", {}) or {}
        extra = saved.get("clips", {}).get(str(seed), {})
        clips.append({**scene, "publicar": extra.get("publicar", False), "fecha": extra.get("fecha", ""),
                      "titulo_youtube": sheet.get("titulo_youtube"), "duracion": scene["duracion"] or 180})
    return {"clips": clips}


# --- temas, piloto y cola -----------------------------------------------------------------------------
def song_view(seed):
    """Ficha de un tema para el Export: SEO, concepto, departamentos y fondo actual."""
    folder = ref.song_folder(seed)
    sheet = ref.read_json(folder / "ficha.json", {}) or {}
    team = {role: ref.read_json(folder / "equipo" / f"{role}.json") for role in ROLES
            if (folder / "equipo" / f"{role}.json").is_file()}
    prompt = folder / "equipo" / "prompt.txt"
    images = {name: image_url(folder / name) for name in ("fondo.png", "fondo_anterior.png") if (folder / name).is_file()}
    return {"semilla": seed, "nombre": folder.name, "titulo_youtube": sheet.get("titulo_youtube"),
            "descripcion": sheet.get("descripcion"), "etiquetas": sheet.get("etiquetas", []),
            "palabras_clave": sheet.get("palabras_clave", []), "genero": sheet.get("genero"),
            "uso": sheet.get("uso"), "paleta": sheet.get("paleta"), "concepto": sheet.get("concepto"),
            "equipo": team, "prompt": prompt.read_text(encoding="utf-8") if prompt.is_file() else sheet.get("prompt_imagen"),
            "imagenes": images, "elenco": universo.frozen().get(str(seed))}


def pilot_view():
    """Grillas del piloto (universo/referencias/_piloto/<fecha>/) para elegir ajustes."""
    runs = []
    base = ref.STORE / "_piloto"
    for folder in sorted((path for path in base.iterdir() if path.is_dir()), reverse=True) if base.is_dir() else []:
        files = sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_TYPES)
        stages = {}
        for path in files:
            stage = path.name[0] if path.name[:2] in ("A_", "B_", "C_") else "hojas"
            stages.setdefault(stage, []).append({"nombre": path.stem, "url": image_url(path)})
        runs.append({"carpeta": folder.name, "etapas": stages, "imagenes": len(files)})
    return {"corridas": runs, "ajustes": ref.settings()}


def music_view():
    """La parte musical de cada tema (Audio -> Musica), separada del guion."""
    songs = []
    for seed in ref.song_seeds():
        folder = ref.song_folder(seed)
        plan = ref.read_json(folder / f"{folder.name}.json", {}) or {}
        project = next(folder.glob("*.flp"), None)
        songs.append({"semilla": seed, "nombre": folder.name, **{key: plan.get(key) for key in MUSIC_FIELDS},
                      "flp": str(project) if project else None, "midi": str(next(folder.glob("*.mid"), "")) or None})
    imported = ref.read_json(project_dir() / "musica.json")   # proyectos importados de Doble Fondo
    if imported:
        songs.append({"semilla": 0, "nombre": imported.get("titulo"), "titulo": imported.get("titulo"),
                      "bpm": imported.get("bpm"), "tonica": imported.get("tonalidad"), "escala": "",
                      "idea": imported.get("estilo_musical"), "duracion_seg": imported.get("duracion"),
                      "letra": imported.get("letra"), "flp": None})
    return {"temas": songs}


def stages_view():
    """Estado de cada etapa: vacia, en curso, lista."""
    data, graph = universo.load(), ref.nodos()
    project = sf.read_project()
    premise = {**project, **(project.get("premisa") or {})}
    script = ref.read_json(project_dir() / "guion.json", {}) or {}
    seeds = ref.song_seeds()

    def state_of(kinds):
        states = [ref.estado(node_id, graph, data)[0] for node_id in graph if node_id.split("/")[0] in kinds]
        states = [state for state in states if state != "a pedido"]
        if not states:
            return "vacia"
        return "lista" if all(state == "aprobado" for state in states) else "en curso"
    plants = sum(1 for seed in seeds if (ref.song_folder(seed) / "toma" / "planta.json").is_file())
    return {"idea": "lista" if premise.get("idea") else "vacia",
            "premisa": "lista" if premise.get("logline") else ("en curso" if premise.get("titulo") else "vacia"),
            "guion": "lista" if (script.get("secuencias") or (script.get("actos") and seeds)) else
            ("en curso" if seeds or script.get("premisa") else "vacia"),
            "casting": state_of(("retrato", "vestuario")), "arte": state_of(("lugar", "objeto")),
            "direccion": "vacia" if not plants else ("lista" if plants >= len(seeds) else "en curso"),
            "storyboard": state_of(("toma",)), "audio": "lista" if seeds else "vacia",
            "edicion": "lista" if (project_dir() / "edicion.json").is_file() else "vacia", "export": "en curso"}


def agents_view():
    items = []
    for path in sorted(AGENTS.rglob("*.md")):
        if AGENT_BACKUPS in path.parents:
            continue
        backups = sorted(AGENT_BACKUPS.glob(f"{path.stem}.*.md"), reverse=True)
        items.append({"ruta": str(path.relative_to(AGENTS)).replace("\\", "/"), "nombre": path.stem,
                      "etapa": AGENT_STAGES.get(path.stem, ""), "editable": True,
                      "respaldos": [backup.name for backup in backups[:10]]})
    external = []
    if PIXELSET_AGENTS.is_dir():
        for path in sorted(PIXELSET_AGENTS.rglob("*")):
            if path.is_file():
                external.append({"ruta": str(path), "nombre": path.name, "legible": path.suffix.lower() in (".md", ".txt")})
    return {"agentes": items, "pixelset": external}


def agent_path(relative):
    path = (AGENTS / relative).resolve()
    if path.suffix != ".md" or not path.is_relative_to(AGENTS.resolve()) or AGENT_BACKUPS.resolve() in path.parents:
        raise ValueError("ruta de agente no permitida")
    return path


def agent_text(relative):
    if relative.startswith(str(PIXELSET_AGENTS)):
        path = Path(relative).resolve()
        if not path.is_relative_to(PIXELSET_AGENTS.resolve()) or path.suffix.lower() not in (".md", ".txt"):
            raise ValueError("solo .md o .txt de Pixel-set")
        return {"ruta": relative, "texto": path.read_text(encoding="utf-8", errors="replace"), "editable": False}
    path = agent_path(relative)
    return {"ruta": relative, "texto": path.read_text(encoding="utf-8") if path.is_file() else "", "editable": True}


def save_agent(relative, text):
    path = agent_path(relative)
    if path.is_file():
        AGENT_BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        (AGENT_BACKUPS / f"{path.stem}.{stamp}.md").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"ok": True}


def restore_agent(relative, backup):
    path = agent_path(relative)
    source = (AGENT_BACKUPS / backup).resolve()
    if not source.is_relative_to(AGENT_BACKUPS.resolve()) or not source.name.startswith(path.stem + "."):
        raise ValueError("respaldo no valido")
    return save_agent(relative, source.read_text(encoding="utf-8"))


def ollama_models():
    try:
        with urllib.request.urlopen(cola.OLLAMA_PS.replace("/api/ps", "/api/tags"), timeout=3) as response:
            return [item["name"] for item in json.loads(response.read()).get("models", [])]
    except OSError:
        return []


def comfy_alive():
    try:
        with urllib.request.urlopen(fondo_comfy.URL + "/system_stats", timeout=2) as response:
            stats = json.loads(response.read())
        device = (stats.get("devices") or [{}])[0]
        return {"prendido": True, "vram_libre_gb": round(device.get("vram_free", 0) / 2**30, 1)}
    except OSError:
        return {"prendido": False}


def ollama_loaded_models():
    try:
        with urllib.request.urlopen(cola.OLLAMA_PS, timeout=3) as response:
            return [item["name"] for item in json.loads(response.read()).get("models", [])]
    except OSError:
        return []


def log_view(node=None):
    """Que se esta generando, la cola, los pedidos a Ollama, el final del log de ComfyUI y el historial."""
    queue = queue_view()
    log = ref.STORE / "registro.log"
    history = log.read_text(encoding="utf-8").splitlines()[-400:] if log.is_file() else []
    if node:
        history = [line for line in history if node in line]
    comfy_log = ref.STORE / "comfyui.log"
    comfy_tail = comfy_log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:] if comfy_log.is_file() else []
    return {**queue, **batches_view(), "historial": history[-200:], "comfyui_log": comfy_tail,
            "ollama_cargado": ollama_loaded_models(),
            "comfyui": comfy_alive(), "pausa": cola.PAUSE.exists(),
            "plan": [{"nodo": job["nodo"], "motivo": job["motivo"]} for job in ref.planificar("pendientes")][:60]}


def config_view():
    return {"config": sf.config(), "ajustes": ref.settings(), "modelos_ollama": ollama_models(),
            "opciones": {"bloom": sorted(postproceso.BLOOMS), "negros": sorted(postproceso.BLACKS)},
            "rutas": {key: str(value) for key, value in sf.paths(sf.STATE["id"]).items()}}


_GRAPH = {}


def graph_cache(_scene=None):
    return _GRAPH.setdefault("g", ref.nodos())


def script_doc():
    """Guion por secuencias -> escenas -> planos, su texto Fountain, versiones y propuestas pendientes."""
    _GRAPH.clear()
    data = universo.load()
    project = sf.read_project()
    structure = guion_sf.load(project_dir())
    title = (project.get("premisa") or {}).get("titulo") or project.get("titulo") or project.get("nombre") or "Guion"
    frozen = universo.frozen()
    for scene in guion_sf.scenes(structure):
        if scene.get("tema"):
            scene["miniatura"] = chosen_url(f"toma/{scene['tema']}") if f"toma/{scene['tema']}" in ref.nodos() else None
            scene["gesto"] = (frozen.get(str(scene["tema"])) or {}).get("gesto")
            scene["objeto"] = (frozen.get(str(scene["tema"])) or {}).get("objeto")
        if scene.get("lugar_id"):
            scene["miniatura_lugar"] = chosen_url(f"lugar/{scene['lugar_id']}")
        for shot in scene.get("planos", []):   # storyboard: la imagen de inicio de cada plano (o su previz)
            node = f"plano/{scene['id']}__{shot['id']}_ini"
            shot["miniatura"] = chosen_url(node) if node in graph_cache(scene) else None
            shot["estado_imagen"] = ref.estado(node, graph_cache(scene))[0] if node in graph_cache(scene) else None
            sketch = ref.plan_folder(scene["id"]) / "toma" / "previz" / f"{shot['id']}_ini.png"
            shot["previz"] = image_url(sketch) if sketch.is_file() else None
    premise = {**project, **(project.get("premisa") or {})}
    return {"estructura": structure, "fountain": guion_sf.to_fountain(structure, title), "titulo": title,
            "versiones": guion_sf.versions(project_dir()), "propuestas": guion_sf.proposals(project_dir()),
            "premisa": {key: premise.get(key, "") for key in ("titulo", "logline", "tema", "genero", "tono")},
            "personajes": [{"id": pid, "nombre": person["nombre"], "objetos": person.get("objetos", []),
                            "gestos": person.get("gestos", []), "retrato": chosen_url(f"retrato/{pid}")}
                           for pid, person in data["personajes"].items()],
            "lugares": [{"id": lid, "nombre": place["nombre"], "miniatura": chosen_url(f"lugar/{lid}")}
                        for lid, place in data["locaciones"].items()]}


def export_script(kind):
    """Texto para descargar y una copia en exportes/ del proyecto."""
    doc = script_doc()
    kind = "fdx" if kind == "fdx" else "fountain"
    text = guion_sf.to_fdx(doc["fountain"]) if kind == "fdx" else doc["fountain"]
    name = re.sub(r"[^\w\- ]", "", doc["titulo"]).strip() or "guion"
    target = project_dir() / "exportes" / f"{name}.{kind}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"nombre": name, "texto": text, "guardado_en": str(target)}


def save_script(structure):
    """Guarda el guion; si una escena-tema cambio de lugar o de elenco, el elenco congelado del tema la sigue."""
    data = universo.load()
    saved = guion_sf.save(project_dir(), structure)
    frozen = universo.frozen()
    for scene in guion_sf.scenes(guion_sf.load(project_dir())):
        seed = scene.get("tema")
        if not seed or str(seed) not in frozen:
            continue
        changes = {}
        if scene.get("lugar_id") in data["locaciones"] and scene["lugar_id"] != frozen[str(seed)].get("lugar_id"):
            changes["lugar_id"] = scene["lugar_id"]
        if scene.get("elenco") and scene["elenco"][0] in data["personajes"] and \
                scene["elenco"][0] != frozen[str(seed)].get("id"):
            changes["id"] = scene["elenco"][0]
        if changes:
            universo.set_frozen(int(seed), **changes)
    return saved


def queue_view():
    status = ref.read_json(ref.STORE / "cola.json", {}) or {}
    log = ref.STORE / "registro.log"
    lines = log.read_text(encoding="utf-8").splitlines()[-40:] if log.is_file() else []
    requests = (ref.read_json(cola.requests_file(), []) or [])[-15:]
    pending = sum(1 for item in cola.batches() if item and item["estado"] == "pendiente")
    return {"corriendo": (ref.STORE / "cola.lock").is_file(), "estado": status, "registro": lines,
            "lotes_pendientes": pending,
            "pedidos": requests}


def start_queue(ids, only_ollama=False, label=""):
    """Agrega un lote a la cola de generacion y arranca el trabajador si no hay uno. Nunca rechaza: si ya hay algo
    corriendo, el lote espera su turno. ids ya filtrados contra el grafo (nada del usuario va a una consola)."""
    batch = cola.add_batch(ids, only_ollama, label or (f"{len(ids)} nodos: {', '.join(ids[:3])}" if ids else
                                                       ("pedidos a Ollama" if only_ollama else "todo lo pendiente")))
    position = sum(1 for item in cola.batches() if item and item["estado"] in ("pendiente", "corriendo"))
    launched = launch_worker()
    return {"lote": batch["lote"], "posicion": position, "trabajador_nuevo": launched}


def launch_worker():
    """Arranca el trabajador de la cola si no hay uno vivo y hay lotes pendientes."""
    if cola.worker_running() or not any(item and item["estado"] == "pendiente" for item in cola.batches()):
        return False
    subprocess.Popen([sys.executable, str(ROOT / "cola_referencias.py"), "trabajar", "--proyecto", sf.STATE["id"]],
                     cwd=ROOT, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) |
                     getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    return True


def batches_view():
    items = [item for item in cola.batches() if item]
    order = {"corriendo": 0, "pendiente": 1}
    items.sort(key=lambda item: (order.get(item["estado"], 2), item["lote"] if item["estado"] in order else -item["lote"]))
    return {"lotes": items[:60], "trabajador": cola.worker_running(), "pausa": cola.PAUSE.exists()}


# --- escrituras ---------------------------------------------------------------------------------------
def save_overlay(name, change):
    path = project_dir() / name
    current = ref.read_json(path, {}) or {}
    change(current)
    ref.write_json(path, current)
    return current


def valid_plan(plan):
    """Planta que manda la pagina: solo numeros entre 0 y 10 y los campos conocidos."""
    def clamp(value):
        return round(max(0.0, min(10.0, float(value))), 2)
    people = {str(key): {"x": clamp(value["x"]), "y": clamp(value["y"]), "mira": str(value.get("mira", ""))[:60],
                         "nombre": str(value.get("nombre", key))[:80]}
              for key, value in (plan.get("personajes") or {}).items()}
    objects = [{"id": str(item["id"])[:40], "nombre": str(item.get("nombre", ""))[:80], "x": clamp(item["x"]),
                "y": clamp(item["y"])} for item in plan.get("objetos") or []]
    names = set(people) | {item["id"] for item in objects}
    def camera3d(value):
        if not isinstance(value, dict):
            return None
        target = value.get("mira") or [5, 5, 1.5]
        return {"x": clamp(value["x"]), "y": clamp(value["y"]), "z": round(max(0.1, min(6.0, float(value["z"]))), 2),
                "mira": [round(max(-20.0, min(30.0, float(item))), 2) for item in target[:3]],
                "focal": round(max(10.0, min(200.0, float(value.get("focal", 35)))), 1)}

    def poses(value):
        return {str(key): {"x": clamp(item["x"]), "y": clamp(item["y"])} for key, item in (value or {}).items()
                if str(key) in people}
    shots = []
    for index, shot in enumerate(plan.get("planos") or [], 1):
        if shot.get("tipo") not in dc.SHOT_TYPES:
            raise ValueError("tipo de plano desconocido")
        clean = {"toma": index, "tipo": shot["tipo"],
                 "camara": {"x": clamp(shot["camara"]["x"]), "y": clamp(shot["camara"]["y"])},
                 "apunta_a": [name for name in shot.get("apunta_a", []) if name in names],
                 "cruza_eje": bool(shot.get("cruza_eje"))}
        if shot.get("id"):
            clean["id"] = str(shot["id"])[:20]
        for key in ("cam_ini", "cam_fin"):
            if camera3d(shot.get(key)):
                clean[key] = camera3d(shot[key])
        for key in ("pers_ini", "pers_fin"):
            if shot.get(key):
                clean[key] = poses(shot[key])
        shots.append(clean)
    for person in people.values():
        if person["mira"] and person["mira"] not in names:
            person["mira"] = ""
    axis = [name for name in plan.get("eje") or [] if name in names][:2]
    result = {"personajes": people, "objetos": objects, "eje": axis, "planos": shots}
    box = (plan.get("set3d") or {}).get("caja")
    if box:
        result["set3d"] = {**dc.DEFAULT_SET, "caja": {key: round(max(2.0, min(40.0, float(box[key]))), 2)
                                                      for key in ("ancho", "fondo", "alto")}}
    return result


def upload(body):
    """Imagen subida a mano: nueva version del nodo, aprobada por quien la sube."""
    node_id = body["id"]
    graph = ref.nodos()
    if node_id not in graph or graph[node_id]["tipo"] not in UPLOAD_KINDS:
        raise ValueError("no se puede subir una imagen a ese nodo")
    raw = base64.b64decode(str(body["datos"]).split(",", 1)[-1], validate=True)
    suffix = next((ext for signature, ext in SIGNATURES.items() if raw.startswith(signature)), None)
    if not suffix:
        raise ValueError("solo PNG o JPG")
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"subida{suffix}"
        source.write_bytes(raw)
        value, digest = ref.recipe(node_id, graph)
        version = ref.record_version(node_id, [source], value, digest, "subida", {"subida": True})
    ref.review_image(node_id, version["candidatos"][0]["hash"], "aprobado", "imagen subida a mano")
    return version


class Handler(BaseHTTPRequestHandler):
    server_version = "StoryForge"

    def log_message(self, *args):
        pass

    def host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def send_bytes(self, body, kind, cache="no-cache", code=200):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value, code=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                        "no-store", code)

    def send_static(self, path):
        base = WEB.resolve()
        target = (base / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if not target.is_relative_to(base) or target.suffix not in STATIC_TYPES or not target.is_file() \
                or "proyectos" in target.relative_to(base).parts:
            return self.send_json({"error": "no existe"}, 404)
        return self.send_bytes(target.read_bytes(), STATIC_TYPES[target.suffix])

    def send_image(self, relative):
        try:
            path = (Path(relative) if Path(relative).is_absolute() else ref.ROOT / relative).resolve()
        except (OSError, ValueError):
            return self.send_json({"error": "ruta invalida"}, 400)
        if path.suffix.lower() not in IMAGE_TYPES or not any(path.is_relative_to(root) for root in allowed_roots()) \
                or not path.is_file():
            return self.send_json({"error": "imagen no permitida"}, 403)
        return self.send_bytes(path.read_bytes(), IMAGE_TYPES[path.suffix.lower()], "max-age=3600")

    def summary(self):
        graph, data = ref.nodos(), universo.load()
        counts = {}
        for node_id in graph:
            status, _ = ref.estado(node_id, graph, data)
            counts.setdefault(node_id.split("/")[0], {}).setdefault(status, 0)
            counts[node_id.split("/")[0]][status] += 1
        return {"conteos": counts, "nombres": NAMES, "cola": queue_view(), "ollama_cargado": cola.ollama_loaded(),
                "plan": ref.planificar("pendientes", graph)}

    def do_GET(self):
        if not self.host_ok():
            return self.send_json({"error": "host no permitido"}, 403)
        url = urlparse(self.path)
        query = parse_qs(url.query)

        def arg(name, default=None):
            return query.get(name, [default])[0]
        try:
            if not url.path.startswith(("/api/", "/img")):
                return self.send_static(url.path)
            if url.path == "/img":
                return self.send_image(arg("p", ""))
            if url.path == "/api/estado":
                graph, data = ref.nodos(), universo.load()
                kind = arg("tipo", "retrato")
                return self.send_json({"tipo": kind, "nodos": [node_view(node_id, graph, data) for node_id in sorted(graph)
                                                               if node_id.split("/")[0] == kind]})
            if url.path == "/api/cascada":
                if arg("id") not in ref.nodos():
                    raise ValueError("nodo desconocido")
                return self.send_json({"id": arg("id"), "cascada": ref.cascada(arg("id"))})
            routes = {"/api/proyectos": lambda: {**sf.registry(), "activo": sf.STATE["id"],
                                                 "carpeta_proyectos": str(sf.PROJECTS)},
                      "/api/musica": music_view, "/api/etapas": stages_view, "/api/agentes": agents_view,
                      "/api/agente": lambda: agent_text(arg("ruta", "")), "/api/config": config_view,
                      "/api/log": lambda: log_view(arg("nodo")),
                      "/api/guion_doc": script_doc,
                      "/api/revision": lambda: revisores_sf.view(project_dir(), arg("etapa", "guion")),
                      "/api/libros": lambda: libros_sf.overview() if libros_sf.available() else {"error_libros": True},
                      "/api/libros_buscar": lambda: {"pasajes": libros_sf.search(arg("q", "")[:300], arg("estilo"))},
                      "/api/guion_export": lambda: export_script(arg("formato")),
                      "/api/proyecto_carpetas": sf.folders_view,
                      "/api/lotes": batches_view,
                      "/api/proyecto": project_view, "/api/resumen": self.summary, "/api/cola": queue_view,
                      "/api/temas": lambda: {"temas": [song_view(seed) for seed in ref.song_seeds()]},
                      "/api/piloto": pilot_view, "/api/guion": script_view, "/api/personajes": characters_view,
                      "/api/personaje": lambda: character_view(arg("id", "")),
                      "/api/tecnico": lambda: scene_technical(arg("escena")) if arg("escena")
                      else technical_view(int(arg("semilla", "0"))), "/api/edicion": edit_view}
            if url.path not in routes:
                return self.send_json({"error": "no existe"}, 404)
            return self.send_json(routes[url.path]())
        except (KeyError, ValueError, TypeError) as error:
            return self.send_json({"error": str(error)}, 400)
        except OSError as error:
            return self.send_json({"error": f"no se pudo con el archivo o la carpeta: {error}"}, 500)

    def do_POST(self):
        port = self.server.server_address[1]
        origin = self.headers.get("Origin", "")
        if not self.host_ok() or origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self.send_json({"error": "origen no permitido"}, 403)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send_json({"error": "se espera JSON"}, 415)
        path = urlparse(self.path).path
        size = int(self.headers.get("Content-Length", "0") or 0)
        if size > (MAX_UPLOAD if path in ("/api/subir", "/api/previz") else MAX_BODY):
            return self.send_json({"error": "pedido demasiado grande"}, 413)
        handlers = {"/api/revisar": self.post_review, "/api/elegir": self.post_choose,
                    "/api/regenerar": self.post_regenerate, "/api/ajustes": self.post_settings,
                    "/api/proyecto": self.post_project, "/api/escena": self.post_scene, "/api/texto": self.post_text,
                    "/api/subir": lambda body: {"ok": True, "version": upload(body)["v"]},
                    "/api/ficha_pedir": self.post_sheet, "/api/tecnico": self.post_technical,
                    "/api/edicion": self.post_edit, "/api/generar": self.post_generate,
                    "/api/guion": self.post_script, "/api/propuesta": self.post_proposal,
                    "/api/proyecto_activo": self.post_active, "/api/proyecto_guardar": self.post_save_project,
                    "/api/proyecto_cargar": self.post_load_project, "/api/proyecto_nuevo": self.post_new_project,
                    "/api/importar_df": self.post_import_df,
                    "/api/proyecto_guardar_aqui": lambda body: {"ok": True, **sf.guardar_aqui()},
                    "/api/abrir_carpeta": self.post_open_folder,
                    "/api/lote_cancelar": lambda body: {"ok": True, **cola.cancel_batch(int(body["lote"]))},
                    "/api/lotes_limpiar": lambda body: (cola.clear_finished(), {"ok": True})[1],
                    "/api/cola_arrancar": lambda body: {"ok": True, "trabajador_nuevo": launch_worker()},
                    "/api/config": self.post_config, "/api/pausa": self.post_pause,
                    "/api/agente": lambda body: save_agent(str(body["ruta"]), str(body["texto"])[:200000]),
                    "/api/agente_restaurar": lambda body: restore_agent(str(body["ruta"]), str(body["respaldo"])),
                    "/api/guion_doc": self.post_script_doc,
                    "/api/guion_version": lambda body: {"ok": bool(guion_sf.restore(project_dir(), str(body["nombre"])))},
                    "/api/propuesta_guion": self.post_script_proposal,
                    "/api/previz": self.post_previz, "/api/clip_pedir": self.post_clip,
                    "/api/revision_seguimiento": lambda body: (revisores_sf.save_follow_up(
                        project_dir(), self._stage(body), str(body["texto"])[:20000]), {"ok": True})[1]}
        if path not in handlers:
            return self.send_json({"error": "no existe"}, 404)
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
            return self.send_json(handlers[path](body))
        except (KeyError, ValueError, TypeError, IndexError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, 400)
        except OSError as error:   # archivos o carpetas: se avisa en la pagina en vez de cortar la conexion
            return self.send_json({"error": f"no se pudo con el archivo o la carpeta: {error}"}, 500)

    # --- POST ---
    def post_review(self, body):
        ref.review_image(body["id"], body["hash"], body["estado"], str(body.get("nota", ""))[:2000],
                         str(body.get("accion", ""))[:40])
        return {"ok": True}

    def post_choose(self, body):
        ref.choose(body["id"], int(body["v"]), int(body["candidato"]))
        return {"ok": True}

    def post_regenerate(self, body):
        graph = ref.nodos()
        ids = [str(item) for item in body.get("ids") or [] if str(item) in graph]

        # Si no hay ids especificos, o si el usuario quiere regenerar el storyboard,
        # buscamos todo lo que este rechazado o desactualizado en el proyecto
        if not ids or body.get("todo") or "storyboard" in body.get("etiqueta", "").lower():
            pendientes = [node_id for node_id in graph if ref.estado(node_id, graph, universo.load())[0] in ("rechazado", "desactualizado")]
            ids = ids + pendientes
            label = body.get("etiqueta", "Lote automatico de regeneracion")
        else:
            label = body.get("etiqueta", f"Regenerar {len(ids)} nodos")

        if not ids:
            raise ValueError("ningun nodo conocido o pendiente para regenerar")

        # En lugar de intentar lanzar el trabajador inmediatamente y esperar,
        # creamos un lote formal en la cola y lanzamos el trabajador en background.
        # Esto permite que el usuario siga usando la web mientras la cola avanza.
        res = start_queue(ids, label=label[:80])
        return {"ok": True, "lote": res["lote"], "posicion": res["posicion"], "pendientes": len(ids)}

    def post_settings(self, body):
        values = {key: body["ajustes"][key] for key in ref.DEFAULT_SETTINGS if key in body.get("ajustes", {})}
        current = ref.read_json(ref.SETTINGS, {}) or {}
        current.update(values)
        ref.write_json(ref.SETTINGS, current)
        return {"ok": True, "ajustes": ref.settings()}

    def post_project(self, body):
        fields = ("titulo", "logline", "genero", "formato", "tono", "concepto", "tema", "tesis")
        intent = ("titulo_trabajo", "formato_duracion", "etapa", "logline", "tema_tesis", "experiencia", "tono_genero",
                  "punto_de_vista", "publico", "referencias", "restricciones", "decisiones_cerradas", "preocupacion")

        def change(saved):
            premise = saved.setdefault("premisa", {})
            premise.update({key: str(body[key])[:4000] for key in fields if key in body})
            if "idea" in body:
                saved["idea"] = str(body["idea"])[:8000]
            if isinstance(body.get("intencion"), dict):
                saved.setdefault("intencion", {}).update(
                    {key: str(value)[:2000] for key, value in body["intencion"].items() if key in intent})
        save_overlay("proyecto.json", change)
        return {"ok": True}

    def post_active(self, body):
        if not sf.entry(str(body["id"])):
            raise ValueError("proyecto desconocido")
        if (ref.STORE / "cola.lock").is_file():
            raise ValueError("hay una cola corriendo en este proyecto: espera a que termine")
        sf.activar(str(body["id"]))
        return {"ok": True, "activo": sf.STATE["id"]}

    def post_save_project(self, body):
        target, project_id = sf.guardar(str(body["carpeta"]), body.get("nombre"))
        return {"ok": True, "carpeta": str(target), "id": project_id}

    def post_load_project(self, body):
        return {"ok": True, "activo": sf.cargar(str(body["carpeta"]))}

    def post_new_project(self, body):
        return {"ok": True, "activo": sf.nuevo(str(body["nombre"])[:80], str(body.get("idea", ""))[:8000],
                                               body.get("carpeta") or None)}

    def post_open_folder(self, body):
        """Abre en el Explorador una carpeta del proyecto (solo las de su estructura)."""
        folder = sf.folder_for(str(body["clave"]))
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))   # noqa: S606 - ruta validada contra la estructura del proyecto
        return {"ok": True, "ruta": str(folder)}

    def post_import_df(self, body):
        import importar_df
        source = Path(str(body["carpeta"])).resolve()
        if not source.is_relative_to(Path(r"C:\canal starlight rebelion\projects").resolve()):
            raise ValueError("solo proyectos de C:\\canal starlight rebelion\\projects")
        return {"ok": True, **importar_df.importar(source)}

    def post_config(self, body):
        allowed = {"ollama_modelo": str, "num_ctx": int, "comfy_url": str, "bloom": str, "negros": str,
                   "estilo_guion": str}
        values = {key: kind(body["config"][key]) if body["config"][key] is not None else None
                  for key, kind in allowed.items() if key in (body.get("config") or {})}
        if values.get("bloom") and values["bloom"] not in postproceso.BLOOMS:
            raise ValueError("bloom desconocido")
        if values.get("negros") and values["negros"] not in postproceso.BLACKS:
            raise ValueError("negros desconocido")
        if values.get("comfy_url") and not values["comfy_url"].startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("ComfyUI tiene que ser local")
        sf.save_project(lambda data: data.setdefault("config", {}).update(values))
        sf.activar(sf.STATE["id"])
        if body.get("ajustes"):
            self.post_settings({"ajustes": body["ajustes"]})
        return {"ok": True, "config": sf.config()}

    def post_exportar_timeline(self, body):
        """Exportación procedimental: recorre el timeline y lanza la generación de todo lo necesario."""
        orden = body.get("orden", [])
        if not orden:
            raise ValueError("no se proporcionó un orden de clips")

        graph = ref.nodos()
        data = universo.load()
        ids_a_generar = []

        # Recorremos el timeline para identificar qué falta o está desactualizado
        for semilla in orden:
            nodo_toma = f"toma/{semilla}"
            if nodo_toma in graph:
                status, _ = ref.estado(nodo_toma, graph, data)
                if status in ("rechazado", "desactualizado", "pendiente"):
                    ids_a_generar.append(nodo_toma)

                    # Dependencias: si la toma falla, es probable que falte el vestuario o el lugar
                    # Agregamos los nodos dependientes para que se generen en el mismo lote
                    cast = universo.frozen().get(str(semilla), {})
                    pid = cast.get("id")
                    lid = cast.get("lugar_id")

                    if pid:
                        v_node = f"vestuario/{pid}"
                        if v_node in graph and ref.estado(v_node, graph, data)[0] != "aprobado":
                            ids_a_generar.append(v_node)
                    if lid:
                        l_node = f"lugar/{lid}"
                        if l_node in graph and ref.estado(l_node, graph, data)[0] != "aprobado":
                            ids_a_generar.append(l_node)

        # Eliminar duplicados manteniendo el orden
        final_ids = []
        for i in ids_a_generar:
            if i not in final_ids: final_ids.append(i)

        if not final_ids:
            return {"ok": True, "total": 0, "mensaje": "Todo el timeline está aprobado"}

        # Lanzamos como un lote de "Producción" (Prioridad alta)
        res = start_queue(final_ids, label=f"Producción Procedimental ({len(final_ids)} nodos)")
        return {"ok": True, "total": len(final_ids), "lote": res["lote"]}

    def post_scene(self, body):
        seed = int(body["semilla"])
        if seed not in ref.song_seeds():
            raise ValueError("tema desconocido")
        if "sinopsis" in body:
            save_overlay("guion.json", lambda saved: saved.setdefault("escenas", {}).setdefault(str(seed), {})
                         .update(sinopsis=str(body["sinopsis"])[:2000]))
        changes = {key: body[key] for key in ("id", "lugar_id", "gesto", "objeto") if key in body}
        if "gesto" in changes:
            changes["gesto"] = str(changes["gesto"])[:300]
        if changes:
            universo.set_frozen(seed, **changes)
        graph = ref.nodos()
        return {"ok": True, "estado": ref.estado(f"toma/{seed}", graph)[0] if f"toma/{seed}" in graph else None}

    def post_text(self, body):
        data = universo.load()
        kind, item_id, field = body["tipo"], body["id"], body["campo"]
        value = str(body["valor"])[:3000]
        if kind == "personaje" and item_id in data["personajes"]:
            if field == "objetos":
                values = list(data["personajes"][item_id]["objetos"])
                values[int(body["indice"])] = value
                value = values
            elif field not in PERSON_FIELDS:
                raise ValueError("campo no editable")
        elif kind == "lugar" and item_id in data["locaciones"]:
            if field not in PLACE_FIELDS:
                raise ValueError("campo no editable")
            if field == "utileria":
                value = [line.strip(" -•") for line in value.splitlines() if line.strip(" -•")][:12]
            problems = universo.place_problems(value) if field != "nombre" else []
            if problems:
                raise ValueError("un lugar se describe vacío: sacá personas y acciones (" + ", ".join(problems) + ")")
        else:
            raise ValueError("no existe")
        universo.update(kind, item_id, field, value)
        return {"ok": True}

    def post_sheet(self, body):
        pid = str(body["personaje"])
        if f"retrato/{pid}" not in ref.nodos():
            raise ValueError("personaje desconocido")
        if not ref.approved_hash(f"retrato/{pid}"):
            raise ValueError("primero aproba el retrato")
        ids = ref.pedir_ficha(pid)
        return {"ok": True, "ids": ids,
                "cola": start_queue(ids, label=f"ficha completa de {pid}") if body.get("lanzar", True) else False}

    def _plan_folder(self, body):
        if body.get("escena") and not str(body["escena"]).startswith("t"):
            guion_sf.find_scene(guion_sf.load(project_dir()), str(body["escena"]))   # la escena tiene que existir
            return ref.plan_folder(str(body["escena"]))
        seed = int(body.get("semilla") or str(body.get("escena", "t0"))[1:])
        folder = ref.song_folder(seed)
        if not folder:
            raise ValueError("tema desconocido")
        return folder

    def post_technical(self, body):
        folder = self._plan_folder(body)
        plan = valid_plan(body["planta"])
        fixed = dc.corregir_eje(plan)
        if body.get("guardar", True):
            dc.save(folder, plan)
        return {"ok": True, "planta": plan, "corregidas": fixed, "puesta": dc.staging(plan),
                "movimientos": [dc.movimiento(plan, shot) for shot in plan["planos"]]}

    def post_previz(self, body):
        """Cuadro del previz (inicio o fin de un plano) que el navegador dibujo: referencia de composicion."""
        folder = self._plan_folder(body)
        shot = re.sub(r"[^a-z0-9]", "", str(body["plano"]).lower())[:20]
        moment = body["momento"] if body["momento"] in ("ini", "fin") else None
        raw = base64.b64decode(str(body["datos"]).split(",", 1)[-1], validate=True)
        if not shot or not moment or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("previz invalido")
        target = folder / "toma" / "previz" / f"{shot}_{moment}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return {"ok": True, "url": image_url(target)}

    def post_clip(self, body):
        node_id = str(body["id"])
        graph = ref.nodos()
        if node_id not in graph or graph[node_id]["tipo"] != "clip":
            raise ValueError("clip desconocido")
        ref.pedir_clip(node_id)
        return {"ok": True, "cola": start_queue([node_id], label=f"clip {node_id}") if body.get("lanzar", True) else False,
                "plan": ref.planificar([node_id], graph)}

    def post_edit(self, body):
        seeds = ref.song_seeds()

        def change(saved):
            if "orden" in body:
                saved["orden"] = [int(seed) for seed in body["orden"] if int(seed) in seeds]
            for seed, clip in (body.get("clips") or {}).items():
                if int(seed) in seeds:
                    saved.setdefault("clips", {})[str(int(seed))] = {"publicar": bool(clip.get("publicar")),
                                                                    "fecha": str(clip.get("fecha", ""))[:10]}
        save_overlay("edicion.json", change)
        return {"ok": True}

    def post_generate(self, body):
        kind = body["tipo"]
        if kind == "tema":
            seed = int(body["semilla"])
            if seed not in ref.song_seeds():
                raise ValueError("tema desconocido")
            request = {"tipo": "tema", "semilla": seed}
        elif kind == "estructura":
            request = {"tipo": "estructura"}
        elif kind in ("premisa", "secuencias"):
            request = {"tipo": kind}
        elif kind == "revision":
            request = {"tipo": "revision", "etapa": self._stage(body)}
        elif kind == "escenas":
            target = str(body["objetivo"])
            if target not in [item["id"] for item in guion_sf.load(project_dir())["secuencias"]]:
                raise ValueError("secuencia desconocida")
            request = {"tipo": kind, "objetivo": target}
        elif kind == "planos":
            target = str(body["objetivo"])
            guion_sf.find_scene(guion_sf.load(project_dir()), target)
            request = {"tipo": kind, "objetivo": target}
        else:
            raise ValueError("pedido desconocido")
        cola.add_request(request)
        return {"ok": True, "cola": start_queue([], only_ollama=True, label=f"Ollama: {kind}")}

    def _stage(self, body):
        stage = str(body.get("etapa", ""))
        if stage not in revisores_sf.STAGES:
            raise ValueError("etapa sin revisores")
        return stage

    def post_script_doc(self, body):
        if "fountain" in body:
            structure = guion_sf.from_fountain(str(body["fountain"])[:400000], guion_sf.load(project_dir()))
        else:
            structure = guion_sf.clean(body["estructura"])
        saved = save_script(structure)
        return {"ok": True, "version": saved["version"]}

    def post_script_proposal(self, body):
        key = str(body["clave"])
        if body["accion"] == "aceptar":
            guion_sf.accept(project_dir(), key, sf.save_project)
        elif body["accion"] == "descartar":
            guion_sf.discard(project_dir(), key)
        else:
            raise ValueError("accion desconocida")
        return {"ok": True}

    def post_script(self, body):
        seeds = ref.song_seeds()
        acts = [{"titulo": str(act["titulo"])[:120],
                 "secuencias": [{"titulo": str(seq["titulo"])[:120], "sinopsis": str(seq.get("sinopsis", ""))[:1000],
                                 "temas": [int(seed) for seed in seq.get("temas", []) if int(seed) in seeds]}
                                for seq in act.get("secuencias", [])]} for act in body["actos"]]
        save_overlay("guion.json", lambda saved: saved.update(actos=acts, premisa=str(body.get("premisa", ""))[:2000]))
        return {"ok": True}

    def post_proposal(self, body):
        proposal = ref.read_json(cola.STRUCTURE_PROPOSAL)
        if not proposal:
            raise ValueError("no hay propuesta")
        if body["accion"] not in ("aceptar", "descartar"):
            raise ValueError("accion desconocida")
        if body["accion"] == "aceptar":
            self.post_script({"actos": proposal["actos"], "premisa": proposal.get("premisa", "")})
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        cola.STRUCTURE_PROPOSAL.replace(cola.STRUCTURE_PROPOSAL.with_name(f"propuesta_{body['accion']}_{stamp}.json"))
        return {"ok": True}


def serve(port=8765, browser=True, project=None):
    sf.ensure_registry()
    if project or not sf.STATE["id"]:
        sf.activar(project or sf.EXAMPLE_1)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"StoryForge en {url}", flush=True)
    if browser:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", type=int, default=8765)
    parser.add_argument("--sin-navegador", action="store_true")
    parser.add_argument("--proyecto", help="id del proyecto a abrir (por defecto Ejemplo 1)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    serve(args.puerto, not args.sin_navegador, args.proyecto).serve_forever()


if __name__ == "__main__":
    main()
