"""Guion tecnico de StoryForge: planta vista desde arriba, regla de los 180 grados y puesta en pantalla de cada plano.

Port de las funciones puras de Doble Fondo (C:\\canal starlight rebelion\\scripts\\decoupage.py) con la misma
convencion: planta de 0 a 10, x hacia la derecha, y del fondo (0) al frente (10); la camara suele estar abajo.

  <tema>/toma/planta.json  {"personajes": {id: {x, y, mira, nombre}}, "objetos": [{id, nombre, x, y}],
                            "eje": [id_a, id_b], "planos": [{toma, tipo, camara: {x, y}, apunta_a, cruza_eje}]}

`bloqueo_texto()` da la puesta en ingles ("staging: the person on the left third of frame facing right") que entra
en el prompt de Kontext de la toma y en su receta: mover la camara o la persona deja la toma desactualizada.
La planta inicial se arma sin azar desde el fotografo (plano y angulo) y el elenco congelado; si falta el dato, la
planta queda vacia para armarla a mano en StoryForge.
"""
import json
import math
import re
import unicodedata
from pathlib import Path

# distancia de camara (en unidades de planta) segun el tamano del plano del fotografo
DISTANCE = (("extreme close", 1.2), ("medium close", 2.4), ("close", 1.8), ("medium", 3.0), ("cowboy", 3.4),
            ("american", 3.4), ("full", 4.2), ("wide", 5.0), ("establishing", 5.5), ("long", 5.0))
# hacia donde gira la camara alrededor de la persona segun el angulo (grados; 0 = de frente, desde abajo)
TURN = (("profile", 90), ("side", 80), ("three-quarter", 40), ("3/4", 40), ("over the shoulder", 150),
        ("from behind", 180), ("back", 170), ("left", -30), ("right", 30))
SHOT_TYPES = ("PG", "PC", "PA", "PM", "PP", "PPP", "escorzo", "inserto", "POV")


