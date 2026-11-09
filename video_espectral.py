"""Motor de video espectral: una imagen de ComfyUI + feedback estilo MilkDrop + procedurales de Cosmos.

    video_espectral.bat "tema.mp3" [--semilla 7] [--paleta Plasma] [--idea "texto"]
    video_espectral.bat "tema.mp3" --desde 60 --segundos 15     prueba corta
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

import moderngl
import numpy as np

import espectro
import fondo_comfy
import seo_youtube as seo
import visual_estilo as style

ROOT = Path(__file__).resolve().parent
SHADERS = ROOT / "shaders"
OUTPUT = ROOT / "Video Espectral"
RINGS = 6
STARS = 5000
SCENE_BLEND = 3.0   # segundos de fundido entre escenas
FADE = 1.5          # entrada y salida a negro
RING_LIFE = 2.2     # segundos que tarda un anillo en cruzar la pantalla
GLOW_SIZE = 4       # el resplandor se calcula a 1/4 de resolucion
WALL_LEVEL = .2     # brillo medio maximo de la imagen
KEY_AREA = (.08, .5)  # parte de la imagen que deben ocupar las pantallas para usarlas de croma
DARK_SKY = .09      # por debajo de esto el cielo admite el planeta procedural


class Scene(NamedTuple):
    start: int      # cuadro
    warp: style.Warp
    shape: int


def plan_scenes(analysis, direction):
    """Una escena por seccion del tema: la imagen no cambia, cambian la deformacion y la forma del espectro."""
    scenes = []
    for number, start in enumerate((0, *analysis.cuts)):
        scenes.append(Scene(start, style.WARPS[direction.warps[number % len(direction.warps)]],
                            style.SHAPES.index(direction.shapes[number % len(direction.shapes)])))
    return scenes


def scene_state(scenes, frame, fps):
    """Escena saliente, entrante y cuanto va del fundido."""
    index = max(number for number, scene in enumerate(scenes) if scene.start <= frame)
    blend = SCENE_BLEND * fps
    amount = min(1.0, (frame - scenes[index].start) / blend) if index else 1.0
    amount = amount * amount * (3 - 2 * amount)
    return scenes[max(0, index - 1)], scenes[index], amount


def active_rings(analysis, frame):
    """Cada golpe fuerte da nacimiento a un anillo con la nota y el volumen de ese instante, como en Cosmos."""
    life = int(RING_LIFE * analysis.fps)
    recent = analysis.beats[(analysis.beats <= frame) & (analysis.beats > frame - life)]
    rings = np.zeros((RINGS, 4), dtype=np.float32)
    for slot, birth in enumerate(recent[-RINGS:]):
        age = (frame - birth) / life
        rings[slot] = (.05 + 1.05 * age ** 1.6, (1 - age) ** 1.5 * min(1, age * 12), analysis.note[birth],
                       analysis.bass[birth])
    return rings


def wallpaper_pixels(path):
    """Lee un PNG con ffmpeg, abajo primero como pide OpenGL."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    width, height = (int(value) for value in probe.strip().split(",")[:2])
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "vflip", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return (width, height), data


def dark_wallpaper(colors):
    """Sin ComfyUI: un degradado oscuro de la paleta, para que el video igual salga."""
    rows = np.linspace(0, 1, 256)[:, None] ** 2 * .22
    image = (rows * np.array(colors[1]) * 255).astype(np.uint8)
    return (1, 256), image.tobytes()


