"""Genera cada tipo de imagen de referencia y las tomas (ver referencias.py y el plan de StoryForge).

  retrato, lugar, objeto   Z-Image (estilo de referencia del canal), varios candidatos, el mas vistoso primero
  vista, expresion         Flux Kontext sobre el retrato aprobado (la misma cara)   } ficha completa (a pedido)
  vestuario                Flux Kontext sobre el retrato aprobado
  cinematico, tela         Flux Kontext sobre el vestuario aprobado                 } ficha completa (a pedido)
  hoja                     ffmpeg: hoja de produccion (retrato, giro, expresiones, cine, telas y objetos)
  toma                     dos pasos para no cambiar de modelo a cada rato:
                             compose: Kontext con vestuario (o retrato) + lugar [+ objeto]
                             estilo:  Z-Image img2img con el prompt largo del equipo + acabado del canal
Las funciones suponen ComfyUI prendido; la cola (cola_referencias.py) se ocupa de prenderlo, de descargar Ollama
antes y de agrupar los trabajos por modelo.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import decoupage_sf
import equipo_imagen as equipo
import estudio_imagen as estudio
import fondo_comfy as comfy
import postproceso
import referencias as ref
import universo
import visual_estilo as visual

VIEW_TEXT = {"frente": "full body from head to boots, standing straight facing the camera, arms relaxed",
             "tres_cuartos": "full body from head to boots, standing in a three-quarter front view",
             "perfil": "full body from head to boots, standing in a clean side profile facing left",
             "tres_cuartos_espalda": "full body from head to boots, standing in a three-quarter back view, the face "
                                     "turned away",
             "espalda": "full body from head to boots, standing seen from directly behind"}
EXPRESSION_TEXT = {"neutral": "a calm neutral expression",
                   "determinada": "a determined expression, jaw set, eyes narrowed with focus",
                   "sonrisa": "a small honest smile reaching the eyes",
                   "enojo": "an angry expression, brows drawn together",
                   "preocupacion": "a worried expression, brows raised in the middle, lips pressed",
                   "sorpresa": "a surprised expression, eyes wide, lips slightly parted"}
KEEP = "Keep the exact same person: same face, same hair, same age and skin, same anime drawing style. "
CANDIDATES = {"retrato": 3, "lugar": 3, "objeto": 2, "vista": 1, "expresion": 1, "cinematico": 2, "tela": 1,
              "vestuario": 1}
SIZES = {"retrato": (1024, 1024), "lugar": (1344, 768), "objeto": (1024, 1024), "vista": (640, 1280),
         "expresion": (896, 896), "cinematico": (1344, 768), "tela": (896, 896), "vestuario": (832, 1216)}
MODEL_OF = {"retrato": "zimage", "lugar": "zimage", "objeto": "zimage", "vista": "kontext", "expresion": "kontext",
            "vestuario": "kontext", "cinematico": "kontext", "tela": "kontext", "hoja": "ffmpeg",
            "toma_compose": "kontext", "toma_estilo": "zimage", "clip": "wan"}
KONTEXT_WORDS = 220   # T5 corta los prompts largos


def seed_for(node_id, version):
    return int(hashlib.sha1(node_id.encode()).hexdigest()[:8], 16) % 1_000_000 + 1000 * (version - 1)


def chosen_path(node_id):
    """Archivo de la imagen elegida (aprobada) de un nodo."""
    _, candidate = ref.chosen_image(node_id)
    if not candidate:
        raise ValueError(f"{node_id} no tiene imagen")
    return ref.node_dir(node_id) / candidate["archivo"]


# --- prompts ------------------------------------------------------------------------------------
def portrait_prompt(person):
    return (f"character reference portrait, head and shoulders, facing the camera, eyes open looking at the viewer, "
            f"neutral calm expression, plain flat medium grey background, soft even light, one person only. "
            f"A young adult {person['genero']}, {person['edad']} years old, clearly a grown adult: {person['aspecto']}. "
            f"{', '.join(person.get('implantes', []))}. {visual.STYLE_ZIMAGE_REF}")


def place_prompt(place):
    return (f"empty establishing shot of a place, no people, no figures: {place['prompt']}. Light: {place['luz']}. "
            f"Atmosphere: {place['atmosfera']}. Props: {', '.join(place.get('utileria', [])[:5])}. {visual.STYLE_ZIMAGE_PLACE}")


def object_prompt(text):
    return (f"single object reference, centered, plain grey background, no people, no hands, no text: {text}. "
            f"{visual.STYLE_ZIMAGE_OBJECT}")


def view_prompt(view, person):
    return (f"{KEEP}Character turnaround reference: {VIEW_TEXT[view]}, wearing: {person['vestuario']}. "
            "Plain grey studio background, even light. One person only.")


def expression_prompt(face):
    return (f"{KEEP}Face study, head and shoulders, eyes open: change only the expression to {EXPRESSION_TEXT[face]}. "
            "Plain grey studio background. One person only.")


def cinematic_prompt(person, place):
    return (f"{KEEP}Same outfit. Cinematic portrait shot of this person, chest up, looking just past the camera, "
            f"shallow depth of field, in {place['prompt']}, lit by {place['luz']}. 1990s cyberpunk anime OVA "
            "illustration. One person only.")


def fabric_prompt(garment):
    return (f"Extreme close-up of the material of the {garment} from this outfit: texture, seams, wear and color. "
            "No face, no hands, fills the frame. Same anime drawing style.")


def wardrobe_prompt(person):
    return (f"{KEEP}Show them from the waist up, three-quarter view, wearing: {person['vestuario']}. "
            "Plain grey studio background. One person only.")


def kontext_prompt(team, place, person, with_object, staging=""):
    """Prompt corto para componer la toma: quien es cada referencia, la escena del director y la camara."""
    director, photographer = team.get("director", {}), team.get("fotografo", {})
    obj = " The small reference on the right is an OBJECT the character carries or uses." if with_object else ""
    text = (f"Create one new illustration. The person in the left reference is the only character: keep the exact same "
            f"face, hair, skin, age and outfit. The next reference is the LOCATION: set the scene inside this place.{obj} "
            "Do not reproduce the references side by side; one single person, one single scene, eyes open. "
            f"Scene: {equipo.plain(director.get('escena', ''))} "
            f"Camera: {photographer.get('plano', '')}, {photographer.get('angulo', '')}, {photographer.get('lente', '')}. "
            f"{staging + '. ' if staging else ''}"
            f"Light: {equipo.LIGHT_TEXT.get(photographer.get('luz', ''), '')}. 1990s cyberpunk anime OVA illustration.")
    return equipo.trim(text, KONTEXT_WORDS)


# --- generadores -----------------------------------------------------------------------------------
def _candidates(kind, node_id, version, prompt_or_graph, work):
    """Genera N candidatos y los devuelve ordenados del mas vistoso al menos."""
    files = []
    for index in range(CANDIDATES.get(kind, 1)):
        seed = seed_for(node_id, version) + index
        target = work / f"{kind}_{index + 1}.png"
        graph = prompt_or_graph(seed)
        comfy.run(graph, target)
        files.append(target)
    return sorted(files, key=lambda path: -estudio.attractiveness(estudio.image_stats(path)))


def make(node_id, graph=None, data=None, step=None):
    """Genera la version nueva de un nodo y la registra. `step` para tomas: "compose" o "estilo"."""
    graph = graph or ref.nodos(data)
    data = data or universo.load()
    node = graph[node_id]
    kind = node["tipo"]
    value, digest = ref.recipe(node_id, graph, data)
    version = len(ref.ficha(node_id)["versiones"]) + 1
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        width, height = SIZES.get(kind, (1024, 1024))
        if kind == "retrato":
            prompt = portrait_prompt(data["personajes"][node["personaje"]])
            files = _candidates(kind, node_id, version, lambda seed: comfy.zimage_workflow(prompt, seed, width, height), work)
        elif kind == "lugar":
            prompt = place_prompt(data["locaciones"][node["lugar"]])
            files = _candidates(kind, node_id, version, lambda seed: comfy.zimage_workflow(prompt, seed, width, height), work)
        elif kind == "objeto":
            prompt = object_prompt(data["personajes"][node["personaje"]]["objetos"][node["indice"]])
            files = _candidates(kind, node_id, version, lambda seed: comfy.zimage_workflow(prompt, seed, width, height), work)
        elif kind in ("vista", "expresion", "vestuario", "cinematico", "tela"):
            person = data["personajes"][node["personaje"]]
            base = "retrato" if kind in ("vista", "expresion", "vestuario") else "vestuario"
            reference = comfy.upload(chosen_path(f"{base}/{node['personaje']}"))
            prompt = {"vista": lambda: view_prompt(node.get("vista"), person),
                      "expresion": lambda: expression_prompt(node.get("expresion")),
                      "vestuario": lambda: wardrobe_prompt(person),
                      "cinematico": lambda: cinematic_prompt(person, home_place(person, data)),
                      "tela": lambda: fabric_prompt(ref.fabric_text(person, node.get("indice", 0)))}[kind]()
            files = _candidates(kind, node_id, version,
                                lambda seed: comfy.kontext_workflow(prompt, seed, [reference], width, height), work)
        elif kind == "hoja":
            files = [character_sheet(node, data, work / "hoja.png")]
        elif kind == "toma":
            return make_shot(node_id, node, value, digest, version, step)
        elif kind == "plano":
            return make_plano(node_id, node, value, digest, version, step)
        elif kind == "clip":
            return make_clip(node_id, node, value, digest, version)
        else:
            raise ValueError(kind)
        return ref.record_version(node_id, files, value, digest, MODEL_OF[kind])


def home_place(person, data):
    """El primer lugar del personaje (para la luz del retrato de cine)."""
    places = [place for place in person.get("lugares", []) if place in data["locaciones"]] or list(data["locaciones"])
    return data["locaciones"][places[0]]


def _ffmpeg_path(path):
    """Ruta para un filtro de ffmpeg en Windows: barras normales y los dos puntos escapados."""
    return str(path).replace(chr(92), "/").replace(":", chr(92) + ":")


SHEET_FONT = _ffmpeg_path("C:/Windows/Fonts/arial.ttf")


def sheet_boxes(node):
    """(nodo, x, y, ancho, alto) de cada imagen en la hoja de 2400x1350."""
    parents = node["padres"]
    pick = lambda prefix: [parent for parent in parents if parent.startswith(prefix)]  # noqa: E731
    boxes = [(f"retrato/{node['personaje']}", 40, 150, 520, 520)]
    boxes += [(item, 600 + n * 355, 110, 330, 640) for n, item in enumerate(pick("vista/"))]
    boxes += [(item, 40, 800, 860, 484) for item in pick("cinematico/")[:1]]
    boxes += [(item, 940 + (n % 3) * 245, 800 + (n // 3) * 245, 230, 230) for n, item in enumerate(pick("expresion/"))]
    extras = pick("tela/") + pick("objeto/")
    boxes += [(item, 1700 + (n % 3) * 220, 800 + (n // 3) * 220, 204, 204) for n, item in enumerate(extras[:6])]
    return boxes


def character_sheet(node, data, target):
    """Hoja de produccion como la referencia del usuario (personajes ficha.png), 2400x1350 con ffmpeg:
    arriba retrato + giro de 5 vistas; abajo cine + expresiones (3x2) + telas y objetos. Leyendas desde el universo."""
    person = data["personajes"][node["personaje"]]
    boxes = sheet_boxes(node)
    with tempfile.TemporaryDirectory() as folder:
        texts = {"titulo": f"{person['nombre']}, {person.get('alias', '')}",
                 "sub": f"{person.get('arquetipo', '')} - {person.get('edad', '')}",
                 "giro": "Frente                  3/4                  Perfil                  3/4 espalda"
                         "                  Espalda",
                 "abajo": "Retrato de cine" + " " * 120 + "Expresiones" + " " * 90 + "Telas y objetos"}
        files = {}
        for key, value in texts.items():
            files[key] = Path(folder) / f"{key}.txt"
            files[key].write_text(value, encoding="utf-8")
        inputs = sum((["-i", str(chosen_path(item))] for item, *_ in boxes), [])
        chain = "color=c=0x16171b:s=2400x1350[c0];"
        for n, (_, x, y, w, h) in enumerate(boxes):
            fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease,scale=w='min(iw,{w})':h='min(ih,{h})'"
            chain += (f"[{n}]{fit},pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x202228[i{n}];"
                      f"[c{n}][i{n}]overlay={x}:{y}[c{n + 1}];")

        def label(key, x, y, size):
            return (f"drawtext=fontfile='{SHEET_FONT}':textfile='{_ffmpeg_path(files[key])}':x={x}:y={y}:"
                    f"fontsize={size}:fontcolor=0xf1f2f4")
        chain += (f"[c{len(boxes)}]{label('titulo', 40, 30, 48)},{label('sub', 40, 92, 26)},"
                  f"{label('giro', 640, 760, 24)},{label('abajo', 40, 1300, 22)}[out]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", chain, "-map", "[out]",
                        "-frames:v", "1", str(target)], check=True)
    return target


def sheet(paths, target, height=512):
    """Hoja de personaje con ffmpeg: las imagenes en fila con el mismo alto."""
    inputs = sum((["-i", str(path)] for path in paths), [])
    scaled = "".join(f"[{n}]scale=-2:{height}[s{n}];" for n in range(len(paths)))
    joined = "".join(f"[s{n}]" for n in range(len(paths)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    f"{scaled}{joined}hstack=inputs={len(paths)}", "-frames:v", "1", str(target)], check=True)
    return target


def shot_adjustments(node_id):
    """Ajustes de la toma segun lo que pidio el usuario al rechazar: mas parecido baja el denoise, mas estilo lo sube."""
    review = ref.revision(node_id)["imagenes"].values()
    delta = sum(.1 for item in review if item.get("accion") == "mas_estilo") - \
        sum(.1 for item in review if item.get("accion") == "mas_parecido")
    return delta


def make_shot(node_id, node, value, digest, version, step):
    """Toma en dos pasos. compose deja el resultado de Kontext en toma/trabajo/; estilo hace la imagen final."""
    folder = ref.node_dir(node_id)
    song = folder.parent
    work = folder / "trabajo"
    work.mkdir(parents=True, exist_ok=True)
    tuning = ref.settings()
    composed = work / f"compose_{digest[:10]}.png"
    if step in (None, "compose"):
        if not composed.is_file():
            team = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (song / "equipo").glob("*.json")
                    if path.stem in equipo.ORDER}
            data = universo.load()
            cast = universo.frozen()[str(node["semilla"])]
            person = data["personajes"][cast["id"]]
            place = data["locaciones"][cast["lugar_id"]]
            person_ref = f"{tuning['persona_ref']}/{cast['id']}"
            images = [comfy.upload(chosen_path(person_ref)), comfy.upload(chosen_path(f"lugar/{cast['lugar_id']}"))]
            if cast.get("objeto") is not None:
                images.append(comfy.upload(chosen_path(f"objeto/{cast['id']}__{cast['objeto']}")))
            prompt = kontext_prompt(team, place, person, cast.get("objeto") is not None,
                                    decoupage_sf.staging(decoupage_sf.load(song)))
            options = []
            for index in range(2):
                target = work / f"compose_{digest[:10]}_{index + 1}.png"
                comfy.run(comfy.kontext_workflow(prompt, seed_for(node_id, version) + index, images,
                                                 mode=tuning["modo"], lora=tuning["lora"]), target)
                options.append(target)
            best = max(options, key=lambda path: estudio.attractiveness(estudio.image_stats(path)))
            composed.write_bytes(best.read_bytes())
        if step == "compose":
            return None
    if not composed.is_file():
        raise ValueError(f"{node_id}: falta el paso compose")
    sheet_data = json.loads((song / "ficha.json").read_text(encoding="utf-8"))
    denoise = min(.65, max(.2, tuning["denoise"] + shot_adjustments(node_id)))
    styled = work / f"estilo_{digest[:10]}.png"
    comfy.run(comfy.zimage_img2img(estudio.full_prompt(sheet_data["prompt_imagen"]), seed_for(node_id, version),
                                   comfy.upload(composed), denoise, hires_denoise=tuning["hires_denoise"]), styled)
    final = work / f"final_{digest[:10]}.png"
    postproceso.postprocess(styled, final, sheet_data.get("paleta"),
                            gamma=estudio.exposure(estudio.image_stats(styled)))
    return ref.record_version(node_id, [final], value, digest, "kontext+zimage",
                              {"compose": composed.name, "estilo": styled.name, "denoise": denoise})


# --- planos del guion (inicio y fin) y clips de Wan ----------------------------------------------------------
PLAN_AGENT = ("Write ONE English image prompt (60 to 120 words) for this film shot: who is in frame and where, what "
              "their hands and body are doing, the place, the light. Only what a camera sees: no thoughts, no magic, "
              "no glowing things synced to breath, no readable text. Every person is an adult.")


def english_prompt_path(scene_id, shot_id):
    return ref.STORE / "plano" / f"{scene_id}__{shot_id}_prompt.json"


def english_source(scene, shot):
    return ref.sha_json({"accion": scene.get("accion"), "plano": {key: shot.get(key) for key in
                                                                 ("tipo", "que_se_ve", "accion", "movimiento")}})


def plano_prompt(scene, shot, model, ask=None):
    """Ollama pasa la escena y el plano (en castellano) a un prompt de imagen en ingles. None si no pudo."""
    data = universo.load()
    people = [f"{data['personajes'][pid]['nombre']}: {data['personajes'][pid]['aspecto']}"
              for pid in scene.get("elenco", []) if pid in data["personajes"]]
    place = data["locaciones"].get(scene.get("lugar_id"), {}).get("prompt", scene.get("lugar", ""))
    schema = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
    text = (f"{PLAN_AGENT}\n\nSCENE ({scene.get('int_ext', '')} {scene.get('lugar', '')} - {scene.get('momento', '')}): "
            f"{scene.get('accion', '')}\nSHOT {shot.get('tipo')}: {shot.get('que_se_ve', '')}. {shot.get('accion', '')}\n"
            f"PEOPLE: {'; '.join(people)}\nPLACE: {place}\nReturn JSON {{\"prompt\": ...}}.")
    answer = (ask or equipo.ask)(text, schema, model, 23)
    prompt = equipo.literal(equipo.plain(answer.get("prompt", "")))
    if not prompt or equipo.check_text("director", prompt, 20, 200):
        return None
    ref.write_json(english_prompt_path(scene["id"], shot["id"]), {"prompt": prompt, "fuente": english_source(scene, shot)})
    return prompt


def _scene_and_shot(node):
    scene = next(item for item in ref.script_scenes() if item["id"] == node["escena"])
    shot = next(item for item in scene["planos"] if item["id"] == node["plano"])
    return scene, shot


def make_plano(node_id, node, value, digest, version, step):
    """Imagen de inicio o de fin de un plano: Kontext compone con persona + lugar + el boceto de previz (camara y
    puesta), y Z-Image da el estilo (como las tomas)."""
    scene, shot = _scene_and_shot(node)
    saved = ref.read_json(english_prompt_path(scene["id"], shot["id"]))
    if not saved or saved.get("fuente") != english_source(scene, shot):
        raise ValueError(f"{node_id}: falta el prompt en ingles (lo prepara Ollama en la fase de texto)")
    folder = ref.node_dir(node_id)
    work = folder / "trabajo"
    work.mkdir(parents=True, exist_ok=True)
    tuning = ref.settings()
    composed = work / f"compose_{digest[:10]}.png"
    if step in (None, "compose") and not composed.is_file():
        images = [comfy.upload(chosen_path(parent)) for parent in node["padres"]]
        sketch = ref.plan_folder(node["escena"]) / "toma" / "previz" / f"{node['plano']}_{node['momento']}.png"
        layout = (" The LAST reference is a rough grey 3D layout sketch: match its camera position, framing and where "
                  "the people stand; do not copy its grey shapes or colors.") if sketch.is_file() else ""
        if sketch.is_file():
            images.append(comfy.upload(sketch))
        prompt = equipo.trim(f"Create one new illustration. The first reference is the person (keep the exact same face, "
                             f"hair, age and outfit); the next is the LOCATION.{layout} One single scene, eyes open. "
                             f"{saved['prompt']} {value.get('puesta', '')}. 1990s cyberpunk anime OVA illustration.",
                             KONTEXT_WORDS)
        options = []
        for index in range(2):
            target = work / f"compose_{digest[:10]}_{index + 1}.png"
            comfy.run(comfy.kontext_workflow(prompt, seed_for(node_id, version) + index, images,
                                             mode=tuning["modo"], lora=tuning["lora"]), target)
            options.append(target)
        composed.write_bytes(max(options, key=lambda path: estudio.attractiveness(estudio.image_stats(path))).read_bytes())
    if step == "compose":
        return None
    denoise = min(.65, max(.2, tuning["denoise"] + shot_adjustments(node_id)))
    styled = work / f"estilo_{digest[:10]}.png"
    comfy.run(comfy.zimage_img2img(estudio.full_prompt(saved["prompt"]), seed_for(node_id, version),
                                   comfy.upload(composed), denoise, hires_denoise=tuning["hires_denoise"]), styled)
    final = work / f"final_{digest[:10]}.png"
    postproceso.postprocess(styled, final, None, gamma=estudio.exposure(estudio.image_stats(styled)))
    return ref.record_version(node_id, [final], value, digest, "kontext+zimage", {"denoise": denoise})


def clip_prompt(node):
    """Prompt de Wan: la escena en ingles + el movimiento de camara y de las personas del previz."""
    if node.get("semilla"):
        folder = ref.song_folder(node["semilla"])
        director = ref.read_json(folder / "equipo" / "director.json", {}) or {}
        scene_text = equipo.trim(director.get("escena", ""), 90)
    else:
        saved = ref.read_json(english_prompt_path(node["escena"], node["plano"]), {}) or {}
        scene_text = saved.get("prompt", "")
    camera, people = ref.shot_text(node).get("movimiento") or ("static camera", "")
    return f"{scene_text} Camera: {camera}.{' ' + people + '.' if people else ''} Natural fluid movement, same face and outfit."


def make_clip(node_id, node, value, digest, version):
    """Clip de Wan 2.2 entre la imagen de inicio y la de fin (o desde la toma, si es un tema)."""
    start = comfy.upload(chosen_path(node["padres"][0]))
    end = comfy.upload(chosen_path(node["padres"][1])) if len(node["padres"]) > 1 else None
    folder = ref.node_dir(node_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"trabajo_{digest[:10]}.mp4"
    comfy.run(comfy.wan_clip_workflow(clip_prompt(node), seed_for(node_id, version), start, end), target,
              output=comfy.WAN_OUTPUT, timeout=3600)
    return ref.record_version(node_id, [target], value, digest, "wan2.2" + (" inicio+fin" if end else " i2v"))
