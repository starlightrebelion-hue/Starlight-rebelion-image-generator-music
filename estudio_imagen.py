"""Estudio de imagen reutilizable: brief -> prompt (equipo de agentes con Ollama) -> imagen (ComfyUI) -> acabado.

Todo lo que se decidio con el usuario el 2026-11-07 esta en DECISIONES y en los modulos que usa:
`agentes/` (los roles), `equipo_imagen.py` (corre los roles), `fondo_comfy.py` (Z-Image Turbo en ComfyUI),
`postproceso.py` (acabado) y `visual_estilo.STYLE_ZIMAGE` (estilo de dibujo).

Siempre en dos fases, para no tener Ollama (~39 GB) y Z-Image (~18 GB) cargados a la vez:
  1. prompts:  python estudio_imagen.py prompts briefs/*.json --salida carpeta
     Por cada brief escribe `<nombre>.prompt.json`. Al final descarga Ollama.
  2. imagenes: python estudio_imagen.py imagenes carpeta
     Por cada `*.prompt.json` (o `*.txt` con un prompt escrito a mano) genera 3 candidatas, rehace la mejor en
     grande, la postproduce y deja `<nombre>.png` (1920x1080). Al final libera y apaga ComfyUI.
  todo:        python estudio_imagen.py todo briefs/*.json --salida carpeta   (fase 1 y despues fase 2)

Brief (JSON): {"titulo", "idea", "emocion", "identidad" (si falta, la cyberpunk del canal), "concepto" (opcional),
"paleta" (para el acabado: Noche, Nebula, Plasma, Cristal, Cuantico, Supernova), "semilla" (opcional)}.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

import equipo_imagen as equipo
import fondo_comfy as comfy
import postproceso
import visual_estilo as visual

DEFAULT_MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"
DECISIONES = {
    "modelo_imagen": "Z-Image Turbo (9 pasos, cfg 1): look de OVA de los 90; Flux schnell y dev daban anime generico",
    "estilo": "visual_estilo.STYLE_ZIMAGE: OVA cyberpunk 80-90, caras maduras con la edad visible",
    "identidad": "equipo_imagen.CYBERPUNK: implantes, megaciudad con lluvia y neon, rebeldes contra corporaciones",
    "prompt": "largo y concreto (300-700 palabras), armado por el equipo de agentes/; la persona va primero",
    "candidatas": "3 semillas; se elige la mas vistosa (color, contraste y detalle medidos)",
    "grande": "la elegida se rehace a 2880x1632 (segunda pasada 1,5x, denoise .45) y se achica a 1920x1080",
    "acabado": "postproceso: bloom fuerte y difuso, negros suaves, color por paleta, aberracion, vineta, grano",
    "seguridad": "personas adultas, sin texto legible, sin personajes ni robots de obras existentes",
    "memoria": "dos fases: Ollama y ComfyUI nunca cargados a la vez",
    "sin_azar": "si Ollama no responde o un rol falla, ese prompt no se hace (nada por reglas)",
}
TRIES = 3
LIMITS = {"brillo": (.08, .42), "contraste": .12}
MIN_SCORE = .4   # la imagen del equipo que aprobo el usuario dio .53; debajo de esto conviene mirarla


# --- medicion de imagenes --------------------------------------------------------------------
def image_stats(path):
    """Medidas de 0 a ~1 sobre el PNG achicado (leido con ffmpeg): brillo, contraste, color y detalle."""
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=480:-2", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    rgb = np.frombuffer(data, dtype=np.uint8).astype(np.float32).reshape(-1, 480, 3) / 255
    luma = rgb @ np.array([.299, .587, .114], dtype=np.float32)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rg, yb = red - green, (red + green) / 2 - blue
    color = np.hypot(rg.std(), yb.std()) + .3 * np.hypot(rg.mean(), yb.mean())  # colorido de Hasler y Susstrunk
    detail = (np.abs(np.diff(luma, axis=0)).mean() + np.abs(np.diff(luma, axis=1)).mean()) * 4
    return {"brillo": round(float(luma.mean()), 3), "contraste": round(float(luma.std()), 3),
            "color": round(float(color), 3), "detalle": round(float(detail), 3)}


def image_ok(stats):
    low, high = LIMITS["brillo"]
    return low <= stats["brillo"] <= high and stats["contraste"] >= LIMITS["contraste"]


def attractiveness(stats):
    """Mas color, contraste y detalle es mas vistoso; fuera del rango de brillo se castiga."""
    score = stats["color"] + 1.5 * stats["contraste"] + .5 * stats["detalle"]
    return round(score if image_ok(stats) else score - 1, 3)


def exposure(stats):
    """Gamma para el acabado: las imagenes muy oscuras se levantan en los medios antes del bloom."""
    if stats["brillo"] < .10:
        return 1.5
    if stats["brillo"] < .15:
        return 1.25
    return 1.0


# --- fase 2: una imagen ----------------------------------------------------------------------
def full_prompt(prompt):
    """El prompt del equipo (o uno escrito a mano) mas el estilo de dibujo del canal, si no lo tiene ya."""
    prompt = equipo.plain(prompt)
    return prompt if visual.STYLE_ZIMAGE[:40] in prompt else f"{prompt} {visual.STYLE_ZIMAGE}"


def render_one(prompt, seed, folder, palette=None, name="fondo", tries=TRIES):
    """3 candidatas, la mejor en grande y postproducida. Devuelve (ruta final, candidatas medidas).

    ComfyUI tiene que estar prendido (comfy.start). Los archivos se nombran con un resumen del prompt: si el prompt
    cambia, se generan imagenes nuevas; si no, se reusan.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    prompt = full_prompt(prompt)
    tag = hashlib.sha1(prompt.encode()).hexdigest()[:6]
    candidates = []
    for attempt in range(tries):
        target = folder / f"{name} {tag} {attempt + 1}.png"
        if not target.is_file():
            comfy.generate(prompt, seed + attempt * 1000, target, model="zimage")
        stats = image_stats(target)
        candidates.append({"archivo": target.name, **stats, "pasa": image_ok(stats), "puntaje": attractiveness(stats)})
    best = max(candidates, key=lambda item: item["puntaje"])
    for item in candidates:
        item["elegido"] = item is best
    chosen = candidates.index(best)
    big = folder / f"{name} {tag} {chosen + 1} grande.png"
    if not big.is_file():
        comfy.generate(prompt, seed + chosen * 1000, big, model="zimage", hires=True)
    final = postproceso.postprocess(big, folder / f"{name}.png", palette, gamma=exposure(image_stats(big)))
    return final, candidates


