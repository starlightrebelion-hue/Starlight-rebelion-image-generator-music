"""Revisores del proyecto (de C:\\Pixel-set\\agentes): cuatro revisores + un Coordinador que arma la hoja de ruta.

  Sociologia, Estructuras Narrativas, Literatura de las Artes Combinadas, Estetica y Teoria de los Medios
  -> cada uno devuelve un informe en el formato comun (agentes/revisores/formato_informe.md)
  -> el Coordinador los unifica en una hoja de ruta (maximo 7 acciones, decisiones para el director).

Que revisores se activan en cada etapa sale de las reglas del Coordinador. Todo lo leen contra la declaracion de
intencion del proyecto (etapa Premisa). Los informes quedan en <proyecto>/revisiones/<etapa>/ con su version; el
seguimiento (notas resueltas, abiertas o rebatidas) lo escribe el usuario y entra en la ronda siguiente.
Si Ollama falla en un revisor, ese informe falta (y se dice): nunca se inventa.
"""
import datetime
import json
import re
from pathlib import Path

import equipo_imagen as equipo
import guion_sf
import referencias as ref

AGENTS = Path(__file__).resolve().parent / "agentes" / "revisores"
REVIEWERS = {"sociologia": "Sociología", "estructuras_narrativas": "Estructuras Narrativas",
             "artes_combinadas": "Literatura de las Artes Combinadas", "estetica": "Estética y Teoría de los Medios"}
# reglas del Coordinador: que revisores activar segun la etapa
STAGES = {"idea": ["sociologia", "estructuras_narrativas", "estetica"],
          "premisa": ["sociologia", "estructuras_narrativas", "estetica"],
          "guion": list(REVIEWERS),
          "direccion": ["sociologia", "estetica", "estructuras_narrativas"],
          "storyboard": ["sociologia", "estetica", "estructuras_narrativas"],
          "edicion": list(REVIEWERS)}
STAGE_NAMES = {"idea": "idea o sinopsis", "premisa": "idea o sinopsis", "guion": "tratamiento o guion",
               "direccion": "puesta en escena y plan de fotografia", "storyboard": "puesta en escena y plan de fotografia",
               "edicion": "montaje y corte final"}


def folder(project_dir, stage):
    return Path(project_dir) / "revisiones" / stage


def intention(project):
    """La declaracion de intencion en el formato del documento."""
    premise = {**project, **(project.get("premisa") or {})}
    intent = project.get("intencion") or {}
    lines = ["# DECLARACIÓN DE INTENCIÓN",
             f"- Título de trabajo: {premise.get('titulo', '')}",
             f"- Formato y duración: {premise.get('formato', '')}",
             f"- Logline: {premise.get('logline', '')}",
             f"- Tema y tesis: {premise.get('tema', '')}",
             f"- Experiencia buscada: {intent.get('experiencia', '')}",
             f"- Tono y género: {premise.get('tono', '')} / {premise.get('genero', '')}",
             f"- Punto de vista: {intent.get('punto_de_vista', '')}",
             f"- Público imaginado: {intent.get('publico', '')}",
             f"- Referencias: {intent.get('referencias', '')}",
             f"- Restricciones reales: {intent.get('restricciones', '')}",
             f"- Decisiones cerradas: {intent.get('decisiones_cerradas', '')}",
             f"- Lo que más me preocupa: {intent.get('preocupacion', '')}"]
    return "\n".join(lines)


def material(project_dir, project, stage):
    """Lo que se revisa en cada etapa (texto)."""
    structure = guion_sf.load(project_dir)
    if stage in ("idea", "premisa"):
        return f"IDEA: {project.get('idea', '')}\nPREMISA: {json.dumps(project.get('premisa') or {}, ensure_ascii=False)}"
    if stage == "guion":
        return guion_sf.to_fountain(structure, (project.get("premisa") or {}).get("titulo", "Guion"))
    if stage in ("direccion", "storyboard"):
        lines = []
        for scene in guion_sf.scenes(structure):
            lines.append(f"ESCENA {scene['id']}: {scene.get('int_ext', '')} {scene.get('lugar', '')} - "
                         f"{scene.get('momento', '')}. {scene.get('accion', '')}")
            for shot in scene.get("planos", []):
                lines.append(f"  PLANO {shot.get('id')} {shot.get('tipo')}: {shot.get('que_se_ve', '')} — "
                             f"{shot.get('accion', '')}")
        return "\n".join(lines)
    order = (ref.read_json(Path(project_dir) / "edicion.json", {}) or {}).get("orden") or ref.song_seeds()
    return "ORDEN DE MONTAJE: " + ", ".join(str(seed) for seed in order)


def versions(project_dir, stage):
    return sorted({int(match.group(1)) for path in folder(project_dir, stage).glob("hoja_de_ruta_v*.md")
                   for match in [re.search(r"_v(\d+)\.md$", path.name)] if match})


