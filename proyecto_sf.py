"""Proyectos de StoryForge como carpetas, y el proyecto activo.

Cada proyecto es una carpeta con este formato (ademas de "Ejemplo 1", que es un adaptador sobre lo que ya existia:
universo/ + Agente Frequency/ + storyforge/proyectos/ejemplo_1/, sin mover nada):

  proyecto.json     id, nombre, idea, premisa, configuracion, etapa
  universo.json     personajes, locaciones, reglas y canon del proyecto
  asignaciones.json elenco congelado por escena (tema)
  guion.json        estructura (secuencias -> escenas -> planos) y textos editados
  edicion.json      orden de los clips
  temas/            una carpeta por escena-tema (como Agente Frequency): plan, equipo/, ficha.json, fondo.png, toma/
  referencias/      el almacen de referencias.py (retratos, lugares, objetos, vestuario...) y el log de la cola
  revisiones/       informes de los revisores y hoja de ruta

`activar()` apunta las rutas que usan referencias.py, universo.py, la cola y StoryForge al proyecto elegido (un
proyecto activo a la vez). `guardar()` copia el proyecto activo a otra carpeta (con respaldo si ya existia) y
`cargar()` valida una carpeta y la activa. La configuracion del proyecto (modelo de Ollama, ComfyUI, bloom...) se
aplica al activar.
"""
import datetime
import json
import shutil
from pathlib import Path

import cola_referencias as cola
import equipo_imagen as equipo
import fondo_comfy
import postproceso
import referencias as ref
import universo

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "storyforge" / "proyectos"
REGISTRY = ROOT / "storyforge" / "proyectos.json"
EXAMPLE_1 = "ejemplo_1"
DEFAULT_CONFIG = {"ollama_modelo": "qwen3:30b-a3b-instruct-2507-q4_K_M", "num_ctx": 16384,
                  "comfy_url": "http://127.0.0.1:8188", "bloom": "fuerte", "negros": "suave", "estilo_guion": None}
STATE = {"id": None, "carpeta": None}
SKIP = {"cola.lock", "__pycache__"}


def registry():
    return ref.read_json(REGISTRY, {"proyectos": []}) or {"proyectos": []}


def entry(project_id):
    return next((item for item in registry()["proyectos"] if item["id"] == project_id), None)


def folder_of(project_id):
    """Carpeta del proyecto (la de Ejemplo 1 es la de sus agregados: guion.json, edicion.json, proyecto.json)."""
    item = entry(project_id)
    if not item:
        raise ValueError(f"No hay proyecto {project_id}")
    return Path(item.get("carpeta") or PROJECTS / project_id)


def paths(project_id):
    """Rutas que usa cada modulo para un proyecto."""
    if project_id == EXAMPLE_1:
        return {"universo": ROOT / "universo" / "universo.json", "asignaciones": ROOT / "universo" / "asignaciones.json",
                "referencias": ROOT / "universo" / "referencias", "temas": ROOT / "Agente Frequency",
                "carpeta": PROJECTS / EXAMPLE_1}
    folder = folder_of(project_id)
    return {"universo": folder / "universo.json", "asignaciones": folder / "asignaciones.json",
            "referencias": folder / "referencias", "temas": folder / "temas", "carpeta": folder}


def config(project_id=None):
    data = ref.read_json(paths(project_id or STATE["id"])["carpeta"] / "proyecto.json", {}) or {}
    return {**DEFAULT_CONFIG, **(data.get("config") or {})}


def activar(project_id):
    """Apunta referencias, universo, la cola y la configuracion al proyecto. Devuelve sus rutas."""
    places = paths(project_id)
    universo.FILE = places["universo"]
    universo.ASSIGNMENTS = places["asignaciones"]
    ref.STORE = places["referencias"]
    ref.SETTINGS = places["referencias"] / "ajustes.json"
    ref.SONGS = places["temas"]
    cola.LOCK = ref.STORE / "cola.lock"
    cola.LOG = ref.STORE / "registro.log"
    cola.STATUS = ref.STORE / "cola.json"
    cola.STRUCTURE_PROPOSAL = places["carpeta"] / "guion_propuesta.json"
    STATE.update(id=project_id, carpeta=places["carpeta"])
    settings = config(project_id)
    cola.DEFAULT_MODEL = settings["ollama_modelo"]
    equipo.NUM_CTX = int(settings["num_ctx"])
    fondo_comfy.URL = settings["comfy_url"].rstrip("/")
    postproceso.BLOOM = settings["bloom"]
    postproceso.NEGROS = settings["negros"]
    ensure_structure(project_id)
    return places