# --- fase 1: prompts -------------------------------------------------------------------------
def slug(text):
    return re.sub(r"[^\w-]+", "_", text.strip().lower()).strip("_")[:60] or "imagen"


def write_prompts(briefs, folder, model=DEFAULT_MODEL):
    """El equipo escribe un prompt por brief. Devuelve las rutas escritas; los que fallan se avisan y no se escriben."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    try:
        for number, brief in enumerate(briefs):
            brief = {"identidad": equipo.CYBERPUNK, **brief}
            seed = int(brief.get("semilla", number + 1))
            name = slug(brief.get("titulo", f"imagen {number + 1}"))
            # cada departamento queda en <carpeta>/<nombre>/equipo/ para poder mejorar solo una parte despues
            result = equipo.make(brief, model, seed=seed, unload_at_end=False, folder=folder / name,
                                 redo=brief.get("mejorar"))
            if not result["prompt"]:
                skipped.append(name)
                print(f"{name}: sin prompt ({'; '.join(result['registro'][-2:])})", flush=True)
                continue
            target = folder / f"{name}.prompt.json"
            target.write_text(json.dumps({"brief": brief, "semilla": seed, "prompt": result["prompt"],
                                          "productor": result["productor"], "equipo": result["equipo"],
                                          "registro": result["registro"]}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            written.append(target)
            print(f"{name}: prompt de {len(result['prompt'].split())} palabras, productor {result['productor']}",
                  flush=True)
    finally:
        equipo.unload(model)  # una sola descarga al final de la fase
    if skipped:
        print(f"Sin prompt: {skipped}", flush=True)
    return written


def render_folder(folder):
    """Fase 2: una imagen por cada *.prompt.json o *.txt de la carpeta."""
    folder = Path(folder)
    jobs = []
    for path in sorted(folder.glob("*.prompt.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs.append((path.name.removesuffix(".prompt.json"), data["prompt"], data.get("semilla", 1),
                     data.get("brief", {}).get("paleta")))
    for path in sorted(folder.glob("*.txt")):
        jobs.append((path.stem, path.read_text(encoding="utf-8"), 1, None))
    process = comfy.start(folder / "comfyui.log")
    results = []
    try:
        for name, prompt, seed, palette in jobs:
            final, candidates = render_one(prompt, seed, folder, palette, name)
            best = max(item["puntaje"] for item in candidates)
            note = "" if best >= MIN_SCORE else "  (puntaje bajo: mirarla)"
            print(f"{name}: {final.name}, puntaje {best}{note}", flush=True)
            results.append((final, candidates))
    finally:
        comfy.call("/free", {"unload_models": True, "free_memory": True}, timeout=60)
        if process:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fase", choices=("prompts", "imagenes", "todo"))
    parser.add_argument("entradas", nargs="+", help="briefs .json (prompts, todo) o la carpeta (imagenes)")
    parser.add_argument("--salida", help="carpeta de los prompts y las imagenes")
    parser.add_argument("--modelo", default=DEFAULT_MODEL)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.fase == "imagenes":
        render_folder(args.entradas[0])
        return
    if not args.salida:
        parser.error("--salida es obligatoria para prompts y todo")
    briefs = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.entradas]
    write_prompts(briefs, args.salida, args.modelo)
    if args.fase == "todo":
        render_folder(args.salida)


if __name__ == "__main__":
    main()
