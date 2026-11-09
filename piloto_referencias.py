"""Piloto de imagenes de referencia (fase 0 del plan de StoryForge + referencias).

Prueba si se puede mantener la misma cara y el mismo lugar entre temas sin perder el look del canal:
  A. Z-Image: retratos (3 por personaje), lugares (2) y un objeto de firma (2). Se elige el mas vistoso de cada uno.
  B. Kontext: vestuario hasta la cintura desde el retrato, y la grilla de tomas
     {referencias pegadas, encadenadas} x {sin LoRA, glif90 0,7} x {persona = retrato, vestuario}.
  C. Z-Image img2img: pasada de estilo sobre la mejor toma de cada personaje,
     denoise {0,30, 0,40, 0,50} x segunda pasada grande {no, 0,30}, con el acabado del canal.
Deja todo en universo/referencias/_piloto/<fecha>/ con hojas de contacto (jpg) y grilla.html para elegir.
Usa solo ComfyUI (no Ollama): no correrlo mientras una tanda de prompts tenga a Ollama cargado.

Uso: python piloto_referencias.py [--etapa A|B|C|todo]
"""
import argparse
import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import estudio_imagen as estudio
import fondo_comfy as comfy
import postproceso
import universo
import visual_estilo as visual

ROOT = Path(__file__).resolve().parent / "universo" / "referencias" / "_piloto"
# dos personajes que contrastan (hombre y mujer, piel, pelo) y uno de sus lugares y gestos
CASTING = (("kaito_veyra", "mercado_nocturno", "pressing two glowing fingertips against a sleeping stranger's temple"),
           ("nadia_okoro", "tunel_inundado", "kicking the motorbike stand down in knee-deep water"))
OBJECT = ("kaito_veyra", 1)   # la bandolera de chips de Kaito
STYLE_DENOISE = (.30, .40, .50)
HIRES = (None, .30)


def ollama_loaded():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5) as response:
            return bool(json.loads(response.read()).get("models"))
    except OSError:
        return False


def portrait_prompt(person):
    return (f"character reference portrait, head and shoulders, facing the camera, eyes open looking at the viewer, "
            f"neutral calm expression, plain flat medium grey background, soft even light, one person only. "
            f"A young adult {person['genero']}, {person['edad']} years old, clearly a grown adult: {person['aspecto']}. "
            f"{', '.join(person['implantes'])}. {visual.STYLE_ZIMAGE_REF}")


def place_prompt(place):
    import generar_referencias   # los mismos prompts que la cola (lugar vacio, sin estilo de personaje)
    return generar_referencias.place_prompt(place)


def object_prompt(text):
    import generar_referencias
    return generar_referencias.object_prompt(text)


def wardrobe_prompt(person):
    return ("Keep the exact same person: same face, same hair, same age and skin, same anime drawing style. "
            f"Show them from the waist up, three-quarter view, wearing: {person['vestuario']}. "
            "Plain grey studio background. One person only.")


def shot_prompt(person, place, gesture, with_object):
    obj = " The small reference on the far right is an OBJECT the character carries." if with_object else ""
    return (f"Create one new illustration. The person in the left reference is the only character: keep the exact same "
            f"face, hair, skin, age and outfit. The next reference is the LOCATION: set the scene inside this place.{obj} "
            "Do not reproduce the references side by side; one single person, one single scene. "
            f"Scene: the {person['genero']} is {gesture}, eyes open, in {place['nombre'].lower()}: {place['prompt']}. "
            "Comic book cover framing, low angle, dramatic light. 1990s cyberpunk anime OVA illustration.")


def generate_z(prompt, seed, target, width, height):
    if not target.is_file():
        graph = comfy.zimage_workflow(prompt, seed, width, height)
        comfy.run(graph, target)
    return target


def best(paths):
    scored = [(estudio.attractiveness(estudio.image_stats(path)), path) for path in paths]
    return max(scored)[1]


def sheet(paths, target, height=360):
    """Hoja de contacto con ffmpeg (sin PIL): todas en una fila de alto fijo."""
    inputs = sum((["-i", str(path)] for path in paths), [])
    scaled = "".join(f"[{n}]scale=-2:{height}[s{n}];" for n in range(len(paths)))
    joined = "".join(f"[s{n}]" for n in range(len(paths)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    f"{scaled}{joined}hstack=inputs={len(paths)}" if len(paths) > 1 else f"[0]scale=-2:{height}",
                    "-frames:v", "1", str(target)], check=True)
    return target


def stage_a(folder, data):
    """Retratos, lugares y objeto con Z-Image."""
    chosen = {}
    for person_id, place_id, _ in CASTING:
        person, place = data["personajes"][person_id], data["locaciones"][place_id]
        portraits = [generate_z(portrait_prompt(person), 501 + n, folder / f"A_retrato_{person_id}_{n + 1}.png", 1024, 1024)
                     for n in range(3)]
        places = [generate_z(place_prompt(place), 601 + n, folder / f"A_lugar_{place_id}_{n + 1}.png", 1344, 768)
                  for n in range(2)]
        chosen[person_id] = {"retrato": str(best(portraits)), "lugar": str(best(places))}
        sheet(portraits + places, folder / f"A_{person_id}.jpg")
    person_id, index = OBJECT
    text = data["personajes"][person_id]["objetos"][index]
    objects = [generate_z(object_prompt(text), 701 + n, folder / f"A_objeto_{person_id}_{n + 1}.png", 1024, 1024)
               for n in range(2)]
    chosen["objeto"] = str(best(objects))
    sheet(objects, folder / "A_objeto.jpg")
    return chosen