# --- la carpeta de cada proyecto ------------------------------------------------------------------------
# (clave, ruta relativa, que guarda). Todo proyecto nuevo tiene exactamente esto adentro de su carpeta.
STRUCTURE = [
    ("proyecto", "proyecto.json", "Nombre, idea, premisa, declaración de intención y configuración"),
    ("universo", "universo.json", "Personajes, lugares, objetos, reglas y canon"),
    ("asignaciones", "asignaciones.json", "Qué personaje, lugar y objeto tiene cada escena-tema"),
    ("guion", "guion.json", "Secuencias, escenas y planos (el guion que editás)"),
    ("edicion", "edicion.json", "Orden de los clips y fechas de publicación"),
    ("temas", "temas", "Una carpeta por escena-tema: plan musical, equipo de imagen, ficha, fondo y toma"),
    ("direccion", "direccion", "Planta, cámaras de inicio y fin y cuadros de previz de cada escena del guion"),
    ("referencias", "referencias", "Imágenes generadas con sus versiones y aprobaciones (retratos, lugares, planos, clips) y el log de la cola"),
    ("revisiones", "revisiones", "Informes de los revisores y hojas de ruta por etapa"),
    ("versiones", "versiones", "Copias anteriores del guion (cada vez que se guarda)"),
    ("exportes", "exportes", "Lo que exportás: .fountain, .fdx, SEO"),
]
# Ejemplo 1 usa carpetas que tambien usa el agente musical: quedan donde estan y StoryForge las enlaza
LINKED = {"universo": "universo/universo.json", "asignaciones": "universo/asignaciones.json",
          "temas": "Agente Frequency", "referencias": "universo/referencias"}


def ensure_structure(project_id):
    """Crea las carpetas que falten y el LEEME.md que explica que hay en cada una."""
    folder = paths(project_id)["carpeta"]
    folder.mkdir(parents=True, exist_ok=True)
    linked = project_id == EXAMPLE_1
    for key, relative, _ in STRUCTURE:
        if "." not in relative and not (linked and key in LINKED):
            (folder / relative).mkdir(exist_ok=True)
    lines = [f"# {read_project(project_id).get('nombre') or project_id}", "",
             "Carpeta de un proyecto de StoryForge. Se guarda sola mientras trabajás; el botón Guardar además deja",
             "una copia del guion en versiones/ y anota la fecha.", ""]
    for key, relative, description in STRUCTURE:
        where = f"{ROOT / LINKED[key]} (enlazada)" if linked and key in LINKED else relative
        lines.append(f"- **{where}**: {description}")
    if linked:
        lines += ["", "Ejemplo 1 comparte universo/ y Agente Frequency/ con el agente musical, por eso esas carpetas",
                  "quedan donde estaban. 'Guardar copia en…' arma una carpeta completa e independiente."]
    (folder / "LEEME.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def _size(path):
    if path.is_file():
        return 1, path.stat().st_size
    files = [item for item in path.rglob("*") if item.is_file()] if path.is_dir() else []
    return len(files), sum(item.stat().st_size for item in files)


def folders_view(project_id=None):
    """Que guarda el proyecto y donde (para la pagina Carpetas)."""
    project_id = project_id or STATE["id"]
    folder = paths(project_id)["carpeta"]
    entries = []
    for key, relative, description in STRUCTURE:
        linked = project_id == EXAMPLE_1 and key in LINKED
        path = ROOT / LINKED[key] if linked else folder / relative
        count, size = _size(path)
        entries.append({"clave": key, "nombre": relative, "ruta": str(path), "descripcion": description,
                        "enlazada": linked, "existe": path.exists(), "archivos": count,
                        "mb": round(size / 2**20, 1)})
    data = read_project(project_id)
    return {"id": project_id, "nombre": data.get("nombre") or project_id, "carpeta": str(folder),
            "guardado": data.get("guardado"), "entradas": entries}


def guardar_aqui():
    """Guarda el proyecto en su propia carpeta: crea lo que falte, deja una copia del guion en versiones/ y la fecha."""
    project_id = STATE["id"]
    folder = ensure_structure(project_id)
    stamp = datetime.datetime.now()
    script = folder / "guion.json"
    if script.is_file():
        shutil.copy2(script, folder / "versiones" / f"guion_{stamp:%Y%m%d-%H%M%S}_guardado.json")
    save_project(lambda data: data.update(guardado=stamp.isoformat(timespec="seconds"),
                                          id=data.get("id") or project_id))
    return folders_view(project_id)


def folder_for(key):
    """Ruta real de una entrada de la estructura (para abrirla en el Explorador)."""
    entry_ = next((item for item in folders_view()["entradas"] if item["clave"] == key), None)
    if key == "carpeta":
        return paths(STATE["id"])["carpeta"]
    if not entry_:
        raise ValueError("carpeta desconocida")
    path = Path(entry_["ruta"])
    return path if path.is_dir() else path.parent


def project_file(project_id=None):
    return paths(project_id or STATE["id"])["carpeta"] / "proyecto.json"


def read_project(project_id=None):
    return ref.read_json(project_file(project_id), {}) or {}


def save_project(change, project_id=None):
    data = read_project(project_id)
    change(data)
    ref.write_json(project_file(project_id), data)
    return data


def register(project_id, name, folder, kind="carpeta", note=""):
    data = registry()
    data["proyectos"] = [item for item in data["proyectos"] if item["id"] != project_id]
    data["proyectos"].append({"id": project_id, "nombre": name, "tipo": kind, "carpeta": str(folder), "nota": note,
                              "abierto": datetime.datetime.now().isoformat(timespec="seconds")})
    ref.write_json(REGISTRY, data)
    return data


def _copy_tree(source, target):
    for path in source.rglob("*"):
        if path.is_dir() or path.name in SKIP or any(part in SKIP for part in path.parts):
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _unique_id(base):
    taken = {item["id"] for item in registry()["proyectos"]}
    base = "".join(char if char.isalnum() else "_" for char in base.lower()).strip("_") or "proyecto"
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}_{number}", number + 1
    return candidate


