"""Edita archivos .flp: lo que la API de scripting de FL no permite (clips y efectos).

Solo probado con proyectos guardados por FL Studio 21.1. FL debe estar cerrado.
"""
import hashlib
import json
import struct
from compression import zstd
from pathlib import Path

import cbor2

CLIPS, PLUGIN_NAME, PLUGIN_WRAPPER, PLUGIN_STATE = 233, 201, 212, 213
INSERT_START, SLOT = 236, 98
MIXER_PARAMS, ROUTES = 225, 235
ROUTE_LEVEL_FIRST = 64  # id del parametro de envio hacia la pista 0
WRAPPER_FIRST_RECORD = struct.pack("<IQ", 0x32, 16)
WRAPPER_PLUGIN_STATE, VST3_COMPONENT, VST3_CONTROLLER = 0x35, 3, 2
PATTERN_NEW, PATTERN_NOTES = 65, 224
CHANNEL_NEW, CHANNEL_TYPE, CHANNEL_INSERT, CHANNELS_END = 64, 21, 22, 99
PLUGIN_TITLE, PLUGIN_COLOR, SAMPLE_PATH, SAMPLER_FLAG = 203, 128, 196, 41
PATTERN_BASE = 20480
TRACK_MAX = 499  # FL guarda la pista invertida
BAR = 384  # ticks por compas a 96 PPQ


def read(path):
    """Devuelve (cabecera, [(id, bytes), ...])."""
    data = Path(path).read_bytes()
    header_size = struct.unpack("<I", data[4:8])[0]
    start = 8 + header_size
    if data[:4] != b"FLhd" or data[start:start + 4] != b"FLdt":
        raise ValueError(f"No es un .flp: {path}")
    pos, end = start + 8, start + 8 + struct.unpack("<I", data[start + 4:start + 8])[0]
    events = []
    while pos < end:
        event = data[pos]
        pos += 1
        if event < 192:
            size = 1 if event < 64 else 2 if event < 128 else 4
        else:
            size = shift = 0
            while True:
                byte = data[pos]
                pos += 1
                size |= (byte & 127) << shift
                shift += 7
                if byte < 128:
                    break
        events.append((event, data[pos:pos + size]))
        pos += size
    return data[:start], events


def write(path, header, events):
    body = bytearray()
    for event, value in events:
        body.append(event)
        if event >= 192:
            size = len(value)
            while True:
                byte = size & 127
                size >>= 7
                body.append(byte | (128 if size else 0))
                if not size:
                    break
        body += value
    Path(path).write_bytes(header + b"FLdt" + struct.pack("<I", len(body)) + body)


def _clip(position, pattern, track, bars, counter):
    length = bars * BAR
    return (struct.pack("<IHHIHH", position, PATTERN_BASE, PATTERN_BASE + pattern, length,
                        TRACK_MAX - track, 0)
            + bytes.fromhex("7800400040648080")
            + struct.pack("<II", 0, length)
            + struct.pack("<I", counter) + bytes(16) + struct.pack("<f", 1.0) + bytes(4))


