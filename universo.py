"""Universo del canal: personajes y lugares propios que se repiten entre temas (formato del universo de Doble Fondo).

  universo/universo.json
    personajes  {id: {nombre, alias, arquetipo, genero, edad, aspecto, vestuario, implantes, objetos, oficio, historia,
                      deseo, miedo, contradiccion, secreto, gestos, lugares, relaciones, arco: [{tema, titulo, que_hizo, lugar}]}}
    locaciones  {id: {nombre, prompt, luz, atmosfera, utileria, que_pasa, acciones}}
    canon       [{tema, titulo, hecho}]   lo que ya paso (no se contradice)
    reglas      como es este mundo

Cada tema recibe un personaje, rotando para que nunca repita el del tema anterior y el elenco se reparta parejo. Cada
vez que un personaje vuelve, va a otro de sus lugares y hace otro de sus gestos, y el equipo de imagen ve su arco
(lo que le paso en los temas anteriores) para que la historia siga.

Personajes ORIGINALES sobre arquetipos del cyberpunk: ninguno copia a un personaje de una obra existente.

  python universo.py listar
  python universo.py elenco 2048 2087        (quien sale en cada tema)
"""
import argparse
import json
import random
import sys
from pathlib import Path

FILE = Path(__file__).resolve().parent / "universo" / "universo.json"
BASE_SEED = 2048   # el primer tema de la tanda: la rotacion arranca aca


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def save(data):
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rotation(data):
    """Orden fijo de los personajes (mezclado una vez), para repartirlos parejo y sin repetir seguidos."""
    ids = sorted(data["personajes"])
    random.Random("universo").shuffle(ids)
    return ids


STOP = set("""a an the of in on at to with from into onto over under by and or his her their its while like
up down out off one two hand hands light lamp rain glass night dark small old big huge someone stranger""".split())


def _words(text):
    return {word.strip(".,;:'").lower() for word in text.split() if len(word) > 3} - STOP


def _fit(gesture, place):
    """Cuantas palabras del gesto aparecen en el lugar (su descripcion, utileria y acciones)."""
    place_words = _words(place["prompt"] + " " + " ".join(place.get("utileria", [])) + " " + " ".join(place["acciones"]))
    return len(_words(gesture) & place_words)


def _gesture_for(person, place, used):
    """El gesto del personaje que mejor encaja en el lugar y que todavia no hizo (None si ninguno encaja)."""
    options = [gesture for gesture in person["gestos"] if gesture not in used] or person["gestos"]
    best = max(options, key=lambda gesture: _fit(gesture, place))
    return best if _fit(best, place) >= 1 else None


