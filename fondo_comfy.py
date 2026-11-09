"""Pide a ComfyUI local la imagen del video, con Flux schnell. Si ComfyUI esta apagado lo prende."""
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

URL = "http://127.0.0.1:8188"
COMFY_DIR = Path("C:/pinokio/api/comfy.git/app")
START_ARGS = ("--reserve-vram", "2.5")  # los mismos que usa el canal
WIDTH, HEIGHT = 1920, 1088  # Flux pide multiplos de 16
START_TIMEOUT = 240
IMAGE_TIMEOUT = 600


class ComfyError(RuntimeError):
    pass


def workflow(prompt, seed, width=WIDTH, height=HEIGHT):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
                                                   "scheduler": "simple", "denoise": 1.0, "model": ["1", 0],
                                                   "positive": ["2", 0], "negative": ["3", 0],
                                                   "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VideoEspectral/fondo", "images": ["6", 0]}},
    }


def call(path, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(URL + path, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def running():
    try:
        call("/system_stats", timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        return False


def start(log):
    """Devuelve el proceso si lo prendio esta llamada; None si ya estaba."""
    if running():
        return None
    python = COMFY_DIR / "env/Scripts/python.exe"
    if not python.is_file():
        raise ComfyError(f"No encuentro {python}. Prende ComfyUI desde Pinokio.")
    print("Prendiendo ComfyUI...", flush=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as output:
        process = subprocess.Popen([str(python), "main.py", *START_ARGS], cwd=COMFY_DIR, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    limit = time.time() + START_TIMEOUT
    while time.time() < limit:
        if running():
            return process
        if process.poll() is not None:
            raise ComfyError(f"ComfyUI se cerro al arrancar. Mira {log}.")
        time.sleep(3)
    process.kill()
    raise ComfyError("ComfyUI no respondio a tiempo.")


DEV_MODEL = "flux1-dev-kontext_fp8_scaled.safetensors"
DEV_STEPS, DEV_GUIDANCE = 28, 3.5  # 3.0 daba colores lavados


# LoRA de estilo (models/loras de ComfyUI): (archivo, fuerza, frase que lo activa). El prompt solo no llegaba al
# look de OVA de los 90 de las referencias del usuario (referencias/fotografo/).
LORAS = {
    "synthetic": ("Flux_1_Dev_LoRA_syntheticanime.safetensors", 1.0, "1980s anime screengrab, VHS quality"),
    "glif90": ("flux_dev_90s_anime_glif.safetensors", 1.0, ""),
}
LORA = "glif90"  # el usuario eligio la fila de glif sobre SyntheticAnime


def dev_workflow(prompt, seed, width=WIDTH, height=HEIGHT, lora=None):
    """Flux dev (el Kontext del canal, sin imagen de referencia): mas pasos, menos errores que schnell."""
    graph = _dev_graph(prompt, seed, width, height)
    if lora:
        name, strength, trigger = LORAS[lora]
        graph["10"] = {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"model": ["1", 0], "lora_name": name, "strength_model": strength}}
        graph["8"]["inputs"]["model"] = ["10", 0]
        if trigger:
            graph["4"]["inputs"]["text"] = f"{trigger}, {prompt}"
    return graph


def _dev_graph(prompt, seed, width, height):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": DEV_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors",
                                                         "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": DEV_GUIDANCE}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": DEV_STEPS, "cfg": 1.0, "sampler_name": "euler",
                                                   "scheduler": "simple", "denoise": 1.0, "model": ["1", 0],
                                                   "positive": ["5", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "fondo_dev"}},
    }


# Z-Image Turbo (Alibaba, Apache 2.0): el modelo con el que se hicieron las referencias que mas le gustaron al usuario.
ZIMAGE_MODEL = "z_image_turbo_bf16.safetensors"
ZIMAGE_TEXT = "qwen_3_4b_fp8_mixed.safetensors"
ZIMAGE_STEPS, ZIMAGE_SHIFT = 9, 3.0
ZIMAGE_LORAS = {"zart3": ("Z-Art-3.safetensors", .8, "art, anime, digital art")}


def zimage_hires(prompt, seed, scale=1.5, denoise=.45, lora=None):
    """Dos pasadas: la imagen normal y despues 1,5x redibujada en parte, para sumar detalle fino (~100 s)."""
    graph = zimage_workflow(prompt, seed, lora=lora)
    graph["12"] = {"class_type": "LatentUpscaleBy", "inputs": {"samples": ["8", 0], "upscale_method": "bislerp",
                                                                "scale_by": scale}}
    graph["13"] = {"class_type": "KSampler", "inputs": {**graph["8"]["inputs"], "denoise": denoise,
                                                        "latent_image": ["12", 0]}}
    graph["9"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["13", 0], "vae": ["3", 0], "tile_size": 1024,
                                                             "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    return graph


def zimage_workflow(prompt, seed, width=WIDTH, height=HEIGHT, lora=None):
    """Plantilla oficial de ComfyUI para Z-Image Turbo: 9 pasos, cfg 1, res_multistep, AuraFlow shift 3."""
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": ZIMAGE_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ZIMAGE_TEXT, "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "11": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": ZIMAGE_SHIFT}},
        "8": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": ZIMAGE_STEPS, "cfg": 1.0,
                                                   "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0,
                                                   "model": ["11", 0], "positive": ["4", 0], "negative": ["5", 0],
                                                   "latent_image": ["6", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "fondo_zimage"}},
    }
    if lora:
        name, strength, trigger = ZIMAGE_LORAS[lora]
        graph["10"] = {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"model": ["1", 0], "lora_name": name, "strength_model": strength}}
        graph["11"]["inputs"]["model"] = ["10", 0]
        if trigger:
            graph["4"]["inputs"]["text"] = f"{trigger}, {prompt}"
    return graph


