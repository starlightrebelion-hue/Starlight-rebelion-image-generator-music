"""Agente musical: arma un tema entero desde una semilla. Lo lanza agente_musical.bat.

Los dados eligen tonalidad, escala, ensamble, estructura, lead y densidad, porque un modelo local
tiende a repetir sus favoritos; Ollama (o el azar) decide el resto y
Python escribe las notas. Siempre deja .mid y ficha; con FL disponible tambien .flp, WAV y MP3.
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import build_starlight as builder
import compositor
import estilo_frequency as style
import flbridge as fl
import mix_starlight as mixer
import render_starlight as session
import video_espectral as video
import visual_estilo as visual

ROOT = Path(__file__).resolve().parent
ROLE = ROOT / "agente_frequency.txt"
BASE = ROOT / "presets/base_fl.flp"
OUTPUT = ROOT / "Agente Frequency"
OLLAMA = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"


class OllamaUnavailable(RuntimeError):
    """Ollama no contesto: el tema no se arma (no hay plan B al azar)."""


def options(scale):
    """Valores permitidos para lo que decide el motor, segun la escala que salio en los dados."""
    return {
        "progresion_verso": list(style.VERSES[scale]),
        "progresion_coro": list(style.CHORUSES[scale]), "contorno": list(style.CONTOURS),
        "melodia": list(style.MELODY_POOLS),
        "efecto": list(style.LEAD_EFFECTS), "acordes": list(style.CHORD_STYLES), "reverb": list(style.DECAYS),
        "delay": list(style.SENDS),
    }


def roll_dice(rng):
    return {"tonica": rng.choice(list(style.TONICS)), "escala": rng.choices(list(style.SCALE_WEIGHTS), list(style.SCALE_WEIGHTS.values()))[0],
            "ensamble": rng.choice(list(style.ENSEMBLES)), "estructura": rng.choice(list(style.STRUCTURES)),
            "lead": rng.choice(list(style.LEADS)), "densidad": rng.choice(list(style.RHYTHMS)),
            "imagen": rng.choice(style.IMAGES),
            # Ollama elegia siempre 100 BPM, arpegio cascada, bajo pulso y bateria seca: ahora salen en los dados
            # y el modelo arma el resto alrededor.
            "bpm": rng.choice(style.TEMPOS), "arpegio": rng.choice(list(style.ARPS)),
            "bajo": rng.choice(list(style.BASS_STYLES)), "bateria": rng.choice(list(style.DRUM_STYLES))}


def random_choices(rng, dice):
    plan = {key: rng.choice(values) for key, values in options(dice["escala"]).items()}
    plan["titulo"] = f"{rng.choice(style.TITLE_WORDS[0])} {rng.choice(style.TITLE_WORDS[1])}"
    plan["idea"] = "Elegido al azar dentro de la estetica."
    return plan


def ask_ollama(dice, seed, model, taken=(), recent=None):
    allowed = options(dice["escala"])
    properties = {key: {"enum": values} for key, values in allowed.items()}
    properties.update({"titulo": {"type": "string"}, "idea": {"type": "string"}})
    schema = {"type": "object", "properties": properties, "required": list(properties)}
    prompt = (f"{ROLE.read_text(encoding='utf-8')}\n\nDados ya tirados: {json.dumps(dice, ensure_ascii=False)}\n"
              f"Opciones permitidas: {json.dumps(allowed, ensure_ascii=False)}\n"
              f"Titulos ya usados, no repitas ninguno ni lo extiendas: {sorted(taken)}\n"
              f"Palabras gastadas, no las uses en el titulo: {worn_words(taken)}\n"
              f"Lo que eligieron los ultimos temas (opcion: veces): {json.dumps(recent or {}, ensure_ascii=False)}. "
              "Varia: no repitas una opcion muy usada salvo que la imagen la pida de verdad.\n"
              "Devolve el plan completo en JSON, con titulo e idea.")
    body = {"model": model, "prompt": prompt, "stream": False, "format": schema, "keep_alive": 0,
            "options": {"temperature": .9, "seed": seed, "num_predict": 500, "num_ctx": 8192}}
    request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(json.loads(response.read())["response"])


def validated(answer, rng, dice):
    """Lo que el motor no haya elegido bien se completa al azar: el plan siempre queda dentro del estilo."""
    plan = random_choices(rng, dice)
    fixed = []
    for key, values in options(dice["escala"]).items():
        if answer.get(key) in values:
            plan[key] = answer[key]
        else:
            fixed.append(key)
    for key in ("titulo", "idea"):
        if str(answer.get(key, "")).strip():
            plan[key] = str(answer[key]).strip()
            if key == "titulo" and plan[key].islower():  # "foglight echo" -> "Foglight Echo"
                plan[key] = plan[key].title()
        else:
            fixed.append(key)
    return plan, fixed


VARIETY_WINDOW = 12   # temas anteriores que se miran
VARIETY_LIMIT = .35   # si una opcion ya salio en mas de esta parte de esos temas, se cambia


def recent_plans(seed, window=VARIETY_WINDOW):
    plans = []
    for path in OUTPUT.glob("*/*.json"):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(plan.get("semilla"), int) and plan["semilla"] < seed and "escala" in plan:
            plans.append(plan)
    return sorted(plans, key=lambda plan: plan["semilla"])[-window:]


def usage(recent, scale):
    return {key: {str(value): sum(str(plan.get(key)) == str(value) for plan in recent) for value in values}
            for key, values in options(scale).items()}


def balance(plan, recent, rng):
    """Ollama tiende a repetir lo mismo en cada tema: lo que ya salio demasiado se cambia por lo menos usado."""
    changed = []
    if len(recent) < 4:
        return changed
    counts = usage(recent, plan["escala"])
    for key, values in options(plan["escala"]).items():
        if len(values) > 1 and counts[key][str(plan[key])] > len(recent) * VARIETY_LIMIT:
            least = min(counts[key].values())
            plan[key] = rng.choice([value for value in values if counts[key][str(value)] == least])
            changed.append(f"variedad: {key}")
    return changed


def used_titles(seed):
    """Titulos de los temas ya hechos (salvo el de esta misma semilla)."""
    titles = set()
    for path in OUTPUT.glob("*/*.json"):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if plan.get("semilla") != seed and plan.get("titulo"):
            titles.add(plan["titulo"].strip().lower())
    return titles


def worn_words(titles, limit=3):
    """Palabras que ya estan en `limit` titulos o mas (Pulse, Neon...): los titulos se parecen todos."""
    counts = {}
    for title in titles:
        for word in set(title.lower().split()):
            counts[word] = counts.get(word, 0) + 1
    return sorted(word for word, count in counts.items() if count >= limit)


def repeats(title, used):
    """Igual a uno ya usado, o uno contiene al otro ("Red Dawn" y "Red Dawn Port")."""
    title = title.strip().lower()
    return any(title == other or title.startswith(other + " ") or other.startswith(title + " ") for other in used)


def unique_title(plan, rng, used):
    if not repeats(plan["titulo"], used):
        return False
    free = [f"{a} {b}" for a in style.TITLE_WORDS[0] for b in style.TITLE_WORDS[1] if not repeats(f"{a} {b}", used)]
    plan["titulo"] = rng.choice(free) if free else f"{plan['titulo']} {plan['semilla']}"
    return True


def make_plan(seed, engine, model):
    rng = random.Random(seed)
    dice = roll_dice(rng)
    used, fixed = "azar", []
    plan = random_choices(rng, dice)
    if engine == "ollama":
        counts = usage(recent_plans(seed), dice["escala"])
        recent = {key: {value: n for value, n in values.items() if n} for key, values in counts.items()}
        for attempt in (1, 2, 3):  # si la GPU esta ocupada Ollama puede no contestar: se espera y se reintenta
            try:
                plan, fixed = validated(ask_ollama(dice, seed, model, used_titles(seed), recent), rng, dice)
                used = model
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
                print(f"Ollama no respondio ({error}), intento {attempt}.", flush=True)
                if attempt < 3:
                    time.sleep(60)
        else:
            # el usuario no quiere temas al azar cuando Ollama falla: ese tema no se arma
            raise OllamaUnavailable(f"Ollama no respondio en 3 intentos para la semilla {seed}")
    plan = {**dice, **plan, "semilla": seed, "motor": used, "corregido": fixed}
    if engine == "ollama":
        fixed += balance(plan, recent_plans(seed), random.Random(f"variedad-{seed}"))
    plan["ambiente"] = random.Random(f"ambiente-{seed}").choice(style.AMBIENTS[plan["ensamble"]])
    if unique_title(plan, random.Random(seed), used_titles(seed)):
        fixed.append("titulo repetido")
    return plan


def file_name(plan):
    title = re.sub(r"[^\w -]", "", plan["titulo"]).strip() or "Sin titulo"
    return f"{title} {plan['semilla']}"


def fl_is_free():
    """FL se puede cerrar solo si no hay cambios sin guardar."""
    if not fl.fl_running():
        return True
    try:
        return fl.batch([("general", "getChangedFlag")])[0].get("value") == 0
    except Exception:
        return False


def sounds_of(plan):
    sounds = dict(style.ENSEMBLES[plan["ensamble"]]["sonidos"])
    sounds[builder.MELODY] = style.LEADS[plan["lead"]][0]
    return sounds


def faders_of(plan):
    levels = style.ENSEMBLES[plan["ensamble"]]["niveles"]
    return tuple(min(1.0, level * 10 ** (levels.get(channel, 0) / 40)) for channel, level in enumerate(mixer.FADERS))


def produce(plan, composed, project, export=True):
    effect = style.LEAD_EFFECTS[plan["efecto"]]
    table = dict(builder.routes_for(plan["reverb_envio"], plan["delay"]))
    builder.assemble(BASE, project, sounds_of(plan), effect, table, composed.patterns, composed.clips,
                     ambient=plan.get("ambiente", True))
    session.open_fl(project)
    mixer.apply(project, composed.names, effect, style.LEADS[plan["lead"]][1], plan["reverb"],
                tempo=plan["bpm"], faders=faders_of(plan))
    session.close_fl()
    if not export:
        return None
    wav = fl.render(project, "wav", 900)
    mp3 = wav.with_suffix(".mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "320k", str(mp3)], check=True)
    return mp3


def measure(path):
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                             "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = result.stderr[result.stderr.rfind("Summary:"):]
    loudness = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return {"lufs": float(loudness.group(1)), "pico_dbfs": float(peak.group(1))}


def one(seed, args):
    started = time.time()
    plan = make_plan(seed, args.motor, args.modelo)
    plan["reverb_envio"] = .25 + .35 * style.DECAYS.index(plan["reverb"]) / (len(style.DECAYS) - 1)
    composed = compositor.compose(plan, seed)
    folder = OUTPUT / file_name(plan)
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / file_name(plan)
    compositor.write_midi(stem.with_suffix(".mid"), composed, plan["bpm"])
    plan["compases"] = composed.bars
    plan["duracion_seg"] = round(composed.bars * 240 / plan["bpm"])
    print(f"[{seed}] {plan['titulo']} | {plan['tonica']} {plan['escala']}, {plan['bpm']} BPM, {plan['ensamble']}, "
          f"{plan['estructura']}, {plan['lead']} | {plan['motor']}", flush=True)
    print(f"    {plan['idea']}", flush=True)
    if not args.sin_fl:
        mp3 = produce(plan, composed, stem.with_suffix(".flp"), not args.sin_exportar)
        if mp3:
            plan["medidas"] = measure(mp3)
            print(f"    {plan['medidas']}", flush=True)
        if mp3 and args.video:
            video.make(mp3, seed, visual.BY_ENSEMBLE[plan["ensamble"]], plan["imagen"], stem.with_suffix(".mp4"), ficha=folder)
    stem.with_suffix(".json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    listo en {time.time() - started:.0f} s: {folder}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Genera temas de synthwave desde una semilla.")
    parser.add_argument("--n", type=int, default=1, help="cuantos temas hacer")
    parser.add_argument("--semilla", type=int, help="repite un tema; si no se da, sale al azar")
    parser.add_argument("--motor", choices=("ollama", "azar"), default="ollama")
    parser.add_argument("--modelo", default=DEFAULT_MODEL)
    parser.add_argument("--sin-fl", action="store_true", help="solo .mid y ficha, sin abrir FL")
    parser.add_argument("--sin-exportar", action="store_true", help="arma el .flp en FL pero no exporta WAV ni MP3")
    parser.add_argument("--video", action="store_true", help="tambien arma el video espectral")
    args = parser.parse_args()
    if args.video and args.sin_fl:
        parser.error("--video necesita el audio de FL: no se puede con --sin-fl.")
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.sin_fl:
        if not shutil.which("ffmpeg"):
            raise SystemExit("Falta ffmpeg en el PATH.")
        if not fl_is_free():
            raise SystemExit("FL esta abierto con cambios sin guardar. Guarda y cerralo, o usa --sin-fl.")
        session.close_fl()
    first = args.semilla if args.semilla is not None else random.randrange(1, 1_000_000)
    failed = []
    without_ollama = []
    for seed in range(first, first + args.n):
        # FL a veces tarda mas de la cuenta en contestar por el tunel: se reintenta una vez y si no, sigue la tanda
        for attempt in (1, 2):
            try:
                one(seed, args)
                break
            except OllamaUnavailable as error:
                print(f"[{seed}] no se armo: {error}", flush=True)
                without_ollama.append(seed)
                break
            except (fl.FLError, SystemExit) as error:
                print(f"[{seed}] fallo el intento {attempt}: {error}", flush=True)
                if not args.sin_fl:
                    session.close_fl()
                    time.sleep(5)
        else:
            failed.append(seed)
        if without_ollama[-2:] == [seed - 1, seed]:
            print("Ollama fallo en dos temas seguidos: freno la tanda.", flush=True)
            break
    if without_ollama:
        print(f"Temas sin armar porque Ollama no respondio: {without_ollama}", flush=True)
    if failed or without_ollama:
        print(f"Temas que fallaron dos veces: {failed}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