def follow_up(project_dir, stage):
    path = folder(project_dir, stage) / "seguimiento.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def save_follow_up(project_dir, stage, text):
    path = folder(project_dir, stage) / "seguimiento.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ask_markdown(prompt, model, seed, ask):
    schema = {"type": "object", "properties": {"informe": {"type": "string"}}, "required": ["informe"]}
    answer = (ask or equipo.ask)(prompt, schema, model, seed)
    text = str(answer.get("informe", "")).strip()
    if len(text) < 80:
        raise ValueError("informe vacio")
    return text


def review(project_dir, project, stage, model, ask=None, log=print):
    """Una ronda de revision de la etapa: informes de los revisores activos + hoja de ruta del Coordinador.
    Devuelve el numero de version o None si ningun revisor pudo responder."""
    if stage not in STAGES:
        raise ValueError(f"etapa sin revisores: {stage}")
    out = folder(project_dir, stage)
    out.mkdir(parents=True, exist_ok=True)
    number = (versions(project_dir, stage) or [0])[-1] + 1
    common = (AGENTS / "formato_informe.md").read_text(encoding="utf-8")
    previous = out / f"hoja_de_ruta_v{number - 1}.md"
    context = (f"{intention(project)}\n\nETAPA: {STAGE_NAMES[stage]} (versión {number})\n\n"
               f"MATERIAL:\n{material(project_dir, project, stage)[:12000]}\n\n"
               f"HOJA DE RUTA ANTERIOR:\n{previous.read_text(encoding='utf-8')[:3000] if previous.is_file() else '(primera ronda)'}\n\n"
               f"SEGUIMIENTO DEL AUTOR:\n{follow_up(project_dir, stage) or '(sin notas)'}")
    reports = {}
    for index, role in enumerate(STAGES[stage]):
        method = (AGENTS / f"{role}.md").read_text(encoding="utf-8")
        prompt = (f"{method}\n\n{common}\n\n{context}\n\nEscribí tu informe en markdown con el formato común "
                  f"(destinatarios: Guionista, Director, Montajista, Fotografía). Devolvé JSON {{\"informe\": \"...\"}}.")
        try:
            reports[role] = _ask_markdown(prompt, model, 31 + index, ask)
            (out / f"{role}_v{number}.md").write_text(reports[role], encoding="utf-8")
            log(f"revision {stage}: {REVIEWERS[role]} listo")
        except Exception as error:  # noqa: BLE001 - ese informe falta; se dice en la hoja de ruta
            log(f"revision {stage}: {REVIEWERS[role]} no respondio ({error})")
    if not reports:
        return None
    method = (AGENTS / "coordinador.md").read_text(encoding="utf-8")
    missing = [REVIEWERS[role] for role in STAGES[stage] if role not in reports]
    joined = "\n\n".join(f"=== INFORME DE {REVIEWERS[role].upper()} ===\n{text}" for role, text in reports.items())
    prompt = (f"{method}\n\n{context}\n\n{joined}\n\n"
              f"{'FALTAN LOS INFORMES DE: ' + ', '.join(missing) + ' (decilo).' if missing else ''}\n"
              "Escribí la hoja de ruta en markdown con el formato de salida. Devolvé JSON {\"informe\": \"...\"}.")
    try:
        roadmap = _ask_markdown(prompt, model, 41, ask)
    except Exception as error:  # noqa: BLE001
        log(f"revision {stage}: el Coordinador no respondio ({error}); quedan los informes sueltos")
        roadmap = "# HOJA DE RUTA\n\nEl Coordinador no respondió: leé los informes de cada revisor."
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    (out / f"hoja_de_ruta_v{number}.md").write_text(f"<!-- {stamp} -->\n{roadmap}", encoding="utf-8")
    return number


def view(project_dir, stage):
    """Lo que muestra la solapa Revision: versiones, hoja de ruta e informes de la ultima (o la pedida)."""
    out = folder(project_dir, stage)
    numbers = versions(project_dir, stage)
    number = numbers[-1] if numbers else None
    reports = {}
    if number:
        for role in REVIEWERS:
            path = out / f"{role}_v{number}.md"
            if path.is_file():
                reports[role] = path.read_text(encoding="utf-8")
    roadmap = (out / f"hoja_de_ruta_v{number}.md").read_text(encoding="utf-8") if number else ""
    return {"etapa": stage, "activos": [{"id": role, "nombre": REVIEWERS[role]} for role in STAGES.get(stage, [])],
            "versiones": numbers, "version": number, "hoja_de_ruta": roadmap,
            "informes": {REVIEWERS[role]: text for role, text in reports.items()},
            "seguimiento": follow_up(project_dir, stage), "etapas": list(STAGES)}