def _n(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def _lado(a, b, c):
    """>0 si c esta a la izquierda de la recta a->b."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _espejar(p, a, b):
    """Refleja el punto p respecto de la recta a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy or 1.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length
    px, py = a[0] + t * dx, a[1] + t * dy
    return (round(2 * px - p[0], 2), round(2 * py - p[1], 2))


def _pos(d, name):
    """Posicion de un personaje o de un objeto (por id o por nombre)."""
    people = d.get("personajes", {})
    item = people.get(name) or next((v for k, v in people.items() if _n(k) == _n(name)), None)
    if not item:
        item = next((o for o in d.get("objetos", []) if o.get("id") == name or _n(o.get("nombre")) == _n(name)), None)
    return (float(item["x"]), float(item["y"])) if item else None


def corregir_eje(d):
    """Regla de los 180: todas las camaras del lado del eje que eligio la mayoria (o el plano general).
    Devuelve las tomas corregidas (las espeja respecto del eje)."""
    axis = d.get("eje") or []
    if len(axis) < 2:
        return []
    a, b = _pos(d, axis[0]), _pos(d, axis[1])
    if not a or not b or a == b:
        return []
    cameras = [(shot, (float(shot["camara"]["x"]), float(shot["camara"]["y"]))) for shot in d.get("planos", [])
               if isinstance(shot.get("camara"), dict)]
    sides = [math.copysign(1, _lado(a, b, c)) for shot, c in cameras
             if abs(_lado(a, b, c)) > 1e-6 and not shot.get("cruza_eje")]
    if not sides:
        return []
    general = next((math.copysign(1, _lado(a, b, c)) for shot, c in cameras
                    if shot.get("tipo") == "PG" and abs(_lado(a, b, c)) > 1e-6), None)
    good = general if general is not None else (1 if sum(sides) >= 0 else -1)
    d["lado"] = good
    fixed = []
    for shot, c in cameras:
        if shot.get("cruza_eje") or abs(_lado(a, b, c)) < 1e-6:
            continue
        if math.copysign(1, _lado(a, b, c)) != good:
            x, y = _espejar(c, a, b)
            shot["camara"] = {"x": max(0, min(10, x)), "y": max(0, min(10, y))}
            fixed.append(shot["toma"])
    return fixed


def _apunta(d, shot):
    target = [p for p in (_pos(d, name) for name in shot.get("apunta_a", [])) if p]
    if not target:
        target = [p for p in (_pos(d, name) for name in d.get("personajes", {})) if p]
    if not target:
        return (5.0, 5.0)
    return (sum(p[0] for p in target) / len(target), sum(p[1] for p in target) / len(target))


def direccion_en_pantalla(d, shot, in_frame):
    """{nombre: {lado, mira, x, dist}} vistos desde la camara del plano."""
    if not isinstance(shot.get("camara"), dict):
        return {}
    c = (float(shot["camara"]["x"]), float(shot["camara"]["y"]))
    t = _apunta(d, shot)
    f = (t[0] - c[0], t[1] - c[1])
    norm = math.hypot(*f) or 1.0
    out = {}
    for name in in_frame:
        p = _pos(d, name)
        if not p:
            continue
        lateral = (f[0] * (p[1] - c[1]) - f[1] * (p[0] - c[0])) / norm   # >0 = a la derecha del cuadro
        out[name] = {"x": lateral, "dist": math.hypot(p[0] - c[0], p[1] - c[1])}
    if not out:
        return {}
    xs = sorted(v["x"] for v in out.values())
    people = d.get("personajes", {})
    for name, v in out.items():
        if len(out) == 1:
            v["lado"] = "center" if abs(v["x"]) < 0.8 else ("right" if v["x"] > 0 else "left")
            q = _pos(d, (people.get(name) or {}).get("mira", ""))
            if q and v["lado"] == "center":   # aire hacia donde mira: queda corrido al tercio contrario
                lat_q = (f[0] * (q[1] - c[1]) - f[1] * (q[0] - c[0])) / norm
                v["lado"] = "left third" if lat_q > v["x"] else "right third"
        else:
            v["lado"] = "left" if v["x"] == xs[0] else ("right" if v["x"] == xs[-1] else "center")
        look = (people.get(name) or {}).get("mira")
        q = _pos(d, look) if look else None
        if q:
            lat_q = (f[0] * (q[1] - c[1]) - f[1] * (q[0] - c[0])) / norm
            p = _pos(d, name)
            toward = (c[0] - p[0]) * (q[0] - p[0]) + (c[1] - p[1]) * (q[1] - p[1])
            v["mira"] = ("right" if lat_q > v["x"] + 0.2 else
                         ("left" if lat_q < v["x"] - 0.2 else ("camera" if toward > 0 else "away")))
    return out


def bloqueo_texto(d, shot, in_frame, labels=None):
    """Puesta en ingles para el prompt. `labels` cambia ids por como los nombra el prompt ("the person")."""
    labels = labels or {}
    screen = direccion_en_pantalla(d, shot, in_frame)
    name = lambda key: labels.get(key, key)  # noqa: E731
    parts = []
    if shot.get("tipo") in ("escorzo", "contraplano") and len(screen) >= 2:
        near = min(screen, key=lambda key: screen[key]["dist"])
        parts.append(f"over the shoulder of {name(near)} (back to camera, blurred foreground, frame {screen[near]['lado']})")
        for key in screen:
            if key != near:
                parts.append(f"{name(key)} facing the camera on the {screen[key]['lado']} of frame")
    else:
        for key, v in screen.items():
            look = {"left": "facing left", "right": "facing right", "camera": "turned toward camera",
                    "away": "turned away from camera"}.get(v.get("mira", ""), "")
            parts.append(f"{name(key)} on the {v['lado']} of frame" + (f" {look}" if look else ""))
    return "staging: " + "; ".join(parts) if parts else ""


# --- Ejemplo 1: planta de un tema -------------------------------------------------------------------
def path_for(song_folder):
    return Path(song_folder) / "toma" / "planta.json"


def load(song_folder):
    path = path_for(song_folder)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save(song_folder, d):
    corregir_eje(d)
    path = path_for(song_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return d


def shot_type(plano):
    text = _n(plano)
    for key, code in (("extreme close", "PPP"), ("medium close", "PM"), ("close", "PP"), ("medium", "PM"), ("cowboy", "PA"),
                      ("american", "PA"), ("full", "PC"), ("wide", "PG"), ("establishing", "PG"), ("long", "PG")):
        if key in text:
            return code
    return "PM"


def initial(cast, person, photographer, object_text=None):
    """Planta inicial sin azar: persona al centro, objeto a su derecha si la escena lo usa, camara al frente a la
    distancia del plano y girada segun el angulo del fotografo. None si falta el plano del fotografo."""
    plano = (photographer or {}).get("plano")
    if not plano or not cast:
        return None
    text = _n(f"{plano} {photographer.get('angulo', '')}")
    distance = next((value for key, value in DISTANCE if key in text), 3.0)
    turn = next((value for key, value in TURN if key in text), 0)
    px, py = 5.0, 4.0
    camera = {"x": round(max(0, min(10, px + distance * math.sin(math.radians(turn)))), 2),
              "y": round(max(0, min(10, py + distance * math.cos(math.radians(turn)))), 2)}
    d = {"personajes": {cast["id"]: {"x": px, "y": py, "mira": "", "nombre": person["nombre"]}},
         "objetos": [], "eje": [], "planos": []}
    if cast.get("objeto") is not None and object_text:
        d["objetos"].append({"id": "objeto", "nombre": re.sub(r"^(a|an|the)\s+", "", object_text)[:60],
                             "x": 6.2, "y": 4.2})
        d["personajes"][cast["id"]]["mira"] = "objeto"
        d["eje"] = [cast["id"], "objeto"]
    d["planos"].append({"toma": 1, "tipo": shot_type(plano), "camara": camera, "apunta_a": [cast["id"]],
                        "cruza_eje": False})
    return d


def staging(d, index=0):
    """Texto de puesta de un plano para el prompt de Kontext ("" si no hay planta)."""
    if not d or not d.get("planos") or index >= len(d["planos"]):
        return ""
    labels = {key: "the person" for key in d.get("personajes", {})}
    labels.update({item["id"]: "the object" for item in d.get("objetos", [])})
    in_frame = list(d.get("personajes", {})) + [item["id"] for item in d.get("objetos", [])]
    return bloqueo_texto(d, d["planos"][index], in_frame, labels)


# --- camara 3D con inicio y fin (port de previz.py de Doble Fondo) ------------------------------------------
# la planta es la misma escala: 1 unidad = 1 metro; z = altura
FOCAL = {"PG": 24, "PC": 28, "PA": 32, "PM": 40, "PP": 60, "PPP": 85, "escorzo": 45, "contraplano": 45, "inserto": 70,
         "POV": 35}
EYE_HEIGHT = {"PG": 1.8, "PC": 1.6, "inserto": 1.1}
DEFAULT_SET = {"caja": {"ancho": 10.0, "fondo": 10.0, "alto": 3.4}, "alturas": {},
               "luces": [{"nombre": "principal", "tipo": "key", "x": 1.5, "y": 2.0, "z": 2.8, "intensidad": 1.0,
                          "color": [255, 196, 130]},
                         {"nombre": "relleno", "tipo": "fill", "x": 8.5, "y": 8.0, "z": 2.2, "intensidad": 0.35,
                          "color": [170, 185, 220]},
                         {"nombre": "contra", "tipo": "contra", "x": 5.0, "y": 0.6, "z": 3.0, "intensidad": 0.5,
                          "color": [255, 225, 190]}]}


def _target(d, shot):
    people = d.get("personajes", {})
    names = shot.get("apunta_a") or list(people)
    points = [_pos(d, name) for name in names if _pos(d, name)]
    if not points:
        return [5.0, 5.0, 1.4]
    z = 0.9 if shot.get("tipo") == "inserto" else 1.5
    return [sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points), z]


def camera(d, shot, t=0.0):
    """Camara del plano al tiempo t (0 = inicio, 1 = fin). Sin keyframes se arma desde la planta 2D: altura de ojos,
    mira al objetivo y focal segun el tipo de plano."""
    flat = shot.get("camara") or {"x": 5, "y": 9.5}
    default = {"x": float(flat["x"]), "y": float(flat["y"]), "z": EYE_HEIGHT.get(shot.get("tipo"), 1.55),
               "mira": _target(d, shot), "focal": FOCAL.get(shot.get("tipo"), 35)}
    start = {**default, **(shot.get("cam_ini") or {})}
    end = {**start, **(shot.get("cam_fin") or {})}
    if t <= 0:
        return start
    mix = lambda a, b: a + (b - a) * t  # noqa: E731
    return {"x": mix(start["x"], end["x"]), "y": mix(start["y"], end["y"]), "z": mix(start["z"], end["z"]),
            "mira": [mix(start["mira"][i], end["mira"][i]) for i in range(3)], "focal": mix(start["focal"], end["focal"])}


def people_at(d, shot, t=0.0):
    """Posicion de cada persona en el plano al tiempo t (interpola pers_ini -> pers_fin)."""
    base = {name: dict(value) for name, value in d.get("personajes", {}).items()}
    start = {**base, **{name: {**base.get(name, {}), **value} for name, value in (shot.get("pers_ini") or {}).items()}}
    end = {**start, **{name: {**start.get(name, {}), **value} for name, value in (shot.get("pers_fin") or {}).items()}}
    return {name: {"x": start[name]["x"] + (end[name]["x"] - start[name]["x"]) * t,
                   "y": start[name]["y"] + (end[name]["y"] - start[name]["y"]) * t, "mira": start[name].get("mira", "")}
            for name in start}


def movimiento(d, shot, labels=None):
    """(movimiento de camara, movimiento de personas) en ingles para el prompt de Wan, desde los keyframes."""
    labels = labels or {}
    a, b = camera(d, shot, 0.0), camera(d, shot, 1.0)
    forward = [a["mira"][0] - a["x"], a["mira"][1] - a["y"]]
    norm = math.hypot(*forward) or 1
    forward = [forward[0] / norm, forward[1] / norm]
    right = [-forward[1], forward[0]]
    move = [b["x"] - a["x"], b["y"] - a["y"], b["z"] - a["z"]]
    ahead = move[0] * forward[0] + move[1] * forward[1]
    lateral = move[0] * right[0] + move[1] * right[1]
    parts = []
    if abs(ahead) > 0.3:
        parts.append(f"slow dolly {'in' if ahead > 0 else 'out'}")
    if abs(lateral) > 0.3:
        parts.append(f"tracking shot moving {'right' if lateral > 0 else 'left'}")
    if abs(move[2]) > 0.25:
        parts.append(f"crane {'up' if move[2] > 0 else 'down'}")
    angle = lambda c: math.atan2(c["mira"][1] - c["y"], c["mira"][0] - c["x"])  # noqa: E731
    turn = (angle(b) - angle(a) + math.pi) % (2 * math.pi) - math.pi
    if abs(turn) > 0.08 and abs(lateral) <= 0.3:
        parts.append(f"camera pans {'right' if turn > 0 else 'left'}")
    tilt_a = a["mira"][2] - a["z"]
    tilt_b = b["mira"][2] - b["z"]
    if abs(tilt_b - tilt_a) > 0.4:
        parts.append(f"camera tilts {'up' if tilt_b > tilt_a else 'down'}")
    if abs(b["focal"] - a["focal"]) > 5:
        parts.append(f"slow zoom {'in' if b['focal'] > a['focal'] else 'out'}")
    camera_text = ", ".join(parts) or "static camera, locked off"
    start, end = people_at(d, shot, 0.0), people_at(d, shot, 1.0)
    actions = []
    for name in start:
        if math.hypot(end[name]["x"] - start[name]["x"], end[name]["y"] - start[name]["y"]) > 0.3:
            others = [other for other in start if other != name]
            near = min(others, key=lambda o: math.hypot(end[o]["x"] - end[name]["x"], end[o]["y"] - end[name]["y"]),
                       default=None)
            toward = near and math.hypot(end[near]["x"] - end[name]["x"], end[near]["y"] - end[name]["y"]) < \
                math.hypot(start[near]["x"] - start[name]["x"], start[near]["y"] - start[name]["y"])
            who, other = labels.get(name, name), labels.get(near, near)
            actions.append(f"{who} walks {'toward ' + other if toward else 'away from ' + other if near else 'across the room'}")
    return camera_text, "; ".join(actions)


def initial_scene(scene, data):
    """Planta inicial de una escena del guion (proyectos nuevos): las personas del elenco en fila al centro mirando
    al frente y una camara por plano, a la distancia de su tipo. Sin azar."""
    people = {}
    cast = [pid for pid in scene.get("elenco", []) if pid in data["personajes"]]
    for index, pid in enumerate(cast):
        x = 5.0 + (index - (len(cast) - 1) / 2) * 1.6
        people[pid] = {"x": round(x, 2), "y": 4.0, "mira": cast[1 - index] if len(cast) == 2 else "",
                       "nombre": data["personajes"][pid]["nombre"]}
    distance = {"PG": 5.5, "PC": 4.2, "PA": 3.4, "PM": 3.0, "PP": 1.8, "PPP": 1.2, "escorzo": 2.4, "inserto": 1.0, "POV": 2.0}
    shots = []
    for index, shot in enumerate(scene.get("planos", []), 1):
        kind = shot.get("tipo") if shot.get("tipo") in SHOT_TYPES + ("inserto", "POV") else "PM"
        shots.append({"toma": index, "id": shot.get("id"), "tipo": kind if kind in SHOT_TYPES else "PM",
                      "camara": {"x": 5.0, "y": round(min(10.0, 4.0 + distance.get(kind, 3.0)), 2)},
                      "apunta_a": cast[:1], "cruza_eje": False})
    return {"personajes": people, "objetos": [], "eje": cast[:2] if len(cast) >= 2 else [], "planos": shots,
            "set3d": json.loads(json.dumps(DEFAULT_SET))}
