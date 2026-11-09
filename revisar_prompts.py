"""Revision de los prompts antes de mandar a hacer las imagenes.

Por cada tema muestra quien es, donde esta, que hace y para que, el puntaje del productor y de continuidad, los
problemas conocidos que encuentre en el prompt (pantallas con cables, ojos cerrados, herramientas que no apuntan a
nada, texto legible, personas que no son las del universo) y con que otros temas de la tanda se parece. Deja un
informe en `Agente Frequency/revision_prompts.md`. Las imagenes se hacen recien cuando la revision esta bien.

Uso: python revisar_prompts.py 2048 2049 ...   (sin numeros: todos los temas con ficha)
"""
import argparse
import json
import re
import sys
from pathlib import Path

import agente_musical as agent
import equipo_imagen as equipo

# lo que el usuario ya rechazo en imagenes anteriores
KNOWN_PROBLEMS = {
    "cable enchufado a una pantalla": (r"\b(cable|wire|cord|plug)", r"\b(screen|monitor|crt|tv|television)\b"),
    "ojos cerrados": (r"\b(eyes (are |half )?closed|closed eyes|eyes shut)\b", None),
    "linterna o luz apuntando a nada": (r"\bflashlight\b", r"\b(at nothing|into nothing|into the dark|into darkness|empty)\b"),
    "mano contra el vidrio": (r"\b(palm|hand)s? (pressed |flat )?(against|on) (the )?(window|glass)\b", None),
    "reflejo magico u objeto flotando": (equipo.MAGIC, None),
    "frase abstracta que no se pinta": (equipo.ABSTRACT, None),
    "persona quieta frente a un aparato": (r"\b(stares?|staring|gazes?|gazing|looks?|looking) at (the |a )?(screen|monitor|crt|terminal)\b", None),
}


def found_problems(prompt):
    problems = []
    # "no text, no logos" (del estilo o del fotografo) es una negacion inofensiva, no una frase abstracta de la escena
    sentences = re.split(r"(?<=[.;!?])\s+", re.sub(equipo.NEGATED_WRITING, " ", prompt, flags=re.I))
    for name, (first, second) in KNOWN_PROBLEMS.items():  # las dos cosas en la misma oracion, no en todo el prompt
        if any(re.search(first, sentence, re.I) and (second is None or re.search(second, sentence, re.I))
               for sentence in sentences):
            problems.append(name)
    readable = re.search(equipo.READABLE, re.sub(equipo.NEGATED_WRITING, " ", prompt, flags=re.I), re.I)
    if readable:
        problems.append(f"texto legible ({readable.group(0)})")
    if re.search(equipo.MINORS, prompt, re.I):
        problems.append("posibles menores")
    return problems


def summary(folder):
    record = json.loads((folder / "ficha.json").read_text(encoding="utf-8"))
    team = (record.get("equipo") or {}).get("equipo") or {}
    saved = folder / "equipo"
    check = json.loads((saved / "continuidad.json").read_text(encoding="utf-8")) if (saved / "continuidad.json").is_file() else {}
    director = team.get("director") or {}
    return {"titulo": folder.name, "prompt": record.get("prompt_imagen", ""),
            "quien": " ".join((team.get("casting") or {}).get("prompt_visual", "").split()[:16]),
            "donde": (team.get("arte") or {}).get("lugar", ""), "que_hace": director.get("que_hace", ""),
            "escena": director.get("escena", (team.get("escritor") or {}).get("escena", "")),
            "veredicto_director": director.get("veredicto", ""),
            "productor": (record.get("equipo") or {}).get("productor") or {},
            "continuidad": {key: check.get(key) for key in ("repetida", "se_parece_a")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("semillas", nargs="*", type=int)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    folders = [path for path in sorted(agent.OUTPUT.glob("* 20*")) if (path / "ficha.json").is_file()
               and (not args.semillas or int(path.name.rsplit(" ", 1)[1]) in args.semillas)]
    shots = [summary(folder) for folder in folders]
    lines = ["# Revision de prompts antes de las imagenes", ""]
    to_fix = []
    for shot in shots:
        others = [{"titulo": other["titulo"], "escena": other["escena"]} for other in shots if other is not shot]
        alike = equipo.similar_shots(shot["escena"], others)
        problems = found_problems(shot["prompt"])
        scores = shot["productor"].get("puntajes", {})
        status = "OK" if not problems and not alike else "REVISAR"
        if status != "OK":
            to_fix.append(shot["titulo"])
        lines += [f"## {shot['titulo']}: {status}", "",
                  f"- **Quien:** {shot['quien']}", f"- **Donde:** {shot['donde']}",
                  f"- **Que hace y para que:** {shot['que_hace']} (director: {shot['veredicto_director']})",
                  f"- **Escena:** {shot['escena']}",
                  f"- **Productor:** {scores} aprobado={shot['productor'].get('aprobado')}",
                  f"- **Continuidad con temas anteriores:** {shot['continuidad']}",
                  f"- **Se parece dentro de la tanda a:** {[item['titulo'] for item in alike] or 'ninguno'}",
                  f"- **Problemas conocidos:** {problems or 'ninguno'}", ""]
        print(f"{shot['titulo']}: {status} | {shot['que_hace'][:90]} | problemas {problems} | parecidos "
              f"{[item['titulo'] for item in alike]}", flush=True)
    lines += ["## Para corregir antes de hacer imagenes", "", *(f"- {title}" for title in to_fix or ["ninguno"]), ""]
    report = agent.OUTPUT / "revision_prompts.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe: {report}. Para corregir: {to_fix or 'ninguno'}", flush=True)


if __name__ == "__main__":
    main()