def wall_light(size, pixels):
    """Ganancia para las imagenes muy claras, y si el rincon del planeta esta oscuro."""
    image = np.frombuffer(pixels, np.uint8).reshape(size[1], size[0], 3).astype(np.float32) / 255
    light = image @ np.array((.3, .59, .11), dtype=np.float32)
    corner = light[int(size[1] * .55):, size[0] // 2:]  # la primera fila es la de abajo
    return min(1.0, WALL_LEVEL / max(float(light.mean()), 1e-3)), float(corner.mean()) < DARK_SKY


def chroma_key(size, pixels):
    """Color de las pantallas: un tono brillante y saturado que ocupe buena parte de la imagen. None si no hay."""
    image = np.frombuffer(pixels, np.uint8).reshape(size[1], size[0], 3)[::4, ::4].reshape(-1, 3).astype(np.float32) / 255
    top, low = image.max(axis=1), image.min(axis=1)
    vivid = image[(top > .6) & ((top - low) / np.maximum(top, 1e-3) > .4)]
    if not KEY_AREA[0] <= len(vivid) / len(image) <= KEY_AREA[1]:
        return None
    direction = vivid / np.linalg.norm(vivid, axis=1, keepdims=True)
    center = np.median(direction, axis=0)
    center /= np.linalg.norm(center)
    close = vivid[direction @ center > .97]
    return tuple(float(value) for value in close.mean(axis=0)) if len(close) > .6 * len(vivid) else None


class Engine:
    def __init__(self, size, direction, wall):
        self.size = size
        self.width, self.height = size
        self.aspect = self.width / self.height
        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable_only(moderngl.NOTHING)
        self.ctx.gc_mode = "auto"
        self.direction = direction
        vertex = (SHADERS / "pantalla.vert").read_text(encoding="utf-8")
        common = "#version 330\n" + (SHADERS / "comun.glsl").read_text(encoding="utf-8")

        def fragment(name):
            return self.ctx.program(vertex_shader=vertex, fragment_shader=common + (SHADERS / name).read_text(
                encoding="utf-8"))

        self.feedback, self.scene = fragment("feedback.frag"), fragment("escena.frag")
        self.glow, self.final = fragment("brillo.frag"), fragment("final.frag")
        quad = self.ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4").tobytes())
        self.quads = {program: self.ctx.vertex_array(program, [(quad, "2f", "aPos")])
                      for program in (self.feedback, self.scene, self.glow, self.final)}

        self.stars = self.ctx.program(vertex_shader=(SHADERS / "estrellas.vert").read_text(encoding="utf-8"),
                                      fragment_shader=(SHADERS / "estrellas.frag").read_text(encoding="utf-8"))
        rng = np.random.default_rng(direction.seed)
        spots = np.concatenate([rng.uniform(-1, 1, (STARS, 2)), rng.uniform(0, 1, (STARS, 1)),
                                rng.uniform(.6, 2.6, (STARS, 1))], axis=1).astype("f4")
        self.star_array = self.ctx.vertex_array(self.stars, [(self.ctx.buffer(spots.tobytes()), "3f 1f",
                                                              "aStar", "aSize")])

        def target(target_size):
            texture = self.ctx.texture(target_size, 4, dtype="f2")
            texture.repeat_x = texture.repeat_y = False
            return texture, self.ctx.framebuffer([texture])

        self.trail = [target(size), target(size)]
        self.frame_scene = target(size)
        small = (max(1, self.width // GLOW_SIZE), max(1, self.height // GLOW_SIZE))
        self.small = small
        self.blur = [target(small), target(small)]
        self.result = self.ctx.texture(size, 3)
        self.result_target = self.ctx.framebuffer([self.result])

        wall_size, pixels = wall
        self.wall = self.ctx.texture(wall_size, 3, pixels)
        self.wall.repeat_x = self.wall.repeat_y = False
        self.wall_gain, self.planet_on = wall_light(wall_size, pixels)
        self.key = chroma_key(wall_size, pixels)
        self.wall_aspect = wall_size[0] / wall_size[1] if wall_size[0] > 1 else self.aspect
        self.spectrum = self.ctx.texture((espectro.BANDS, 1), 1, dtype="f4")
        self.wave = self.ctx.texture((espectro.WAVE_POINTS, 1), 1, dtype="f4")
        for texture in (self.spectrum, self.wave):
            texture.repeat_x = texture.repeat_y = False
        self.travel = 0.0

    def set(self, program, **values):
        for name, value in values.items():
            if name in program:
                program[name].value = value

    def bind(self, program, **textures):
        for unit, (name, texture) in enumerate(textures.items()):
            texture.use(unit)
            if name in program:
                program[name].value = unit

    def colors(self):
        one, two, three = self.direction.colors
        return {"uCol0": tuple(one), "uCol1": tuple(two), "uCol2": tuple(three)}

    def draw(self, analysis, scenes, frame, total_seconds):
        fps = analysis.fps
        seconds = frame / fps
        bass, mid, treble = (float(values[frame]) for values in (analysis.bass, analysis.mid, analysis.treble))
        beat, energy = float(analysis.beat[frame]), float(analysis.energy[frame])
        old, new, blend = scene_state(scenes, frame, fps)
        warp = style.Warp(*(a + (b - a) * blend for a, b in zip(old.warp, new.warp)))
        per_frame = 60 / fps  # los presets estan pensados a 60 cuadros
        shapes = [0.0] * 4
        shapes[old.shape] += 1 - blend
        shapes[new.shape] += blend
        shared = dict(uTime=seconds, uAspect=self.aspect, uBass=bass, uMid=mid, uTreb=treble, uBeat=beat,
                      uEnergy=energy, **self.colors())

        self.spectrum.write(analysis.spectrum[frame].tobytes())
        self.wave.write(espectro.wave_at(analysis, frame).tobytes())

        previous, current = self.trail
        current[1].use()
        self.set(self.feedback, **shared, uZoom=1 + (warp.zoom - 1) * per_frame, uSpin=warp.spin, uWarp=warp.wave,
                 uDecay=warp.decay ** per_frame, uLift=warp.lift * per_frame, uFold=warp.fold, uShapes=tuple(shapes))
        self.bind(self.feedback, uPrev=previous[0], uSpec=self.spectrum, uWave=self.wave)
        self.quads[self.feedback].render(moderngl.TRIANGLE_STRIP)

        self.travel += (.05 + .22 * energy + .25 * bass) / fps
        self.ctx.enable_only(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE
        self.set(self.stars, uTravel=self.travel, uAspect=self.aspect, uHeight=float(self.height),
                 uTint=tuple(self.direction.colors[0]), uGain=.25 + .7 * energy + .6 * treble)
        self.star_array.render(moderngl.POINTS)
        self.ctx.enable_only(moderngl.NOTHING)
        self.trail = [current, previous]

        self.frame_scene[1].use()
        drift = seconds * .12
        planet = (.70 + .02 * np.sin(drift), .31 + .015 * np.cos(drift * .7), .10, float(self.direction.planet))
        self.set(self.scene, **shared, uDrift=drift, uFractal=energy ** 2, uPlanet=planet,
                 uPlanetOn=float(self.planet_on), uGain=self.wall_gain,
                 uKey=self.key or (1, 1, 1), uKeyOn=float(self.key is not None),
                 uTrail=.12 + .20 * energy + .14 * beat, uWallAspect=self.wall_aspect)
        self.scene["uRing"].write(active_rings(analysis, frame).tobytes())
        self.bind(self.scene, uWall=self.wall, uFeedback=current[0])
        self.quads[self.scene].render(moderngl.TRIANGLE_STRIP)

        for source, target, direction, threshold in (
                (self.frame_scene, self.blur[0], (1.6 / self.small[0], 0), 1.0),
                (self.blur[0], self.blur[1], (0, 1.6 / self.small[1]), 0.0)):
            target[1].use()
            self.set(self.glow, uDir=direction, uThreshold=threshold)
            self.bind(self.glow, uTex=source[0])
            self.quads[self.glow].render(moderngl.TRIANGLE_STRIP)

        self.result_target.use()
        fade = min(1.0, seconds / FADE, max(0.0, (total_seconds - seconds) / FADE))
        self.set(self.final, uTime=seconds, uBeat=beat, uFadeIn=fade, uGlowGain=.9 + .9 * energy)
        self.bind(self.final, uScene=self.frame_scene[0], uGlow=self.blur[1][0])
        self.quads[self.final].render(moderngl.TRIANGLE_STRIP)
        return self.result_target.read(components=3, alignment=1)


def encoder(size, fps, audio, target, start, seconds):
    width, height = size
    audio_input = ["-ss", str(start)] + (["-t", str(seconds)] if seconds else []) + ["-i", str(audio)]
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
               "-r", str(fps), "-i", "-", *audio_input, "-map", "0:v", "-map", "1:a",
               "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-maxrate", "24M", "-bufsize", "48M",
               "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", str(target)]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def render(audio, target, direction, image, fps=60, height=1080, start=0.0, seconds=None):
    """image: ruta PNG; None = fondo oscuro de la paleta."""
    samples = espectro.load(audio, start, seconds)
    analysis = espectro.analyze(samples, fps)
    size = (height * 16 // 9 // 2 * 2, height)
    wall = wallpaper_pixels(image) if image else dark_wallpaper(direction.colors)
    scenes = plan_scenes(analysis, direction)
    print(f"{analysis.frames} cuadros, {len(analysis.beats)} golpes, {len(scenes)} escenas "
          f"en {[round(cut / fps) for cut in analysis.cuts]} s", flush=True)
    engine = Engine(size, direction, wall)
    target.parent.mkdir(parents=True, exist_ok=True)
    process = encoder(size, fps, audio, target, start, seconds)
    total = analysis.frames / fps
    started = time.time()
    for frame in range(analysis.frames):
        process.stdin.write(engine.draw(analysis, scenes, frame, total))
        if frame and frame % (fps * 15) == 0:
            print(f"  {frame / fps:.0f} de {total:.0f} s, {frame / (time.time() - started):.0f} cuadros/s", flush=True)
    process.stdin.close()
    if process.wait():
        raise RuntimeError("ffmpeg no pudo terminar el video.")
    print(f"Listo en {time.time() - started:.0f} s: {target}", flush=True)
    return target


def make(audio, seed, palette=None, idea=None, target=None, comfy=True, ficha=None, **options):
    """Dirige, pide los wallpapers y renderiza. Si este llamado prendio ComfyUI, lo apaga al terminar.

    `ficha`: carpeta de un tema con ficha.json y fondo.png (ficha_tema.py): se usan su puesta y su fondo.
    """
    audio = Path(audio).resolve()
    sheet = Path(ficha) / "ficha.json" if ficha else None
    if sheet and sheet.is_file():
        import json
        record = json.loads(sheet.read_text(encoding="utf-8"))
        direction = style.from_ficha(record, seed)
        image = Path(ficha) / "fondo.png"
        if image.is_file():
            target = Path(target) if target else OUTPUT / f"{audio.stem} {seed}.mp4"
            print(f"Ficha: {direction.palette}; {', '.join(direction.warps)}; {', '.join(direction.shapes)}", flush=True)
            video = render(audio, target, direction, image, **options)
            target.with_suffix(".txt").write_text(
                f"TITULO\n{record['titulo_youtube']}\n\nDESCRIPCION\n{record['descripcion']}\n"
                f"ETIQUETAS\n{', '.join(record['etiquetas'])}\n", encoding="utf-8")
            return video
    else:
        direction = style.direct(seed, palette, idea)
    target = Path(target) if target else OUTPUT / f"{audio.stem} {seed}.mp4"
    print(f"Paleta {direction.palette}; {', '.join(direction.warps)}; {', '.join(direction.shapes)}", flush=True)
    image, process = None, None
    if comfy:
        try:
            image, process = fondo_comfy.wallpaper(direction, OUTPUT / "fondos")
        except (fondo_comfy.ComfyError, OSError) as error:
            print(f"Sin imagen ({error}): sigo con el fondo de la paleta.", flush=True)
    if process:  # el python del entorno lanza un hijo: hay que cerrar el arbol
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    video = render(audio, target, direction, image, **options)
    seo.write(target.with_suffix(".txt"), audio.stem, seed)
    return video


def main():
    parser = argparse.ArgumentParser(description="Video espectral para un tema.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--semilla", type=int, default=1)
    parser.add_argument("--paleta", choices=list(style.PALETTES))
    parser.add_argument("--idea", help="escena que inspira la imagen")
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--alto", type=int, default=1080, help="1080 o 2160")
    parser.add_argument("--desde", type=float, default=0.0, help="segundo de inicio, para pruebas")
    parser.add_argument("--segundos", type=float, help="duracion, para pruebas")
    parser.add_argument("--sin-comfy", action="store_true", help="sin imagen, solo lo procedural")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    make(args.audio, args.semilla, args.paleta, args.idea, args.salida, not args.sin_comfy, fps=args.fps,
         height=args.alto, start=args.desde, seconds=args.segundos)


if __name__ == "__main__":
    sys.exit(main())