def stage_b(folder, data, chosen):
    """Vestuario desde el retrato y grilla de tomas con Kontext."""
    comfy.free()
    for person_id, place_id, gesture in CASTING:
        person, place = data["personajes"][person_id], data["locaciones"][place_id]
        portrait = comfy.upload(chosen[person_id]["retrato"])
        wardrobe = folder / f"B_vestuario_{person_id}.png"
        if not wardrobe.is_file():
            comfy.run(comfy.kontext_workflow(wardrobe_prompt(person), 801, [portrait], 832, 1216), wardrobe)
        chosen[person_id]["vestuario"] = str(wardrobe)
        place_ref = comfy.upload(chosen[person_id]["lugar"])
        refs = {"retrato": portrait, "vestuario": comfy.upload(wardrobe)}
        extra = [comfy.upload(chosen["objeto"])] if person_id == OBJECT[0] else []
        shots = []
        for mode in ("stitch", "chain"):
            for lora in (None, "glif90"):
                for person_ref in ("retrato", "vestuario"):
                    target = folder / f"B_toma_{person_id}_{mode}_{lora or 'nolora'}_{person_ref}.png"
                    if not target.is_file():
                        graph = comfy.kontext_workflow(shot_prompt(person, place, gesture, bool(extra)), 901,
                                                       [refs[person_ref], place_ref, *extra], mode=mode, lora=lora)
                        comfy.run(graph, target)
                    shots.append(target)
        chosen[person_id]["tomas"] = [str(path) for path in shots]
        sheet(shots[:4], folder / f"B_{person_id}_pegadas.jpg", 300)
        sheet(shots[4:], folder / f"B_{person_id}_encadenadas.jpg", 300)
    return chosen


def stage_c(folder, data, chosen):
    """Pasada de estilo con Z-Image sobre la toma mas vistosa de cada personaje, y el acabado del canal."""
    comfy.free()
    for person_id, place_id, gesture in CASTING:
        person, place = data["personajes"][person_id], data["locaciones"][place_id]
        source = best([Path(path) for path in chosen[person_id]["tomas"]])
        chosen[person_id]["toma_base"] = str(source)
        uploaded = comfy.upload(source)
        prompt = estudio.full_prompt(
            f"{person['aspecto']}. Wearing {person['vestuario']}. The {person['genero']} is {gesture}, eyes open, in "
            f"{place['prompt']}")
        results = []
        for denoise in STYLE_DENOISE:
            for hires in HIRES:
                raw = folder / f"C_{person_id}_d{int(denoise * 100)}_{'h' + str(int(hires * 100)) if hires else 'sinh'}.png"
                if not raw.is_file():
                    comfy.run(comfy.zimage_img2img(prompt, 1001, uploaded, denoise, hires_denoise=hires), raw)
                final = raw.with_name(raw.stem + "_final.png")
                postproceso.postprocess(raw, final, "Noche", gamma=estudio.exposure(estudio.image_stats(raw)))
                results.append(final)
        chosen[person_id]["estilo"] = [str(path) for path in results]
        sheet([source] + results[0::2], folder / f"C_{person_id}_sin_grande.jpg", 300)   # el orden es d, grande
        sheet([source] + results[1::2], folder / f"C_{person_id}_con_grande.jpg", 300)
    return chosen


def grid_html(folder, chosen):
    rows = []
    for jpg in sorted(folder.glob("*.jpg")):
        rows.append(f"<h3>{jpg.stem}</h3><img src='{jpg.name}' style='max-width:100%'>")
    (folder / "grilla.html").write_text("<html><body style='background:#111;color:#ddd;font-family:sans-serif'>"
                                        "<h1>Piloto de referencias</h1>" + "".join(rows) + "</body></html>",
                                        encoding="utf-8")
    (folder / "elegidos.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--etapa", choices=("A", "B", "C", "todo"), default="todo")
    parser.add_argument("--carpeta", help="carpeta de un piloto anterior para seguirlo")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if ollama_loaded():
        raise SystemExit("Ollama tiene un modelo cargado: espera a que termine la tanda de prompts.")
    folder = Path(args.carpeta) if args.carpeta else ROOT / datetime.date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder / "elegidos.json"
    chosen = json.loads(saved.read_text(encoding="utf-8")) if saved.is_file() else {}
    data = universo.load()
    process = comfy.start(folder / "comfyui.log")
    try:
        if args.etapa in ("A", "todo"):
            chosen = stage_a(folder, data)
            grid_html(folder, chosen)
        if args.etapa in ("B", "todo"):
            chosen = stage_b(folder, data, chosen)
            grid_html(folder, chosen)
        if args.etapa in ("C", "todo"):
            chosen = stage_c(folder, data, chosen)
            grid_html(folder, chosen)
    finally:
        comfy.free()
        if process:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    print(f"Piloto listo: {folder / 'grilla.html'}", flush=True)


if __name__ == "__main__":
    main()
