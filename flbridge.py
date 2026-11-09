"""Cliente del tunel a FL Studio, temas visuales y presets de proyecto."""
import json
import msvcrt
import random
import subprocess
import tempfile
import time
import winreg
from contextlib import contextmanager
from pathlib import Path

from winmidi import MidiError, Port

ROOT = Path(__file__).resolve().parent
RENDER_SETTLE = 4  # segundos sin cambios en el archivo para dar el render por terminado
PRESETS_DIR = ROOT / "presets"
LOCK_FILE = Path(tempfile.gettempdir()) / "flbridge.lock"
PORT_NAME = "loopMIDI Port"
HEADER = bytes((0xF0, 0x7D, 0x46, 0x4C))
REQUEST, REPLY = 1, 2
CHUNK = 200  # bytes de datos por mensaje; debe coincidir con device_FLBridge.py
THEME_KEY = r"Software\Image-Line\FL Studio 21\General\Theme"
CURRENT_THEME = "__current.flstheme"


class FLError(RuntimeError):
    pass


def _shared_path(value: str) -> Path:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Image-Line\Shared\Paths") as key:
        return Path(winreg.QueryValueEx(key, value)[0])


def settings_dir() -> Path:
    return _shared_path("Shared data") / "FL Studio" / "Settings"


# ---------------------------------------------------------------- tunel

def _encode(arg) -> str:
    if isinstance(arg, bool):
        return "b:" + ("1" if arg else "0")
    if isinstance(arg, int):
        return f"i:{arg}"
    if isinstance(arg, float):
        return f"f:{arg!r}"
    text = str(arg).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    return "s:" + text


@contextmanager
def _lock():
    """La CLI y el servidor MCP se turnan: una peticion a la vez."""
    with open(LOCK_FILE, "a+b") as handle:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # reintenta ~10 s
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _frames(message_id: int, data: bytes) -> list:
    total = -(-len(data) // CHUNK)
    if total > 127:
        raise FLError("Peticion demasiado grande: divide los comandos.")
    frames = []
    for index in range(total):
        body = bytearray()
        for byte in data[index * CHUNK:(index + 1) * CHUNK]:
            body += bytes((byte >> 4, byte & 15))
        frames.append(HEADER + bytes((REQUEST, message_id, index, total)) + body + b"\xf7")
    return frames


def _exchange(data: bytes, timeout: float) -> bytes:
    message_id = random.randrange(128)
    received = bytearray()
    deadline = time.time() + timeout
    with _lock(), Port(PORT_NAME) as port:
        for frame in _frames(message_id, data):
            port.send(frame)
        while time.time() < deadline:
            for message in port.receive():
                if message[:6] != HEADER + bytes((REPLY, message_id)):
                    continue  # eco de la peticion u otro trafico del puerto
                index, total, body = message[6], message[7], message[8:-1]
                received += bytes((body[i] << 4) | body[i + 1] for i in range(0, len(body), 2))
                if index == total - 1:
                    return bytes(received)
            time.sleep(0.002)
    raise FLError(
        f"FL Studio no respondio en {timeout:g} s. Comprueba que FL este abierto y que "
        f"'{PORT_NAME}' este asignado a FLBridge como entrada y salida en el puerto 200.")


def batch(calls, timeout: float = 5.0) -> list:
    """Ejecuta [(modulo, funcion, *args), ...] en orden.

    Devuelve un resultado {"ok", "value"|"error"} por comando; FL se detiene en
    el primer error, asi que la lista puede ser mas corta que `calls`.
    """
    results = []
    for group in _groups(calls):
        try:
            reply = _exchange("\n".join(group).encode("utf-8"), timeout)
        except MidiError as error:
            raise FLError(str(error)) from error
        results += json.loads(reply)["results"]
        if not results[-1]["ok"]:
            break
    return results


def _groups(calls) -> list:
    """Agrupa comandos en pedidos de un mensaje: muchos SysEx seguidos cuelgan FL."""
    groups, size = [[]], 0
    for item in calls:
        line = "\t".join([item[0], item[1], *map(_encode, item[2:])])
        length = len(line.encode("utf-8")) + 1
        if groups[-1] and size + length > CHUNK:
            groups.append([])
            size = 0
        groups[-1].append(line)
        size += length
    return groups


def call(module: str, function: str, *args, timeout: float = 5.0):
    result = batch([(module, function, *args)], timeout)[0]
    if not result["ok"]:
        raise FLError(result["error"])
    return result["value"]


def status() -> dict:
    keys = ("version", "tempo", "playing", "channels", "mixer_tracks", "pattern")
    results = batch([
        ("general", "getVersion"), ("mixer", "getCurrentTempo"), ("transport", "isPlaying"),
        ("channels", "channelCount"), ("mixer", "trackCount"), ("patterns", "patternNumber"),
    ])
    state = {k: r.get("value", r.get("error")) for k, r in zip(keys, results)}
    if isinstance(state["tempo"], int):
        state["tempo"] /= 1000  # FL devuelve BPM x 1000
    return state


# ---------------------------------------------------------------- exportar

def render(project, fmt: str = "wav", timeout: float = 600.0) -> Path:
    """Renderiza un .flp guardado; el audio queda junto al proyecto.

    Abre una instancia de FL que se cierra sola, por eso FL debe estar cerrado.
    """
    project = Path(project).resolve()
    if not project.is_file():
        raise FLError(f"No existe el proyecto: {project}")
    if fmt not in ("wav", "mp3"):
        raise FLError(f"Formato no soportado: {fmt}. Usa wav o mp3.")
    if fl_running():
        raise FLError("Cierra FL Studio primero: el render abre su propia instancia.")
    target = project.with_suffix("." + fmt)
    started = time.time()
    process = subprocess.Popen([str(_shared_path("FL Studio")), "/R", f"/E{fmt}", str(project)])
    size, still = -1, 0
    while process.poll() is None:
        if time.time() - started > timeout:
            process.kill()
            raise FLError(f"El render no termino en {timeout:g} s.")
        time.sleep(1)
        current = target.stat().st_size if target.is_file() else -1
        still = still + 1 if current == size and render_finished(target, started - 2) else 0
        size = current
        if still >= RENDER_SETTLE:
            # Con plugins VST, FL no se cierra: pregunta si guarda. El proyecto ya estaba guardado.
            process.kill()
            process.wait()
            return target
    if process.returncode:
        raise FLError(f"FL termino con codigo {process.returncode}.")
    if not target.is_file() or target.stat().st_mtime < started - 2:
        raise FLError(f"FL termino pero no genero {target.name}.")
    return target


def render_finished(target: Path, since: float) -> bool:
    """Un archivo escrito desde `since` esta completo si su cabecera WAV declara su tamano real."""
    if not target.is_file() or target.stat().st_size == 0 or target.stat().st_mtime < since:
        return False
    if target.suffix != ".wav":
        return True
    with open(target, "rb") as file:
        head = file.read(8)
    return head[:4] == b"RIFF" and int.from_bytes(head[4:8], "little") + 8 == target.stat().st_size


# ---------------------------------------------------------------- presets de proyecto

def list_presets() -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")).get("description", "")
            for p in sorted(PRESETS_DIR.glob("*.json"))}