def guardar(target, name=None):
    """Copia el proyecto activo a `target` como un proyecto nuevo e independiente (con su propia carpeta y su id) y lo
    registra, para poder abrirlo y seguir trabajando ahi. El proyecto abierto no cambia. Ejemplo 1 se exporta: sus
    temas con equipo, su universo, su almacen y sus agregados. Si la carpeta ya tenia algo, queda un respaldo al lado;
    si esta vacia, se usa."""
    target = Path(target).resolve()
    places = paths(STATE["id"])
    for key in ("carpeta", "referencias", "temas"):
        source = places[key].resolve()
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError(f"La copia no puede ir dentro del proyecto (ni el proyecto dentro de la copia): {source}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"{target} es un archivo, no una carpeta")
    temporary = target.with_name(target.name + ".guardando")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    _copy_tree(places["carpeta"], temporary)
    for key in ("universo", "asignaciones"):
        if places[key].is_file():
            shutil.copy2(places[key], temporary / places[key].name)
    if places["referencias"].is_dir() and places["referencias"].resolve() != (places["carpeta"] / "referencias").resolve():
        _copy_tree(places["referencias"], temporary / "referencias")
    if places["temas"].resolve() != (places["carpeta"] / "temas").resolve():
        for seed in ref.song_seeds():
            song = ref.song_folder(seed)
            if (song / "equipo").is_dir():
                _copy_tree(song, temporary / "temas" / song.name)
    original = read_project(STATE["id"])
    project_id = _unique_id(name or target.name)
    data = ref.read_json(temporary / "proyecto.json", {}) or {}
    data.update(id=project_id, nombre=name or target.name, copia_de=original.get("nombre") or STATE["id"],
                guardado=datetime.datetime.now().isoformat(timespec="seconds"))
    ref.write_json(temporary / "proyecto.json", data)
    if target.exists():
        if any(target.iterdir()):
            shutil.move(str(target), target.with_name(f"{target.name}.respaldo-{datetime.datetime.now():%Y%m%d-%H%M%S}"))
        else:
            target.rmdir()   # carpeta vacia (por ejemplo, recien creada en el Explorador): se usa
    temporary.rename(target)
    register(project_id, data["nombre"], target, note=f"copia de {data['copia_de']}")
    return target, project_id


def cargar(folder):
    """Valida una carpeta de proyecto, la registra y la activa."""
    folder = Path(folder).resolve()
    data = ref.read_json(folder / "proyecto.json")
    if not data or not (folder / "universo.json").is_file():
        raise ValueError("La carpeta no es un proyecto de StoryForge (falta proyecto.json o universo.json)")
    project_id = data.get("id") or folder.name
    register(project_id, data.get("nombre", folder.name), folder)
    activar(project_id)
    return project_id


def nuevo(name, idea="", folder=None):
    """Proyecto vacio desde una idea (las etapas siguientes se generan en StoryForge)."""
    project_id = "".join(char if char.isalnum() else "_" for char in name.lower()).strip("_") or "proyecto"
    folder = Path(folder or PROJECTS / project_id).resolve()
    if (folder / "proyecto.json").exists():
        raise ValueError(f"Ya existe un proyecto en {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    ref.write_json(folder / "proyecto.json", {"id": project_id, "nombre": name, "idea": idea, "premisa": {},
                                              "config": dict(DEFAULT_CONFIG), "etapa": "idea",
                                              "creado": datetime.datetime.now().isoformat(timespec="seconds")})
    ref.write_json(folder / "universo.json", {"_nota": "", "reglas": "", "personajes": {}, "locaciones": {}, "canon": []})
    ref.write_json(folder / "guion.json", {"premisa": "", "actos": []})
    register(project_id, name, folder)
    activar(project_id)
    return project_id