def run(graph, target, output="7", timeout=IMAGE_TIMEOUT):
    """Encola un grafo, espera la imagen del nodo `output` y la baja a `target`."""
    client = uuid.uuid4().hex
    queued = json.loads(call("/prompt", {"prompt": graph, "client_id": client}))
    prompt_id = queued["prompt_id"]
    limit = time.time() + timeout
    while time.time() < limit:
        history = json.loads(call(f"/history/{prompt_id}")).get(prompt_id)
        if history:
            produced = history.get("outputs", {}).get(output, {})
            images = produced.get("images") or produced.get("videos") or produced.get("gifs")   # SaveVideo tambien
            if not images:
                raise ComfyError(f"ComfyUI no devolvio imagen: {json.dumps(history.get('status'))[:500]}")
            query = urllib.parse.urlencode({key: images[0][key] for key in ("filename", "subfolder", "type")})
            Path(target).write_bytes(call(f"/view?{query}", timeout=60))
            return Path(target)
        time.sleep(1)
    raise ComfyError("ComfyUI tardo demasiado en la imagen.")


def generate(prompt, seed, target, model="schnell", lora=None, hires=False):
    """Genera una imagen y la baja a target."""
    if model == "zimage" and hires:
        graph = zimage_hires(prompt, seed, lora=lora)
    elif model == "zimage":
        graph = zimage_workflow(prompt, seed, lora=lora)
    elif model == "dev":
        graph = dev_workflow(prompt, seed, lora=lora)
    else:
        graph = workflow(prompt, seed)
    return run(graph, target)


def free():
    """Descarga los modelos de ComfyUI (al cambiar de modelo o al terminar)."""
    call("/free", {"unload_models": True, "free_memory": True}, timeout=60)


