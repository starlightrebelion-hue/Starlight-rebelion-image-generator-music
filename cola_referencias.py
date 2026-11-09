"""Cola de trabajos de referencias: Ollama y ComfyUI en fases separadas, agrupado por modelo y retomable.

  python cola_referencias.py plan [ids...]      que se haria (sin generar nada)
  python cola_referencias.py correr [ids...]    genera lo pendiente, desactualizado o rechazado (y su cascada)
      --limite N    como mucho N imagenes (para probar)
      --solo-ollama solo los pedidos de texto de StoryForge (pedidos_ollama.json), sin prender ComfyUI

Pedidos de texto (los encola StoryForge en pedidos_ollama.json, se hacen en la fase Ollama):
  {"tipo": "tema", "semilla": N}         rehace concepto y departamentos del tema (ficha_tema, sin imagen)
  {"tipo": "estructura"}                 el guionista propone actos y secuencias con los temas (queda como propuesta)

Orden: 1) Ollama: reescribe las descripciones rechazadas con nota y rehace los departamentos pedidos de las tomas;
descarga el modelo y confirma que no quedo nada cargado. 2) ComfyUI por modelo: Z-Image (retratos, lugares,
objetos), Kontext (poses, vestuario, composicion de tomas), Z-Image (estilo de tomas), ffmpeg (hojas).
Lo que depende de algo recien generado queda "esperando" la aprobacion en StoryForge: no se gasta GPU en algo que
capaz se rechaza. Si Ollama falla, el trabajo queda en fallo (nunca se inventa nada). Un solo runner a la vez
(cola.lock); el archivo PAUSA_REFERENCIAS lo frena entre trabajos.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import equipo_imagen as equipo
import fondo_comfy as comfy
import generar_referencias as gen
import referencias as ref
import universo

LOCK = ref.STORE / "cola.lock"
LOG = ref.STORE / "registro.log"
STATUS = ref.STORE / "cola.json"
PAUSE = ref.ROOT / "PAUSA_REFERENCIAS"
OLLAMA_PS = "http://127.0.0.1:11434/api/ps"
DEFAULT_MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"
# que campo del universo corrige una nota de rechazo de cada tipo
STRUCTURE_PROPOSAL = ref.ROOT / "storyforge" / "proyectos" / "ejemplo_1" / "guion_propuesta.json"
FIELD_OF = {"retrato": ("personaje", "aspecto"), "vestuario": ("personaje", "vestuario"), "lugar": ("lugar", "prompt"),
            "objeto": ("personaje", "objetos")}


def log(message):
    ref.STORE.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}"
    with open(LOG, "a", encoding="utf-8") as output:
        output.write(line + "\n")
    print(line, flush=True)


def ollama_loaded():
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=5) as response:
            return bool(json.loads(response.read()).get("models"))
    except OSError:
        return False


def acquire():
    if LOCK.exists():
        try:
            pid = int(json.loads(LOCK.read_text(encoding="utf-8"))["pid"])
            alive = str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
                                               text=True).stdout
        except (ValueError, KeyError, json.JSONDecodeError):
            alive = False
        if alive:
            raise SystemExit("Ya hay una cola corriendo (cola.lock).")
    ref.write_json(LOCK, {"pid": os.getpid(), "inicio": datetime.datetime.now().isoformat(timespec="seconds")})


def release():
    LOCK.unlink(missing_ok=True)


def save_status(jobs, current=None):
    ref.write_json(STATUS, {"actual": current, "trabajos": jobs,
                            "actualizado": datetime.datetime.now().isoformat(timespec="seconds")})


def latest_rejection(node_id):
    """La nota y la accion del rechazo de la imagen actual, o (None, None)."""
    _, candidate = ref.chosen_image(node_id)
    if not candidate:
        return None, None
    verdict = ref.revision(node_id)["imagenes"].get(candidate["hash"], {})
    return (verdict.get("nota"), verdict.get("accion")) if verdict.get("estado") == "rechazado" else (None, None)


def rewrite_description(node_id, note, model):
    """Ollama reescribe el texto del universo segun la nota (agentes/referencias.md). None si no pudo."""
    graph = ref.nodos()
    node = graph[node_id]
    kind = node["tipo"]
    group, field = FIELD_OF[kind]
    data = universo.load()
    item_id = node.get("personaje") if group == "personaje" else node["lugar"]
    item = data["personajes" if group == "personaje" else "locaciones"][item_id]
    current = item[field][node["indice"]] if kind == "objeto" else item[field]
    method = (ref.ROOT / "agentes" / "referencias.md").read_text(encoding="utf-8")
    schema = {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}
    prompt = (f"{method}\n\nTEXTO ACTUAL ({kind}): {current}\nNOTA DEL USUARIO: {note}\n"
              'Devolve JSON {"texto": ...} con el texto corregido, en ingles.')
    try:
        text = equipo.plain(equipo.ask(prompt, schema, model, 7).get("texto", ""))
    except Exception as error:  # noqa: BLE001 - cualquier falla de Ollama deja el trabajo en fallo
        log(f"{node_id}: Ollama no respondio ({error})")
        return None
    problems = equipo.check_text(kind, text, 8, 160)
    if kind == "lugar":
        problems += [f"el lugar tiene personas o acciones: {', '.join(universo.place_problems(text))}"] \
            if universo.place_problems(text) else []
    if problems:
        log(f"{node_id}: la reescritura no paso la revision ({'; '.join(problems)})")
        return None
    if kind == "objeto":
        values = list(item[field])
        values[node["indice"]] = text
        text = values
    universo.update(group, item_id, field, text)
    return text


def requests_file():
    return ref.STORE / "pedidos_ollama.json"


def add_request(request):
    """Encola un pedido de texto (no repite uno igual que todavia esta pendiente)."""
    pending = ref.read_json(requests_file(), []) or []
    if not any(item["pedido"] == request and item["estado"] == "pendiente" for item in pending):
        pending.append({"pedido": request, "estado": "pendiente",
                        "fecha": datetime.datetime.now().isoformat(timespec="seconds")})
        ref.write_json(requests_file(), pending)
    return pending


def propose_structure(model):
    """El guionista (agentes/guionista_storyforge.md) agrupa los temas en actos y secuencias. Solo ids que existen;
    si Ollama falla o inventa temas, no se guarda nada."""
    data = universo.load()
    seeds = ref.song_seeds()
    frozen = universo.frozen()
    songs = []
    for seed in seeds:
        folder = ref.song_folder(seed)
        writer = ref.read_json(folder / "equipo" / "escritor.json", {}) or {}
        cast = frozen.get(str(seed), {})
        songs.append({"tema": seed, "titulo": folder.name.rsplit(" ", 1)[0], "personaje": cast.get("id"),
                      "lugar": cast.get("lugar_id"), "sinopsis": writer.get("logline") or writer.get("escena", "")})
    method = (ref.ROOT / "agentes" / "guionista_storyforge.md").read_text(encoding="utf-8")
    people = {pid: f"{person['nombre']}: {person.get('deseo', '')}" for pid, person in data["personajes"].items()}
    schema = {"type": "object", "properties": {"premisa": {"type": "string"}, "actos": {"type": "array", "items": {
        "type": "object", "properties": {"titulo": {"type": "string"}, "secuencias": {"type": "array", "items": {
            "type": "object", "properties": {"titulo": {"type": "string"}, "sinopsis": {"type": "string"},
                                             "temas": {"type": "array", "items": {"type": "integer"}}},
            "required": ["titulo", "sinopsis", "temas"]}}}, "required": ["titulo", "secuencias"]}}},
        "required": ["premisa", "actos"]}
    prompt = (f"{method}\n\nPERSONAJES: {json.dumps(people, ensure_ascii=False)}\n"
              f"TEMAS: {json.dumps(songs, ensure_ascii=False)}\nDevolve el JSON pedido.")
    try:
        answer = equipo.ask(prompt, schema, model, 11)
    except Exception as error:  # noqa: BLE001 - sin Ollama no hay propuesta (nunca se inventa)
        log(f"estructura: Ollama no respondio ({error})")
        return None
    used = [seed for act in answer.get("actos", []) for sequence in act.get("secuencias", []) for seed in sequence["temas"]]
    if not used or any(seed not in seeds for seed in used) or len(used) != len(set(used)):
        log("estructura: la propuesta tiene temas que no existen o repetidos; no se guarda")
        return None
    answer["fecha"] = datetime.datetime.now().isoformat(timespec="seconds")
    answer["sin_ubicar"] = [seed for seed in seeds if seed not in used]
    ref.write_json(STRUCTURE_PROPOSAL, answer)
    return answer


def books_context(request):
    """Referencia de tono de los libros para el guionista ("" si no hay libros o no hay estilo elegido)."""
    try:
        import libros_sf
        return libros_sf.contexto_para(request["tipo"])
    except Exception:  # noqa: BLE001 - sin libros el guion se genera igual
        return ""


def text_requests(model):
    """Hace los pedidos de texto pendientes. Devuelve si uso Ollama."""
    import ficha_tema
    pending = ref.read_json(requests_file(), []) or []
    touched = False
    for item in pending:
        if item["estado"] != "pendiente":
            continue
        touched = True
        request = item["pedido"]
        try:
            if request["tipo"] == "tema":
                ok = ficha_tema.make(int(request["semilla"]), model, with_image=False)
            elif request["tipo"] == "estructura":
                ok = propose_structure(model)
            elif request["tipo"] == "revision":
                import proyecto_sf
                import revisores_sf
                ok = revisores_sf.review(STRUCTURE_PROPOSAL.parent, proyecto_sf.read_project(), request["etapa"],
                                         model, log=log)
            elif request["tipo"] in ("premisa", "secuencias", "escenas", "planos"):
                import guion_sf
                import proyecto_sf
                folder = STRUCTURE_PROPOSAL.parent   # carpeta del proyecto activo
                ok = guion_sf.generate(folder, proyecto_sf.read_project(), request["tipo"], request.get("objetivo"),
                                       model, books=books_context(request))
            else:
                ok = None
        except Exception as error:  # noqa: BLE001 - el pedido queda en fallo, sin inventar nada
            log(f"pedido {request}: fallo ({error!r})")
            ok = None
        item["estado"] = "hecho" if ok else "fallo"
        item["terminado"] = datetime.datetime.now().isoformat(timespec="seconds")
        log(f"pedido {request}: {item['estado']}")
        ref.write_json(requests_file(), pending)
    return touched


def english_prompts(jobs, model):
    """Los planos del guion se escriben en castellano: Ollama los pasa a un prompt de imagen en ingles antes de
    ComfyUI. Si no puede, ese plano (y su clip) queda en fallo."""
    touched, done = False, {}
    for job in jobs:
        kind = job["nodo"].split("/")[0]
        if kind not in ("plano", "clip") or job["motivo"] == "esperando":
            continue
        node = ref.nodos()[job["nodo"]]
        if node.get("semilla"):
            continue   # clip de un tema: usa el director del tema (ya en ingles)
        key = (node["escena"], node["plano"])
        if key not in done:
            scene, shot = gen._scene_and_shot(node)
            saved = ref.read_json(gen.english_prompt_path(*key))
            if saved and saved.get("fuente") == gen.english_source(scene, shot):
                done[key] = True
            else:
                touched = True
                try:
                    done[key] = bool(gen.plano_prompt(scene, shot, model))
                except Exception as error:  # noqa: BLE001 - sin Ollama no hay prompt (nunca se inventa)
                    log(f"{job['nodo']}: Ollama no respondio ({error})")
                    done[key] = False
        if not done[key]:
            job["ollama"] = "fallo"
    return touched


def ollama_phase(jobs, model):
    """Descripciones rechazadas con nota y departamentos pedidos para tomas. Al final descarga Ollama."""
    import ficha_tema
    touched = text_requests(model)
    for job in jobs:
        # PRIORIDAD: Si el nodo está rechazado, debe pasar por Ollama si hay una nota
        if job["motivo"] == "rechazado":
            note, action = latest_rejection(job["nodo"])
            if not note:
                continue

            kind = job["nodo"].split("/")[0]
            # Caso 1: Reescritura de descripción general (Personaje/Lugar/Objeto)
            if action == "descripcion" and kind in FIELD_OF:
                touched = True
                job["ollama"] = "hecho" if rewrite_description(job["nodo"], note, model) else "fallo"

            # Caso 2: Mejora de departamento para Toma (el director/fotógrafo pide cambios)
            elif action and action.startswith("rol:"):
                touched = True
                # Si es una toma, usamos ficha_tema.improve para ajustar el departamento específico
                if kind == "toma":
                    seed = int(job["nodo"].split("/")[1])
                    # El rol viene como "rol:fotografo", extraemos "fotografo"
                    rol_nombre = action[4:]
                    job["ollama"] = "hecho" if ficha_tema.improve(seed, {rol_nombre: note}, model) else "fallo"
                else:
                    log(f"{job['nodo']}: el rol {action} no aplica a tipo {kind}")
                    job["ollama"] = "fallo"

            log(f"{job['nodo']}: ollama {job.get('ollama', '-')}")

    touched = english_prompts(jobs, model) or touched
    if touched:
        equipo.unload(model)
    for _ in range(30):
        if not ollama_loaded():
            return
        equipo.unload(model)
    raise SystemExit("Ollama sigue con un modelo cargado: no se prende ComfyUI.")


def comfy_steps(jobs):
    """(modelo, nodo, paso) en el orden que minimiza los cambios de modelo."""
    steps = []
    for job in jobs:
        if job["motivo"] == "esperando" or job.get("ollama") == "fallo":
            continue
        kind = job["nodo"].split("/")[0]
        if kind in ("toma", "plano"):
            steps += [("kontext", job["nodo"], "compose"), ("zimage_toma", job["nodo"], "estilo")]
        else:
            steps.append((gen.MODEL_OF[kind], job["nodo"], None))
    rank = {"zimage": 0, "kontext": 1, "ffmpeg": 2, "zimage_toma": 3, "wan": 4}
    return sorted(steps, key=lambda step: (rank[step[0]], ref.ORDER.index(step[1].split("/")[0]), step[1]))


def correr(ids=None, limit=None, model=DEFAULT_MODEL, only_ollama=False, locked=False, progress=None):
    """Genera un lote. `locked`: lo llama el trabajador de la cola, que ya tiene el lock. `progress(hechos, total,
    actual)` informa el avance (para el Log)."""
    if not locked:
        acquire()
    process = None
    progress = progress or (lambda done, total, current: None)
    try:
        if only_ollama:
            save_status([], {"nodo": "pedidos de texto", "paso": "ollama"})
            if text_requests(model):   # sin ComfyUI no hace falta esperar a que Ollama quede vacio
                equipo.unload(model)
            save_status([])
            return []
        jobs = ref.planificar(ids or "pendientes")
        save_status(jobs)
        log(f"cola: {len(jobs)} trabajos ({sum(job['motivo'] == 'esperando' for job in jobs)} esperando aprobacion)")
        ollama_phase(jobs, model)
        steps = comfy_steps(jobs)
        progress(0, len(steps), None)
        if not steps:
            log("nada para generar")
            return jobs
        process = comfy.start(ref.STORE / "comfyui.log")
        current_model, done = None, 0
        for model_name, node_id, step in steps:
            if PAUSE.exists():
                log("pausa pedida: freno")
                break
            if limit is not None and done >= limit:
                break
            if model_name != current_model and model_name != "ffmpeg":
                if current_model:
                    comfy.free()
                current_model = model_name
            save_status(jobs, {"nodo": node_id, "paso": step, "modelo": model_name})
            progress(done, len(steps), f"{node_id}{' ' + step if step else ''}")
            result = "fallo"
            for attempt in (1, 2):
                try:
                    gen.make(node_id, step=step)
                    log(f"{node_id}{' ' + step if step else ''}: listo")
                    result = "listo"
                    break
                except Exception as error:  # noqa: BLE001 - se registra y se reintenta una vez
                    log(f"{node_id}: fallo intento {attempt} ({error!r})")
            for job in jobs:
                if job["nodo"] == node_id:
                    job["resultado"] = result if job.get("resultado") != "fallo" else "fallo"
            done += 1
            progress(done, len(steps), None)
        save_status(jobs)
        return jobs
    finally:
        if process:
            comfy.free()
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        if not locked:
            release()


# --- cola de lotes: cada pedido de StoryForge es un lote; un solo trabajador los hace en orden ---------------------
def batches_dir():
    return ref.STORE / "cola_pedidos"


def add_batch(ids, only_ollama=False, label=""):
    """Agrega un lote a la cola (un archivo por lote: StoryForge solo los crea o los cancela). Devuelve el lote."""
    folder = batches_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now()
    number = 1 + max((int(path.stem.split("_")[0]) for path in folder.glob("*.json") if path.stem.split("_")[0].isdigit()),
                     default=0)
    batch = {"lote": number, "ids": list(ids), "solo_ollama": bool(only_ollama), "etiqueta": label,
             "estado": "pendiente", "creado": stamp.isoformat(timespec="seconds"), "hechos": 0, "total": None,
             "actual": None, "resultado": None}
    ref.write_json(folder / f"{number:05d}.json", batch)
    return batch


def batches():
    return [ref.read_json(path) for path in sorted(batches_dir().glob("*.json"))] if batches_dir().is_dir() else []


def update_batch(number, **changes):
    path = batches_dir() / f"{number:05d}.json"
    batch = ref.read_json(path)
    if batch:
        batch.update(changes)
        ref.write_json(path, batch)
    return batch


def cancel_batch(number):
    batch = ref.read_json(batches_dir() / f"{number:05d}.json")
    if not batch or batch["estado"] != "pendiente":
        raise ValueError("solo se cancela un lote que todavia no empezo")
    return update_batch(number, estado="cancelado")


def clear_finished():
    for path in batches_dir().glob("*.json") if batches_dir().is_dir() else []:
        batch = ref.read_json(path, {}) or {}
        if batch.get("estado") in ("hecho", "fallo", "cancelado"):
            path.unlink(missing_ok=True)


def worker_running():
    """Hay un trabajador vivo (el lock con un pid que existe)."""
    if not LOCK.exists():
        return False
    try:
        pid = int(json.loads(LOCK.read_text(encoding="utf-8"))["pid"])
    except (ValueError, KeyError, json.JSONDecodeError, OSError):
        return False
    return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout


def trabajar(model=DEFAULT_MODEL, wait=3):
    """Hace los lotes pendientes en orden hasta que no quede ninguno (o se pida pausa)."""
    import time
    acquire()
    try:
        idle = 0
        while True:
            pending = [batch for batch in batches() if batch and batch["estado"] == "pendiente"]
            if not pending:
                idle += 1
                if idle > 1:   # una espera mas, por si StoryForge agrego un lote recien
                    return
                time.sleep(wait)
                continue
            idle = 0
            if PAUSE.exists():
                log("pausa pedida: los lotes pendientes esperan")
                return
            batch = pending[0]
            update_batch(batch["lote"], estado="corriendo",
                         empezado=datetime.datetime.now().isoformat(timespec="seconds"))
            log(f"lote {batch['lote']}: empieza ({batch.get('etiqueta') or len(batch['ids'])})")
            try:
                jobs = correr(batch["ids"] or None, model=model, only_ollama=batch["solo_ollama"], locked=True,
                              progress=lambda done, total, current, number=batch["lote"]: update_batch(
                                  number, hechos=done, total=total, actual=current))
                failed = sum(1 for job in jobs or [] if job.get("resultado") == "fallo" or job.get("ollama") == "fallo")
                paused = PAUSE.exists()
                update_batch(batch["lote"], estado="pendiente" if paused else ("fallo" if failed else "hecho"),
                             actual=None, terminado=datetime.datetime.now().isoformat(timespec="seconds"),
                             resultado=f"{failed} con fallo" if failed else "ok",
                             trabajos=[{"nodo": job["nodo"], "motivo": job["motivo"],
                                        "resultado": job.get("resultado") or job.get("ollama") or "-"}
                                       for job in jobs or []][:200])
                if paused:
                    return
            except SystemExit as error:   # p. ej. Ollama no se descargo: el lote falla y se sigue con el proximo
                update_batch(batch["lote"], estado="fallo", actual=None, resultado=str(error))
            except Exception as error:  # noqa: BLE001 - un lote roto no frena la cola
                log(f"lote {batch['lote']}: fallo ({error!r})")
                update_batch(batch["lote"], estado="fallo", actual=None, resultado=repr(error)[:300])
    finally:
        release()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", choices=("plan", "correr", "trabajar"))
    parser.add_argument("nodos", nargs="*")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--modelo", help="modelo de Ollama (por defecto el de la configuracion del proyecto)")
    parser.add_argument("--solo-ollama", action="store_true")
    parser.add_argument("--proyecto", default="ejemplo_1", help="id del proyecto (storyforge/proyectos.json)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import proyecto_sf
    proyecto_sf.activar(args.proyecto)   # rutas y configuracion del proyecto
    args.modelo = args.modelo or proyecto_sf.config()["ollama_modelo"]
    if args.accion == "plan":
        jobs = ref.planificar(args.nodos or "pendientes")
        for job in jobs:
            print(f"{job['nodo']}: {job['motivo']} {job['detalle']}")
        for model_name, node_id, step in comfy_steps(jobs):
            print(f"  {model_name:12} {node_id} {step or ''}")
        return
    if args.accion == "trabajar":
        trabajar(args.modelo)
        return
    correr(args.nodos or None, args.limite, args.modelo, args.solo_ollama)


if __name__ == "__main__":
    main()
