"""Lee y crea presets de Arturia Pigments sin abrir el programa.

Los presets son archivos de texto de Boost serialization: una cabecera (nombre, banco, autor,
etiquetas) y unos 1200 parametros `largo nombre valor`, casi todos normalizados de 0 a 1.
Un preset nuevo se hace copiando uno de fabrica y cambiando valores: el resto del archivo
(tablas de onda, muestras, ruteos binarios) queda byte por byte igual.
"""
import re
from functools import cache
from pathlib import Path
from typing import NamedTuple

FACTORY = Path(r"C:\ProgramData\Arturia\Presets\Pigments")
NAMES = Path(r"C:\ProgramData\Arturia\Pigments\resources\Reference_ParamNames.xml")
DEFINITION = NAMES.with_name("Pigments.xml")
OUTPUT = Path(__file__).resolve().parent / "presets" / "pigments"
HEADER = re.compile(rb"^22 serialization::archive \d+ \d+ \d+ \d+ \d+ ")
SECTION = re.compile(rb" \d{3,5} 0 0 0 \d")    # cantidad de parametros, justo antes del primero
LENGTH = re.compile(rb"(?<= )(\d{1,3}) ")
NAME = re.compile(rb"[A-Za-z_][A-Za-z0-9_ ]*")
VALUE = re.compile(rb" (-?[0-9][0-9.eE+-]*)(?= \d|\n|$)")  # despues viene el largo del proximo nombre
NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")
# lo que importa para entender un sonido de un vistazo
SUMMARY = ("Engine1_ModuleType", "Engine2_ModuleType", "Env1_Attack", "Env1_Decay", "Env1_Sustain", "Env1_Release",
           "Filter1_ModuleType", "Filter1_Cutoff", "Filter1_Resonance", "Filter2_ModuleType", "Filter2_Cutoff",
           "Filter2_Resonance", "Filter_Routing", *(f"FX{n}_ModuleType" for n in range(1, 10)), "FX_Routing",
           "Glide", "Macro1", "Macro2", "Macro3", "Macro4", "MasterVolume")
# parametros que guardan un indice, no un valor de 0 a 1: prefijo de sus listas en Pigments.xml
CHOICES = {"Engine": "EngType", "Filter": "FilterTypesV", "FX": "FXListV"}


class Preset(NamedTuple):
    path: Path
    name: str
    bank: str
    author: str
    kind: str
    tags: tuple
    version: tuple


def _version(text):
    return tuple(int(part) for part in text.split("."))


def _string(data, position):
    """Lee `largo texto` desde `position`. Devuelve (texto, siguiente posicion)."""
    space = data.index(b" ", position)
    size = int(data[position:space])
    start = space + 1
    return data[start:start + size].decode("utf-8", "replace"), start + size + 1


def header(path):
    data = Path(path).read_bytes()[:4000]
    match = HEADER.match(data)
    if not match:
        raise ValueError(f"No es un preset de Pigments: {path}")
    name, position = _string(data, match.end())
    bank, position = _string(data, position)
    position = data.index(b" ", position) + 1  # numero de version de la clase
    author, position = _string(data, position)
    text = data.decode("latin1")
    kind = re.search(r" 4 Type (\d+) ", text)
    kind = text[kind.end():kind.end() + int(kind.group(1))] if kind else ""
    tags = re.search(r" (\d+) (Characteristics,)", text)
    tags = text[tags.start(2):tags.start(2) + int(tags.group(1))] if tags else ""
    words = tuple(sorted({word for group in tags.split(";") if "," in group
                          for word in group.split(",", 1)[1].split("|") if word}))
    version = re.search(r" \d+ (\d+\.\d+\.\d+)\.\d+ ", text)
    return Preset(Path(path), name, bank, author, kind, words, _version(version.group(1)) if version else (0, 0, 0))


@cache
def library():
    """Todos los presets de fabrica y los creados aca."""
    folders = [FACTORY / "Factory", OUTPUT]
    presets = []
    for folder in folders:
        for path in sorted(folder.rglob("*")) if folder.exists() else ():
            if path.is_file() and path.suffix == "":
                try:
                    presets.append(header(path))
                except ValueError:
                    continue
    return tuple(presets)


def find(text="", kind="", tag="", limit=40):
    """Busca por nombre, tipo (Pad, Bass, Lead...) y etiqueta (Ambient, Evolving...)."""
    text, kind, tag = text.lower(), kind.lower(), tag.lower()
    found = [preset for preset in library()
             if text in preset.name.lower() and kind in preset.kind.lower()
             and (not tag or any(tag in word.lower() for word in preset.tags))]
    return found[:limit]


def locate(name):
    exact = [preset for preset in library() if preset.name.lower() == name.lower()]
    if not exact:
        raise ValueError(f"No hay un preset llamado {name!r}. Usa find() para buscarlo.")
    return exact[0]