def run_preset(name: str) -> int:
    path = PRESETS_DIR / f"{name}.json"
    if not path.is_file():
        raise FLError(f"Preset desconocido: {name}. Disponibles: {', '.join(list_presets())}")
    commands = json.loads(path.read_text(encoding="utf-8"))["commands"]
    results = batch(commands, timeout=10.0)
    if results and not results[-1]["ok"]:
        failed = commands[len(results) - 1]
        raise FLError(f"Preset detenido en el comando {len(results)} {failed}: {results[-1]['error']}")
    return len(results)


# ---------------------------------------------------------------- temas visuales

def themes_dir() -> Path:
    return settings_dir() / "Themes"


def _theme_files() -> dict:
    stock = _shared_path("FL Studio").parent / "Artwork" / "Themes"
    files = {p.stem: p for p in stock.rglob("*.flstheme")}
    files.update({p.stem: p for p in themes_dir().glob("*.flstheme") if p.name != CURRENT_THEME})
    return files


def list_themes() -> list:
    return sorted(_theme_files())


def _theme_path(name: str) -> Path:
    files = _theme_files()
    if name not in files:
        raise FLError(f"Tema desconocido: {name}. Disponibles: {', '.join(sorted(files))}")
    return files[name]


def _color(value):
    """'#RRGGBB' -> entero ARGB con signo, como lo guarda .flstheme."""
    if isinstance(value, str) and value.startswith("#"):
        return (0xFF000000 | int(value[1:], 16)) - (1 << 32)
    return value


def create_theme(name: str, base: str = "Dark", **values) -> Path:
    """Crea un tema de usuario a partir de `base`. Los colores aceptan '#RRGGBB'."""
    lines = _theme_path(base).read_text(encoding="utf-8-sig").splitlines()
    theme = dict(line.split("=", 1) for line in lines if "=" in line)
    theme.update({key: str(_color(value)) for key, value in values.items()})
    target = themes_dir() / f"{name}.flstheme"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "\r\n".join(f"{key}={value}" for key, value in theme.items()) + "\r\n"
    target.write_bytes(body.encode("utf-8-sig"))
    return target


def fl_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FL64.exe", "/NH"],
                         capture_output=True, text=True).stdout
    return "FL64.exe" in out


def _set_active_theme(filename: str) -> None:
    if fl_running():
        raise FLError("Cierra FL Studio primero: solo lee el tema al arrancar.")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ThemeFilename", 0, winreg.REG_SZ, filename)


def apply_theme(name: str) -> Path:
    """Deja el tema activo para el proximo arranque de FL.

    FL ignora rutas en ThemeFilename: arranca desde Themes/__current.flstheme.
    """
    source = _theme_path(name)
    _set_active_theme(CURRENT_THEME)
    target = themes_dir() / CURRENT_THEME
    target.write_bytes(source.read_bytes())
    return target


def reset_theme() -> None:
    """Vuelve al tema por defecto de FL."""
    _set_active_theme("")
    (themes_dir() / CURRENT_THEME).unlink(missing_ok=True)