def upload(path):
    """Sube una imagen a la carpeta input de ComfyUI. Devuelve el nombre con que quedo (resumen del contenido)."""
    data = Path(path).read_bytes()
    name = f"ref_{hashlib.sha1(data).hexdigest()[:16]}{Path(path).suffix.lower() or '.png'}"
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(URL + "/upload/image", body,
                                     {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read()).get("name", name)


# Wan 2.2: clip entre la imagen de inicio y la de fin (el workflow probado de Doble Fondo, 14B + LoRA de 4 pasos +
# interpolacion FILM x2). Con imagen de fin se cambia WanImageToVideo por WanFirstLastFrameToVideo.
WAN_WORKFLOW = Path(r"C:\canal starlight rebelion\workflows\clip_wan22_14b_light_API.json")
WAN_OUTPUT = "108"
WAN_NEGATIVE = ("deformed face, morphing face, face changing identity, extra fingers, fused fingers, deformed hands, "
                "extra limbs, floating objects, flickering, static, frozen, still image, text, subtitles, watermark, blurry")


def wan_clip_workflow(prompt, seed, start_image, end_image=None, width=896, height=512, frames=49):
    """Grafo de Wan 2.2 i2v (o primer y ultimo cuadro si hay end_image). Frames = 4n+1 (Wan los pide asi)."""
    graph = json.loads(WAN_WORKFLOW.read_text(encoding="utf-8"))
    frames = int(frames) - (int(frames) - 1) % 4
    graph["97"]["inputs"]["image"] = start_image
    graph["129_93"]["inputs"]["text"] = prompt
    graph["129_89"]["inputs"]["text"] = WAN_NEGATIVE
    graph["129_86"]["inputs"]["noise_seed"] = int(seed)
    graph["108"]["inputs"]["filename_prefix"] = "StoryForge/clip"
    video = graph["129_98"]
    video["inputs"].update(width=int(width), height=int(height), length=frames)
    if end_image:
        graph["97_fin"] = {"class_type": "LoadImage", "inputs": {"image": end_image}}
        video["class_type"] = "WanFirstLastFrameToVideo"
        video["inputs"]["end_image"] = ["97_fin", 0]
    return graph


# Flux Kontext: imagen nueva a partir de referencias (como el estudio de Doble Fondo, workflows/identidad_kontext_API)
KONTEXT_GUIDANCE, KONTEXT_STEPS = 2.5, 20


def kontext_workflow(prompt, seed, images, width=1344, height=768, mode="stitch", lora=None, lora_strength=.7,
                     guidance=KONTEXT_GUIDANCE, steps=KONTEXT_STEPS):
    """`images`: nombres ya subidos con upload(). mode "stitch" las pega en una sola referencia (ImageStitch);
    "chain" encadena un ReferenceLatent por imagen. El latente de salida es nuevo (width x height), no el collage."""
    if not images:
        raise ValueError("Kontext necesita al menos una imagen de referencia")
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": DEV_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors",
                                                         "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
    }
    loads = []
    for number, name in enumerate(images):
        node = f"20{number}"
        graph[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
        loads.append(node)
    conditioning = ["4", 0]
    if mode == "stitch":
        joined = [loads[0], 0]
        for number, node in enumerate(loads[1:], 1):
            stitch = f"21{number}"
            graph[stitch] = {"class_type": "ImageStitch", "inputs": {"image1": joined, "image2": [node, 0],
                             "direction": "right", "match_image_size": True, "spacing_width": 0,
                             "spacing_color": "white"}}
            joined = [stitch, 0]
        sources = [joined]
    else:
        sources = [[node, 0] for node in loads]
    for number, source in enumerate(sources):
        scale, encode, reference = f"22{number}", f"23{number}", f"24{number}"
        graph[scale] = {"class_type": "FluxKontextImageScale", "inputs": {"image": source}}
        graph[encode] = {"class_type": "VAEEncode", "inputs": {"pixels": [scale, 0], "vae": ["3", 0]}}
        graph[reference] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": conditioning,
                                                                        "latent": [encode, 0]}}
        conditioning = [reference, 0]
    graph["9"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": conditioning, "guidance": guidance}}
    model = ["1", 0]
    if lora:
        graph["10"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": LORAS[lora][0],
                                                                       "strength_model": lora_strength}}
        model = ["10", 0]
    graph["8"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler",
                                                       "scheduler": "simple", "denoise": 1.0, "model": model,
                                                       "positive": ["9", 0], "negative": ["5", 0],
                                                       "latent_image": ["6", 0]}}
    graph["11"] = {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}}
    graph["7"] = {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "kontext"}}
    return graph


def zimage_img2img(prompt, seed, image, denoise=.4, width=WIDTH, height=HEIGHT, hires_denoise=None):
    """Pasada de estilo: la imagen (ya subida) se redibuja con Z-Image con poco denoise para el look del canal.
    Con `hires_denoise` agrega la segunda pasada 1,5x (como zimage_hires) y decodifica por mosaicos."""
    graph = zimage_workflow(prompt, seed, width, height)
    graph["20"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    graph["21"] = {"class_type": "ImageScale", "inputs": {"image": ["20", 0], "upscale_method": "lanczos",
                                                          "width": width, "height": height, "crop": "center"}}
    graph["22"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["3", 0]}}
    graph["8"]["inputs"].update(latent_image=["22", 0], denoise=denoise)
    del graph["6"]
    if hires_denoise:
        graph["12"] = {"class_type": "LatentUpscaleBy", "inputs": {"samples": ["8", 0], "upscale_method": "bislerp",
                                                                    "scale_by": 1.5}}
        graph["13"] = {"class_type": "KSampler", "inputs": {**graph["8"]["inputs"], "denoise": hires_denoise,
                                                            "latent_image": ["12", 0]}}
        graph["9"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["13", 0], "vae": ["3", 0], "tile_size": 1024,
                                                                 "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    return graph


def wallpaper(direction, folder):
    """La imagen del video. Si ya existe no se regenera; al terminar libera la memoria de video."""
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(direction.prompt.encode()).hexdigest()[:8]
    target = folder / f"fondo {direction.seed} {name}.png"
    if target.is_file():
        return target, None
    process = start(folder / "comfyui.log")
    started = time.time()
    generate(direction.prompt, direction.seed, target)
    print(f"  {target.name}: {time.time() - started:.0f} s", flush=True)
    call("/free", {"unload_models": True, "free_memory": True}, timeout=60)
    return target, process