def _fields(data):
    """(nombre, inicio y fin del valor) de cada parametro numerico.

    Empieza despues de la cabecera, en `N 0 0 0` (N = cantidad de parametros). Los nombres pueden
    tener espacios, asi que se leen por su largo y no con una expresion.
    """
    section = SECTION.search(data)
    position = section.end() - 1 if section else len(data)
    for match in LENGTH.finditer(data, position):
        size, start = int(match.group(1)), match.end()
        name = data[start:start + size]
        value = VALUE.match(data, start + size)
        if NAME.fullmatch(name) and value:
            yield name.decode(), value.start(1), value.end(1)


def parameters(path):
    """{nombre: valor} de todos los parametros numericos."""
    data = Path(path).read_bytes()
    return {name: float(data[start:end]) for name, start, end in _fields(data)}


@cache
def display_names():
    """El XML de Arturia no es valido en todas sus lineas: se lee con una expresion."""
    text = NAMES.read_text(encoding="utf-8", errors="replace")
    return dict(re.findall(r'<param name="([^"]+)" display_name="([^"]*)"', text))


@cache
def choices():
    """Nombres de motores, filtros y efectos por indice.

    Pigments suma opciones en cada version: algunas listas repiten las anteriores y otras solo agregan.
    """
    text = DEFINITION.read_text(encoding="utf-8", errors="replace")
    bodies = {name: re.findall(r'<item text="([^"]*)"', body) for name, body in
              re.findall(r'<item_list name="([^"]+)"[^/>]*>(.*?)</item_list>', text, re.S)}
    versions = dict(re.findall(r'<item_list name="([^"]+)" version="([\d.]+)"\s*/>', text))
    result = {}
    for kind, prefix in CHOICES.items():
        names, steps = [], []
        for name in sorted((name for name in versions if name.startswith(prefix)), key=lambda n: _version(versions[n])):
            items = bodies.get(name, [])
            if not items or (names and len(items) < len(names) and items[0] == names[0]):
                continue
            if names and items[0] == names[0]:
                names = list(items)
            else:
                names = names + [item for item in items if item not in names]
            steps.append((_version(versions[name]), names))
        result[kind] = steps
    return result


def options(kind, version=(99,)):
    """Las opciones de motor, filtro o efecto que tenia Pigments en esa version."""
    steps = [names for since, names in choices()[kind] if since <= tuple(version)]
    return steps[-1] if steps else []


def readable(key, value, version=(99,)):
    """El valor tal cual, salvo los tipos de motor, filtro y efecto, que se traducen a su nombre.

    Pigments los guarda como indice / (opciones - 1), con las opciones de la version del preset.
    """
    kind = re.match(r"(Engine|Filter|FX)\d_ModuleType$", key)
    if kind:
        names = options(kind.group(1), version)
        index = round(value * (len(names) - 1)) if len(names) > 1 else 0
        if names and abs(index - value * (len(names) - 1)) < .01:
            return names[index]
    return value


def choice_value(kind, name, version=(99,)):
    """Valor a escribir para elegir un motor, filtro o efecto por nombre."""
    names = options(kind, version)
    if name not in names:
        raise ValueError(f"{name!r} no existe en la version {'.'.join(map(str, version))} de este preset. "
                         f"Opciones: {names}. Usa una base mas nueva para tener las demas.")
    return names.index(name) / (len(names) - 1)


def describe(name, contains=""):
    """Los parametros principales de un preset, o los que contengan `contains`, con su nombre legible."""
    preset = locate(name)
    values = parameters(preset.path)
    names = display_names()
    keys = [key for key in values if contains.lower() in key.lower()] if contains else \
        [key for key in SUMMARY if key in values]
    return {"preset": preset._asdict() | {"path": str(preset.path)},
            "parametros": {key: {"valor": readable(key, values[key], preset.version), "nombre": names.get(key, "")} for key in keys}}


def _rename(data, old, new):
    old_field = f"{len(old.encode())} {old} ".encode()
    new_field = f"{len(new.encode())} {new} ".encode()
    start = HEADER.match(data).end()
    if data[start:start + len(old_field)] != old_field:
        raise ValueError("No encuentro el nombre en la cabecera")
    return data[:start] + new_field + data[start + len(old_field):]


def derive(base, name, changes, folder=OUTPUT):
    """Copia un preset, le cambia el nombre y los valores de `changes` {parametro: valor}. Devuelve la ruta."""
    if not re.fullmatch(r"[\w .\-()]{1,60}", name):
        raise ValueError("Nombre con caracteres no validos para un archivo")
    preset = locate(base)
    data = _rename(preset.path.read_bytes(), preset.name, name)
    known = parameters(preset.path)
    missing = set(changes) - set(known)
    if missing:
        raise ValueError(f"Parametros que este preset no tiene: {sorted(missing)}")

    edits = [(start, end, f"{float(changes[name]):.8g}".encode()) for name, start, end in _fields(data)
             if name in changes]
    for start, end, value in reversed(edits):
        data = data[:start] + value + data[end:]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(data)
    library.cache_clear()
    return target