def arrange(events, sections, clip_bars=1):
    """Reemplaza la playlist. `sections`: [(patron, pista, compases), ...] en orden.

    Pone un clip cada `clip_bars` compases, que debe ser lo que dura el patron.
    """
    clips, bar = [], 0
    for pattern, track, bars in sections:
        for _ in range(bars // clip_bars):
            clips.append((bar, pattern, track, clip_bars))
            bar += clip_bars
    place(events, clips)
    return bar


def place(events, clips):
    """Reemplaza la playlist. `clips`: [(compas, patron, pista, compases), ...]."""
    data = [_clip(bar * BAR, pattern, track, bars, number)
            for number, (bar, pattern, track, bars) in enumerate(sorted(clips), 1)]
    index = next(n for n, (event, _) in enumerate(events) if event == CLIPS)
    events[index] = (CLIPS, b"".join(data))


def note(position, channel, length, key, velocity=100):
    """Una nota de 24 bytes. Velocidad 0-127; key 60 es el Do central."""
    return (struct.pack("<IHHIHH", position, 0x4000, channel, length, key, 0)
            + bytes((0x78, 0, 0x40, 0, 0x40, velocity, 0x80, 0x80)))


def set_patterns(events, patterns):
    """Reemplaza las notas. `patterns`: {numero: [(posicion, nota_en_bytes), ...]}."""
    first = next(n for n, (event, _) in enumerate(events) if event == PATTERN_NEW)
    end = first
    while events[end][0] in (PATTERN_NEW, PATTERN_NOTES):
        end += 1
    block = []
    for number, notes in sorted(patterns.items()):
        block.append((PATTERN_NEW, struct.pack("<H", number)))
        block.append((PATTERN_NOTES, b"".join(data for _, data in sorted(notes, key=lambda n: n[0]))))
    events[first:end] = block


def _channel_starts(events):
    return [n for n, (event, _) in enumerate(events) if event == CHANNEL_NEW]


def _channel_end(events, start):
    end = start + 1
    while events[end][0] not in (CHANNEL_NEW, PATTERN_NEW, CHANNELS_END):
        end += 1
    return end


def _text(value):
    return (value + "\0").encode("utf-16-le")


def set_sample(events, channel, path):
    """Cambia la muestra de un canal Sampler."""
    start = _channel_starts(events)[channel]
    for n in range(start, _channel_end(events, start)):
        if events[n][0] == SAMPLE_PATH:
            events[n] = (SAMPLE_PATH, _text(path))
            return
    raise ValueError(f"El canal {channel} no tiene muestra")


def add_channel(events, header, name, insert, preset=None, sample=None):
    """Agrega un canal usando el canal 1 como molde. Devuelve (cabecera, indice).

    `preset`: .fst de un generador. `sample`: ruta para un canal Sampler.
    """
    starts = _channel_starts(events)
    index = len(starts)
    replaced = {CHANNEL_NEW: struct.pack("<H", index), PLUGIN_TITLE: _text(name),
                CHANNEL_INSERT: bytes((insert,))}
    if sample:
        replaced[SAMPLE_PATH] = _text(sample)
    block = [(event, replaced.get(event, value))
             for event, value in events[starts[1]:_channel_end(events, starts[1])]]
    if preset:
        values = dict(read(preset)[1])
        replaced = {CHANNEL_TYPE: b"\x02", PLUGIN_NAME: values[PLUGIN_NAME],
                    PLUGIN_WRAPPER: values[PLUGIN_WRAPPER]}
        generator = []
        for event, value in block:
            if event not in (SAMPLE_PATH, SAMPLER_FLAG):
                generator.append((event, replaced.get(event, value)))
            if event == PLUGIN_COLOR:
                generator.append((PLUGIN_STATE, values[PLUGIN_STATE]))
        block = generator
    target = next(n for n in range(starts[-1], len(events)) if events[n][0] == CHANNELS_END)
    events[target:target] = block
    return header[:10] + struct.pack("<H", index + 1) + header[12:], index


def plugin_block(events, name):
    """Extrae los eventos de un efecto del mixer por su nombre interno."""
    first_insert = next(n for n, (event, _) in enumerate(events) if event == INSERT_START)
    for n in range(first_insert, len(events)):
        event, value = events[n]
        if event == PLUGIN_NAME and value.decode("utf-16-le").rstrip("\0") == name:
            end = next(m for m in range(n, len(events)) if events[m][0] == SLOT)
            return events[n:end]
    raise ValueError(f"Efecto no encontrado: {name}")


def effect_block(preset):
    """Extrae un efecto de un preset .fst, listo para `add_effect`."""
    block = [(event, value) for event, value in read(preset)[1]
             if event in (PLUGIN_NAME, PLUGIN_WRAPPER, 155, PLUGIN_COLOR, SAMPLER_FLAG, PLUGIN_STATE)]
    name = dict(block)[PLUGIN_NAME]
    if bytes(1) not in name[:-1]:  # los presets viejos guardan el nombre en ASCII
        name = _text(name.rstrip(bytes(1)).decode("ascii"))
    return [(event, name if event == PLUGIN_NAME else value) for event, value in block]


def _records(data):
    """Lee los registros del wrapper de VST: id u32, largo u64, valor."""
    records, pos = [], 0
    while pos < len(data):
        record, size = struct.unpack("<IQ", data[pos:pos + 12])
        records.append((record, data[pos + 12:pos + 12 + size]))
        pos += 12 + size
    return records


def _pack_records(records):
    return b"".join(struct.pack("<IQ", record, len(value)) + value for record, value in records)


def fxp_chunk(path):
    """Devuelve el patch guardado en un .fxp."""
    data = Path(path).read_bytes()
    if data[:4] != b"CcnK" or data[8:12] != b"FPCh":
        raise ValueError(f"No es un patch .fxp: {path}")
    size = struct.unpack(">I", data[56:60])[0]
    return data[60:60 + size]


def set_vst3_chunk(state, chunk):
    """Reemplaza el patch dentro del estado que FL guarda para un VST3."""
    start = state.index(WRAPPER_FIRST_RECORD)
    records = _records(state[start:])
    for n, (record, value) in enumerate(records):
        if record == WRAPPER_PLUGIN_STATE:
            inner = 16 + struct.unpack("<Q", value[8:16])[0]
            parts = [(part, struct.pack("<I", len(chunk)) + chunk if part == VST3_COMPONENT else data)
                     for part, data in _records(value[inner:])]
            records[n] = (record, value[:inner] + _pack_records(parts))
            return state[:start] + _pack_records(records)
    raise ValueError("El estado no trae datos del plugin: guardalo antes desde FL")


def _xfer_split(data):
    """Separa un bloque XferJson en (cabecera JSON, datos comprimidos)."""
    size = struct.unpack("<Q", data[9:17])[0]
    return json.loads(data[17:17 + size]), data[17 + size:]


def _xfer_join(header, body):
    """El hash es el MD5 de los datos, sin sus primeros 8 bytes."""
    header = {**header, "hash": hashlib.md5(body[8:]).hexdigest()}
    text = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return data_prefix(len(text)) + text + body


def data_prefix(size):
    return b"XferJson" + bytes(1) + struct.pack("<Q", size)


SERUM_INTERFACE_KEYS = {"ClipPlayer", "Filter", "GranularOsc", "MultiSampleOsc", "Osc", "SerumGUI", "SpectralOsc",
                        "WTOsc", "arpBankDisplayName", "clipBankDisplayName", "fileType", "presetAuthor",
                        "presetDescription", "presetName"}


def _serum_plain(value):
    """En el preset `plainParams` puede valer "default"; en el estado es un mapa vacio."""
    if isinstance(value, dict):
        return {key: {} if key == "plainParams" and item == "default" else _serum_plain(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_serum_plain(item) for item in value]
    return value


def serum_processor(body):
    """Convierte los datos de un preset a los del procesador de Serum 2."""
    data = cbor2.loads(zstd.decompress(body[8:]))
    data = {key: item for key, item in _serum_plain(data).items() if key not in SERUM_INTERFACE_KEYS}
    raw = cbor2.dumps({"component": "processor", **data})
    return struct.pack("<II", len(raw), 2) + zstd.compress(raw)


def set_serum_preset(state, preset):
    """Carga un .SerumPreset en el estado que FL guarda para Serum 2."""
    info, body = _xfer_split(Path(preset).read_bytes())
    body = serum_processor(body)
    start = state.index(WRAPPER_FIRST_RECORD)
    records = _records(state[start:])
    for n, (record, value) in enumerate(records):
        if record == WRAPPER_PLUGIN_STATE:
            inner = 16 + struct.unpack("<Q", value[8:16])[0]
            parts = []
            for part, data in _records(value[inner:]):
                if part == VST3_COMPONENT:
                    data = _xfer_join({**_xfer_split(data)[0], "version": info["version"],
                                       "productVersion": info["productVersion"]}, body)
                elif part == VST3_CONTROLLER:
                    header, controller = _xfer_split(data)
                    data = _xfer_join({**header, "presetName": info["presetName"]}, controller)
                parts.append((part, data))
            records[n] = (record, value[:inner] + _pack_records(parts))
            return state[:start] + _pack_records(records)
    raise ValueError("El estado no trae datos del plugin: guardalo antes desde FL")


def set_pigments_preset(state, preset):
    """Carga un preset de Pigments en el estado que FL guarda para su VST3.

    Pigments guarda ahi el mismo texto que sus archivos de preset, en el componente y en el
    controlador. El canal tiene que haberse guardado antes con Pigments desde FL.
    """
    text = Path(preset).read_bytes()
    if not text.startswith(b"22 serialization::archive"):
        raise ValueError(f"No es un preset de Pigments: {preset}")
    start = state.index(WRAPPER_FIRST_RECORD)
    records = _records(state[start:])
    for n, (record, value) in enumerate(records):
        if record == WRAPPER_PLUGIN_STATE:
            inner = 16 + struct.unpack("<Q", value[8:16])[0]
            parts = _records(value[inner:])
            if not any(data.startswith(b"22 serialization::archive") for part, data in parts):
                raise ValueError("El estado no es de Pigments")
            parts = [(part, text if part in (VST3_COMPONENT, VST3_CONTROLLER) else data) for part, data in parts]
            records[n] = (record, value[:inner] + _pack_records(parts))
            return state[:start] + _pack_records(records)
    raise ValueError("El estado no trae datos del plugin: guardalo antes desde FL")


def set_routes(events, insert, levels):
    """Reemplaza las salidas de una pista. `levels`: {pista destino: nivel 0-1}.

    Un nivel 0 deja la ruta sin audio: sirve para alimentar un sidechain.
    """
    starts = [n for n, (event, _) in enumerate(events) if event == INSERT_START]
    end = starts[insert + 1] if insert + 1 < len(starts) else len(events)
    target = next(n for n in range(starts[insert], end) if events[n][0] == ROUTES)
    events[target] = (ROUTES, bytes(int(n in levels) for n in range(len(events[target][1]))))
    index = next(n for n, (event, _) in enumerate(events) if event == MIXER_PARAMS)
    records = b"".join(struct.pack("<IBBHi", 0, ROUTE_LEVEL_FIRST + dest, 31, 0x2000 | insert << 6,
                                   round(level * 12800))
                       for dest, level in sorted(levels.items()))
    events[index] = (MIXER_PARAMS, events[index][1] + records)


def add_effect(events, insert, slot, block):
    """Inserta un efecto en la pista `insert` del mixer (0 = master)."""
    starts = [n for n, (event, _) in enumerate(events) if event == INSERT_START]
    end = starts[insert + 1] if insert + 1 < len(starts) else len(events)
    target = next(n for n in range(starts[insert], end)
                  if events[n][0] == SLOT and struct.unpack("<H", events[n][1])[0] == slot)
    if events[target - 1][0] == PLUGIN_STATE:
        raise ValueError(f"El slot {slot} de la pista {insert} ya esta ocupado")
    block = [(event, struct.pack("<II", insert, slot) + value[8:] if event == PLUGIN_WRAPPER else value)
             for event, value in block]
    events[target:target] = block