def crear_ejemplo_simple(seed=2051, project_id="ejemplo_simple"):
    """Proyecto chico para recorrer todas las etapas: un tema de Ejemplo 1 con su personaje, su lugar y su objeto."""
    source = paths(EXAMPLE_1)
    folder = PROJECTS / project_id
    if (folder / "proyecto.json").exists():
        return folder
    data = json.loads(source["universo"].read_text(encoding="utf-8"))
    cast = json.loads(source["asignaciones"].read_text(encoding="utf-8"))[str(seed)]
    person = dict(data["personajes"][cast["id"]])
    person["arco"] = [step for step in person.get("arco", []) if step.get("tema") == seed]
    person["lugares"] = [cast["lugar_id"]]
    person.pop("relaciones", None)
    place = data["locaciones"][cast["lugar_id"]]
    song = next(path for path in source["temas"].glob(f"* {seed}") if (path / f"{path.name}.json").is_file())
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "temas").mkdir(exist_ok=True)
    for name in (f"{song.name}.json", "ficha.json", f"{song.name} ficha.md", "fondo.png"):
        if (song / name).is_file():
            target = folder / "temas" / song.name / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(song / name, target)
    shutil.copytree(song / "equipo", folder / "temas" / song.name / "equipo", dirs_exist_ok=True)
    sheet = json.loads((song / "ficha.json").read_text(encoding="utf-8"))
    concept = sheet.get("concepto") or {}
    ref.write_json(folder / "universo.json", {
        "_nota": data.get("_nota", ""), "reglas": data.get("reglas", ""),
        "personajes": {cast["id"]: person}, "locaciones": {cast["lugar_id"]: place},
        "canon": [fact for fact in data.get("canon", []) if fact.get("tema") == seed]})
    ref.write_json(folder / "asignaciones.json", {str(seed): cast})
    ref.write_json(folder / "proyecto.json", {
        "id": project_id, "nombre": "Ejemplo simple · Lunar Departure",
        "idea": "Una buceadora de la ciudad sumergida rescata del agua la ultima foto de su familia.",
        "premisa": {"titulo": "Lunar Departure", "logline": concept.get("tesis", ""),
                    "genero": "Synthwave · cyberpunk anime 90s", "formato": "Un tema = una escena",
                    "tono": "melancolico, nocturno"},
        "config": dict(DEFAULT_CONFIG), "etapa": "guion",
        "creado": datetime.datetime.now().isoformat(timespec="seconds")})
    ref.write_json(folder / "guion.json", {"premisa": concept.get("tesis", ""), "actos": [
        {"titulo": "Acto unico", "secuencias": [{"titulo": "La foto", "sinopsis": "", "temas": [seed]}]}]})
    register(project_id, "Ejemplo simple · Lunar Departure", folder, note="1 tema para recorrer todas las etapas")
    return folder


def ensure_registry():
    """Ejemplo 1 siempre registrado (proyectos.json viejo se respeta)."""
    data = registry()
    if not any(item["id"] == EXAMPLE_1 for item in data["proyectos"]):
        data["proyectos"].insert(0, {"id": EXAMPLE_1, "nombre": "Ejemplo 1 · Agente Frequency / Neo-Kansai Delta",
                                     "tipo": "ejemplo1", "carpeta": str(PROJECTS / EXAMPLE_1)})
        ref.write_json(REGISTRY, data)
    for item in data["proyectos"]:
        if item["id"] == EXAMPLE_1 and not item.get("carpeta"):
            item["carpeta"] = str(PROJECTS / EXAMPLE_1)
            item["tipo"] = "ejemplo1"
            ref.write_json(REGISTRY, data)
    return data