def plan(until, data=None):
    """El elenco tema por tema desde BASE_SEED hasta `until`: rota personajes, no repite lugares de los ultimos tres
    temas ni el mismo lugar o gesto de un personaje."""
    data = data or load()
    order = rotation(data)
    result, recent_places = {}, []
    places_by_person, gestures_by_person = {}, {}
    for seed in range(BASE_SEED, until + 1):
        turn = seed - BASE_SEED
        person_id = order[turn % len(order)]
        person = data["personajes"][person_id]
        mine = places_by_person.setdefault(person_id, [])
        candidates = ([place for place in person["lugares"] if place not in mine and place not in recent_places[-3:]]
                      + [place for place in person["lugares"] if place in mine and place not in recent_places[-3:]]
                      + person["lugares"])
        used = gestures_by_person.setdefault(person_id, [])
        # el primer lugar donde alguno de sus gestos tiene sentido; si en ninguno, su mejor par lugar-gesto
        pairs = [(place, _gesture_for(person, data["locaciones"][place], used)) for place in dict.fromkeys(candidates)]
        place_id, gesture = next(((place, gesture) for place, gesture in pairs if gesture), (None, None))
        if not place_id:
            place_id = candidates[0]
            gesture = max(person["gestos"], key=lambda g: _fit(g, data["locaciones"][place_id]))
        mine.append(place_id)
        gestures_by_person[person_id].append(gesture)
        recent_places.append(place_id)
        result[seed] = {"id": person_id, "aparicion": turn // len(order) + 1, "lugar_id": place_id, "gesto": gesture}
    return result


ASSIGNMENTS = FILE.parent / "asignaciones.json"


def frozen():
    """Elenco congelado por tema {semilla: {id, lugar_id, gesto, objeto}}: editar el universo no lo reordena."""
    return json.loads(ASSIGNMENTS.read_text(encoding="utf-8")) if ASSIGNMENTS.is_file() else {}


def _object_for(person, scene):
    """El objeto de firma que la escena usa (por palabras en comun), o None."""
    scene_words = _words(scene)
    scored = [(len(_words(text) & scene_words), index) for index, text in enumerate(person.get("objetos", []))]
    best = max(scored, default=(0, None))
    return best[1] if best[0] >= 2 else None


def freeze(seed, scene="", data=None):
    """Congela el elenco de un tema (si ya estaba congelado, lo devuelve sin cambiarlo)."""
    assignments = frozen()
    if str(seed) in assignments:
        return assignments[str(seed)]
    data = data or load()
    chosen = plan(seed, data)[seed]
    person = data["personajes"][chosen["id"]]
    chosen = {**chosen, "objeto": _object_for(person, scene or chosen["gesto"])}
    assignments[str(seed)] = chosen
    ASSIGNMENTS.write_text(json.dumps(assignments, ensure_ascii=False, indent=2), encoding="utf-8")
    return chosen


# un lugar se describe vacio: sin personas, sin lo que hacen y sin estados de animo de alguien (el usuario, 2026-11-08)
PLACE_PEOPLE = (r"\b(figures?|crowds?|people|persons?|passengers?|customers?|bartenders?|cooks?|strikers?|workers?|"
                r"vendors?|dealers? (?:haggling|selling)|guards?|patients?(?!['’]s)|man|woman|men|women|someone|somebody|"
                r"a person|hiding|suspicion|tension|trapped|secret|anonymous|conversations?|intimate|waiting for)\b")
PLACE_FIELDS = ("prompt", "luz", "atmosfera", "utileria")


def place_problems(text):
    """Palabras de personas o acciones en la descripcion de un lugar ([] si esta limpia)."""
    import re
    text = " ".join(text) if isinstance(text, list) else str(text or "")
    return sorted({match.group(0).lower() for match in re.finditer(PLACE_PEOPLE, text, re.I)})


def set_frozen(seed, data=None, **changes):
    """Cambia a mano el elenco congelado de un tema (StoryForge: otro personaje, lugar, gesto u objeto).
    Valida contra el universo; la toma queda desactualizada por su receta."""
    data = data or load()
    assignments = frozen()
    current = dict(assignments.get(str(seed)) or freeze(seed, data=data))
    if "id" in changes and changes["id"] not in data["personajes"]:
        raise ValueError(f"No existe el personaje {changes['id']}")
    if "lugar_id" in changes and changes["lugar_id"] not in data["locaciones"]:
        raise ValueError(f"No existe el lugar {changes['lugar_id']}")
    person = data["personajes"][changes.get("id", current["id"])]
    if changes.get("objeto") is not None and not 0 <= int(changes["objeto"]) < len(person.get("objetos", [])):
        raise ValueError("Ese objeto no es del personaje")
    if "id" in changes and changes["id"] != current["id"] and "objeto" not in changes:
        changes["objeto"] = None   # el objeto era del personaje anterior
    current.update({key: value for key, value in changes.items() if key in ("id", "lugar_id", "gesto", "objeto")})
    assignments = frozen()
    assignments[str(seed)] = current
    ASSIGNMENTS.write_text(json.dumps(assignments, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def update(kind, item_id, field, value):
    """Cambia un texto del universo y guarda el anterior en historial_texto (StoryForge, al rechazar con nota)."""
    data = load()
    group = data["personajes" if kind == "personaje" else "locaciones"]
    item = group[item_id]
    item.setdefault("historial_texto", []).append({"campo": field, "valor": item.get(field)})
    item[field] = value
    save(data)
    return item


def cast(seed, data=None):
    """Personaje, lugar y gesto de este tema, con el arco del personaje hasta ahora (respeta el elenco congelado)."""
    data = data or load()
    chosen = frozen().get(str(seed)) or plan(seed, data)[seed]
    person = data["personajes"][chosen["id"]]
    return {**chosen, "personaje": person, "lugar": data["locaciones"][chosen["lugar_id"]],
            "arco": [step for step in person.get("arco", []) if step.get("tema") != seed]}


def register(seed, title, person_id, what, place_id):
    """Agrega al arco del personaje lo que hizo en este tema (rehacer el tema reemplaza esa entrada)."""
    data = load()
    person = data["personajes"][person_id]
    arc = [step for step in person.get("arco", []) if step.get("tema") != seed]
    arc.append({"tema": seed, "titulo": title, "que_hizo": what, "lugar": place_id})
    person["arco"] = sorted(arc, key=lambda step: step["tema"])
    canon = [fact for fact in data.get("canon", []) if fact.get("tema") != seed]
    canon.append({"tema": seed, "titulo": title, "hecho": f"{person['nombre']}: {what}"})
    data["canon"] = sorted(canon, key=lambda fact: fact["tema"])
    save(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", choices=("listar", "elenco"))
    parser.add_argument("desde", nargs="?", type=int, default=BASE_SEED)
    parser.add_argument("hasta", nargs="?", type=int, default=BASE_SEED + 39)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    data = load()
    if args.accion == "listar":
        for person_id, person in data["personajes"].items():
            print(f"{person['nombre']} ({person['alias']}), {person['edad']}: {person['arquetipo']}. "
                  f"Apariciones: {len(person.get('arco', []))}")
        return
    for seed in range(args.desde, args.hasta + 1):
        chosen = cast(seed, data)
        print(f"{seed}: {chosen['personaje']['nombre']} (vez {chosen['aparicion']}) en {chosen['lugar']['nombre']}: "
              f"{chosen['gesto']}")


if __name__ == "__main__":
    main()
