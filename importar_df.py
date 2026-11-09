"""Importa un proyecto de Doble Fondo (projects/DF_xxx) a una carpeta de StoryForge, SIN modificar el original.

  python importar_df.py "C:\\canal starlight rebelion\\projects\\DF_005" [--destino storyforge\\proyectos\\df_005]

  brief.json        -> proyecto.json (premisa) + musica.json (bpm, tonalidad, estilo, letra)
  storyboard.json   -> guion.json: cada seccion del tema (Intro, Verse 1, Chorus...) es una secuencia con una escena,
                       y cada toma es un plano (tipo segun el prompt, que se ve = prompt, accion = accion animada)
                     -> la imagen final (o el boceto) de cada toma entra como version "legado" aprobada del plano de
                       inicio, y su prompt (ya en ingles) queda como prompt del plano: nada se regenera solo
  decoupage.json    -> la planta de cada escena, si el proyecto la tiene
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import decoupage_sf as dc
import guion_sf
import proyecto_sf as sf
import referencias as ref

PORTADA = "Portada"


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def importar(source, target=None, register=True):
    source = Path(source).resolve()
    brief = read(source / "brief.json")
    board = read(source / "storyboard.json")
    if not brief or not board:
        raise ValueError(f"{source} no parece un proyecto de Doble Fondo (falta brief.json o storyboard.json)")
    project_id = f"df_{source.name.lower().replace('df_', '')}"
    target = Path(target or sf.PROJECTS / project_id).resolve()
    # Windows no distingue mayusculas: "df_005" y "DF_005" son la misma carpeta. Nunca se escribe en el original.
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("El destino no puede ser la carpeta de Doble Fondo (ni estar adentro): elegí otra")
    if (target / "proyecto.json").exists():
        raise ValueError(f"Ya existe {target}: borrala o elegí otro destino")
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    ref.write_json(target / "proyecto.json", {
        "id": project_id, "nombre": f"Doble Fondo · {brief.get('titulo', source.name)}", "idea": brief.get("hipotesis", ""),
        "premisa": {"titulo": brief.get("titulo", ""), "genero": brief.get("tipo", ""), "formato": "videoclip",
                    "concepto": brief.get("descripcion", "")},
        "config": dict(sf.DEFAULT_CONFIG), "etapa": "storyboard", "importado_de": str(source), "creado": stamp})
    ref.write_json(target / "musica.json", {key: brief.get(key) for key in
                                            ("titulo", "bpm", "tonalidad", "estilo_musical", "duracion", "letra", "audio")})
    ref.write_json(target / "universo.json", {"_nota": f"Importado de {source}", "reglas": "", "personajes": {},
                                              "locaciones": {}, "canon": []})
    sections, order = {}, []
    for shot in board.get("tomas", []):
        section = shot.get("seccion") or "Sin seccion"
        if section == PORTADA:
            continue
        if section not in sections:
            sections[section] = []
            order.append(section)
        sections[section].append(shot)
    sequences, images = [], []
    for number, section in enumerate(order, 1):
        scene_id = f"e{number}"
        shots = []
        for shot in sections[section]:
            shot_id = "p" + "".join(char for char in shot["id"] if char.isalnum()).lower()
            shots.append({"id": shot_id, "tipo": dc.shot_type(shot.get("prompt", "")), "que_se_ve": shot.get("prompt", ""),
                          "accion": shot.get("accion_animada", ""), "duracion": round(2.5 * float(shot.get("peso", 1)), 1),
                          "estado": "legado"})
            image = source / (shot.get("final") or shot.get("archivo") or "")
            if image.is_file():
                images.append((scene_id, shot_id, image, shot.get("prompt", "")))
        sequences.append({"id": f"s{number}", "titulo": section, "sinopsis": "", "escenas": [
            {"id": scene_id, "int_ext": "INT.", "lugar": section.upper(), "momento": "NOCHE",
             "accion": " ".join(item.get("accion_animada", "") for item in sections[section])[:1500],
             "dialogos": [], "elenco": [], "estado": "guardada", "planos": shots}]})
    guion_sf.save(target, {"premisa": brief.get("hipotesis", ""), "secuencias": sequences}, "importado")
    decoupage = read(source / "decoupage.json", {}) or {}
    for scene_id, plan in decoupage.items():
        if isinstance(plan, dict) and plan.get("planos"):
            dc.save(target / "direccion" / scene_id, plan)
    if register:
        sf.register(project_id, f"Doble Fondo · {brief.get('titulo', source.name)}", target,
                    note=f"importado de {source.name} (sin tocar el original)")
    previous = sf.STATE["id"]
    sf.activar(project_id) if register else None
    graph = ref.nodos()
    imported = 0
    for scene_id, shot_id, image, prompt in images:
        node_id = f"plano/{scene_id}__{shot_id}_ini"
        if node_id not in graph:
            continue
        scene = next(item for item in guion_sf.scenes(guion_sf.load(target)) if item["id"] == scene_id)
        shot = next(item for item in scene["planos"] if item["id"] == shot_id)
        ref.write_json(ref.STORE / "plano" / f"{scene_id}__{shot_id}_prompt.json",
                       {"prompt": prompt, "fuente": ref.sha_json({"accion": scene.get("accion"), "plano": {
                           key: shot.get(key) for key in ("tipo", "que_se_ve", "accion", "movimiento")}})})
        version = ref.record_version(node_id, [image], {"legado": True}, "legado", "doble fondo", {"legado": True})
        ref.review_image(node_id, version["candidatos"][0]["hash"], "aprobado", "imagen de Doble Fondo", "legado")
        imported += 1
    if register and previous:
        sf.activar(previous)
    return {"carpeta": str(target), "id": project_id, "secuencias": len(sequences),
            "planos": sum(len(sequence["escenas"][0]["planos"]) for sequence in sequences), "imagenes": imported}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("origen")
    parser.add_argument("--destino")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sf.ensure_registry()
    print(json.dumps(importar(args.origen, args.destino), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
