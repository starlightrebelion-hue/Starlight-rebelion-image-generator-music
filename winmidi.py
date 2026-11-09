"""Puerto MIDI con SysEx sobre winmm (python-rtmidi no tiene wheel para Python 3.14)."""
import ctypes
import time
from ctypes import POINTER, byref, c_char, c_size_t, c_uint, c_ushort, c_void_p, c_wchar, sizeof

MHDR_DONE = 1
BUFFER_SIZE = 4096
BUFFER_COUNT = 8

winmm = ctypes.WinDLL("winmm")


class MidiError(RuntimeError):
    pass


class MIDIHDR(ctypes.Structure):
    _fields_ = [("lpData", c_void_p), ("dwBufferLength", c_uint), ("dwBytesRecorded", c_uint),
                ("dwUser", c_size_t), ("dwFlags", c_uint), ("lpNext", c_void_p),
                ("reserved", c_size_t), ("dwOffset", c_uint), ("dwReserved", c_size_t * 8)]


class MIDIINCAPS(ctypes.Structure):
    _fields_ = [("wMid", c_ushort), ("wPid", c_ushort), ("vDriverVersion", c_uint),
                ("szPname", c_wchar * 32), ("dwSupport", c_uint)]


class MIDIOUTCAPS(ctypes.Structure):
    _fields_ = [("wMid", c_ushort), ("wPid", c_ushort), ("vDriverVersion", c_uint),
                ("szPname", c_wchar * 32), ("wTechnology", c_ushort), ("wVoices", c_ushort),
                ("wNotes", c_ushort), ("wChannelMask", c_ushort), ("dwSupport", c_uint)]


for _name, _args in {
    "midiInGetDevCapsW": (c_size_t, POINTER(MIDIINCAPS), c_uint),
    "midiOutGetDevCapsW": (c_size_t, POINTER(MIDIOUTCAPS), c_uint),
    "midiInOpen": (POINTER(c_void_p), c_uint, c_size_t, c_size_t, c_uint),
    "midiOutOpen": (POINTER(c_void_p), c_uint, c_size_t, c_size_t, c_uint),
    "midiInPrepareHeader": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiInUnprepareHeader": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiInAddBuffer": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiOutPrepareHeader": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiOutUnprepareHeader": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiOutLongMsg": (c_void_p, POINTER(MIDIHDR), c_uint),
    "midiInStart": (c_void_p,), "midiInReset": (c_void_p,), "midiInClose": (c_void_p,),
    "midiOutClose": (c_void_p,),
}.items():
    getattr(winmm, _name).argtypes = _args


def _check(code: int, what: str) -> None:
    if code:
        raise MidiError(f"{what} fallo con codigo {code}")


def _find(count: int, get_caps, caps_type, name: str) -> int:
    for index in range(count):
        caps = caps_type()
        if get_caps(index, byref(caps), sizeof(caps)) == 0 and caps.szPname == name:
            return index
    raise MidiError(f"No existe el puerto MIDI '{name}'. Abre loopMIDI y crealo.")


class Port:
    """Entrada y salida del mismo puerto; se usa con `with`."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        in_id = _find(winmm.midiInGetNumDevs(), winmm.midiInGetDevCapsW, MIDIINCAPS, self.name)
        out_id = _find(winmm.midiOutGetNumDevs(), winmm.midiOutGetDevCapsW, MIDIOUTCAPS, self.name)
        self._in, self._out = c_void_p(), c_void_p()
        _check(winmm.midiOutOpen(byref(self._out), out_id, 0, 0, 0), "midiOutOpen")
        _check(winmm.midiInOpen(byref(self._in), in_id, 0, 0, 0), "midiInOpen")
        self._buffers = []
        for _ in range(BUFFER_COUNT):
            memory = ctypes.create_string_buffer(BUFFER_SIZE)
            header = MIDIHDR(lpData=ctypes.addressof(memory), dwBufferLength=BUFFER_SIZE)
            _check(winmm.midiInPrepareHeader(self._in, byref(header), sizeof(header)), "midiInPrepareHeader")
            _check(winmm.midiInAddBuffer(self._in, byref(header), sizeof(header)), "midiInAddBuffer")
            self._buffers.append((header, memory))
        _check(winmm.midiInStart(self._in), "midiInStart")
        return self

    def __exit__(self, *_):
        winmm.midiInReset(self._in)
        for header, _memory in self._buffers:
            winmm.midiInUnprepareHeader(self._in, byref(header), sizeof(header))
        winmm.midiInClose(self._in)
        winmm.midiOutClose(self._out)

    def send(self, data: bytes) -> None:
        memory = ctypes.create_string_buffer(data, len(data))
        header = MIDIHDR(lpData=ctypes.addressof(memory), dwBufferLength=len(data))
        _check(winmm.midiOutPrepareHeader(self._out, byref(header), sizeof(header)), "midiOutPrepareHeader")
        _check(winmm.midiOutLongMsg(self._out, byref(header), sizeof(header)), "midiOutLongMsg")
        while not header.dwFlags & MHDR_DONE:
            time.sleep(0.001)
        winmm.midiOutUnprepareHeader(self._out, byref(header), sizeof(header))

    def receive(self):
        """Devuelve los SysEx que hayan llegado, sin bloquear."""
        messages = []
        for header, memory in self._buffers:
            if header.dwFlags & MHDR_DONE:
                messages.append(bytes((c_char * header.dwBytesRecorded).from_buffer(memory)))
                header.dwFlags &= ~MHDR_DONE
                header.dwBytesRecorded = 0
                _check(winmm.midiInAddBuffer(self._in, byref(header), sizeof(header)), "midiInAddBuffer")
        return messages
