# FLBridge

Túnel en Python para controlar FL Studio 21 desde la terminal o desde Claude (MCP).

```
Claude / flctl.py  <-- SysEx por loopMIDI -->  device_FLBridge.py (dentro de FL)  -->  API de FL
```

El Python de FL es un 3.9 sin biblioteca estándar ni sockets, y FL bloquea el acceso a
archivos (`open` no existe y `_io.open` da `File access not allowed`). El único canal
posible es MIDI. El cliente usa winmm directamente porque `python-rtmidi` no tiene
wheel para Python 3.14.

## Puesta en marcha

1. Instala el puerto virtual: `winget install TobiasErichsen.loopMIDI`
2. Abre loopMIDI y crea un puerto llamado `loopMIDI Port`. Debe estar abierto antes que FL.
3. Instala el script: `.venv\Scripts\python install.py`
4. En FL pulsa F10. En **Input** selecciona `loopMIDI Port`, activa Enable, pon el
   puerto 200 y en Controller type elige **FLBridge**. En **Output** selecciona
   `loopMIDI Port` con el mismo puerto 200.
5. Comprueba: `.venv\Scripts\python flctl.py status`

Para Claude Code, abre esta carpeta y aprueba el servidor `fl-studio` de `.mcp.json`.

Ejecutar comandos o enviar MIDI desde `OnSysEx` cuelga FL (CPU en cero): el script
solo guarda ahí el pedido y hace el trabajo en `OnIdle`.

## Comandos

```
flctl.py status | play | stop | tempo 128
flctl.py functions mixer                    # funciones reales de tu versión de FL
flctl.py call mixer setTrackVolume 1 0.8    # cualquier función de la API
flctl.py preset list | preset run trap_140
flctl.py theme list | theme apply Vino | theme reset
flctl.py render cancion.flp mp3             # con FL cerrado; sale junto al .flp
```

Módulos permitidos: arrangement, bridge, channels, device, general, mixer, patterns,
playlist, plugins, transport y ui.

## Presets de proyecto

Son archivos JSON en `presets/`, con una lista de comandos que se ejecutan en orden
y se detienen en el primer error:

```json
{"description": "...", "commands": [["bridge", "setTempo", 140], ["mixer", "setTrackName", 1, "Kick"]]}
```

## Temas visuales

Los temas funcionan sin el túnel, pero **FL debe estar cerrado** y se ven al volver a
abrirlo: FL solo lee `Settings\Themes\__current.flstheme` al arrancar. Una ruta en
`ThemeFilename` no sirve; FL la ignora y la borra.

Para crear uno: `fl.create_theme("Nombre", base="Dark", Hue=20, Selected="#00E5FF")`
o la herramienta MCP `fl_create_theme`.

## Pruebas

`.venv\Scripts\python -m unittest tests.test_tunnel` ejecuta el script real de FL
contra una API simulada.

## Arreglo y efectos

La API no puede colocar clips ni cargar plugins, así que `flp_edit.py` los escribe en el
`.flp` con FL cerrado. `build_tema.py` es el ejemplo completo. Los efectos se copian de
los proyectos que trae FL, con sus ajustes; después hay que afinarlos en vivo con
`plugins.setParamValue`. Solo está probado con archivos guardados por FL 21.1.

`build_synthwave.py` compone un tema completo agregando canales, notas y presets `.fst`.
Después, con el proyecto abierto en FL, `mix_synthwave.py` aplica y guarda la mezcla.
Reconstruir borra la mezcla: hay que volver a correr los dos.

## Ruta Neon Epica

Mismo tema que Ruta Neon, armado como el video de referencia: un instrumento por pista de la
playlist, buses de Bateria y Sintes, retornos de Reverb y Delay, y sidechain del Kick sobre los sintes.

1. Con FL cerrado: `python build_epico.py "<Primer Tema.base.flp>" "<Ruta Neon Epica.flp>"`
2. Abre el proyecto en FL: `python mix_epico.py "<Ruta Neon Epica.flp>"`

Reconstruir borra lo que se haya cambiado a mano en el proyecto.

## Ruta Neon Dune

Ruta Neon Epica con patches de Dune 3 (necesita Dune 3 escaneado en FL). Mismos pasos con
`build_dune.py` y `mix_dune.py`. Kickstart 2 dejo el bus en silencio y colgo FL al ponerlo en bypass,
asi que el bombeo sigue con Fruity Limiter y sidechain.

## Copia de estudio y carpeta pruebas

`pruebas/` guarda los proyectos de prueba. `build_copia.py` y `mix_copia.py` arman el loop del video
de referencia para igualar el sonido. Es un paso privado: cambia las notas antes de publicar.
Serum 2 acepta sus `.SerumPreset` por `flp.set_serum_preset`, que necesita `cbor2`.

## Starlight Rebellion

Tema original en Fa# menor, 100 BPM, 80 compases, en 10 versiones. La tabla `VERSIONS` de
`build_starlight.py` define melodia, lead, efecto, arpegio, reverb, delay y ganancia de cada una.

```
python render_starlight.py "pruebas\Primer Tema.base.flp" "Starlight Rebellion"        # las 10
python render_starlight.py "pruebas\Primer Tema.base.flp" "Starlight Rebellion" 3 7    # solo esas
```

Abre y cierra FL en cada version, unos 2 minutos cada una: no uses FL mientras corre. FL se queda
preguntando si guarda al terminar un render con VST; `fl.render` lo cierra solo cuando el WAV esta
completo, porque el proyecto ya estaba guardado.

## Agente musical

`agente_musical.bat` arma un tema de cero. Los dados eligen tonalidad, escala, ensamble, estructura,
lead y densidad; Ollama decide el resto con el rol de `agente_frequency.txt`, y `compositor.py`
escribe las notas. `estilo_frequency.py` guarda lo que se puede elegir.

```
agente_musical.bat                     # un tema nuevo
agente_musical.bat --n 3               # tres temas
agente_musical.bat --semilla 123       # repite la semilla
agente_musical.bat --motor azar        # sin Ollama
agente_musical.bat --sin-fl            # solo .mid y ficha
agente_musical.bat --modelo qwen2.5:14b-instruct
```

Cada tema queda en `Agente Frequency\<titulo> <semilla>\`. Si FL esta abierto con cambios sin
guardar, el agente se detiene sin tocarlo.

## Video espectral
Arma el video de cualquier tema: `video_espectral.bat "tema.mp3" --semilla 7`, o soltando el audio sobre el `.bat`. Desde el agente: `agente_musical.bat --video`, que elige paleta e idea segun el tema.

Cada video usa una sola imagen fija de anime cyberpunk, como el canal de referencia. Lo que cambia por seccion es lo procedural: deformacion y forma del espectro. Junto al `.mp4` deja un `.txt` con titulo, descripcion y etiquetas.

- `espectro.py`: espectro, graves, golpes, nota dominante y secciones, con numpy.
- `visual_estilo.py`: paletas de Cosmos, motivos de la imagen y deformaciones tipo MilkDrop.
- `fondo_comfy.py`: la imagen con Flux schnell. Prende ComfyUI si hace falta y la guarda en `Video Espectralondos`.
- `video_espectral.py` y `shaders\`: render por GPU sin ventana con moderngl, y salida H.264 por NVENC.
- `seo_youtube.py`: formula de titulos y etiquetas, sin nombrar a otros artistas.
- `analizar_mix.py`: mide un mix largo y deja estadisticas en `universo_frequency.json`, sin audio ni melodias.

Opciones: `--paleta`, `--idea`, `--desde 60 --segundos 15` (prueba corta), `--sin-comfy`, `--alto 2160`, `--fps 30`. Requiere `pip install moderngl` en `.venv`.

## Pigments (Arturia)

`pigments.py` lee los presets de fabrica de Pigments (texto de Boost serialization en
`C:\ProgramData\Arturia\Presets\Pigments`) y crea presets nuevos copiando uno y cambiando valores;
lo demas del archivo queda igual. El servidor MCP `pigments` de `.mcp.json` (`mcp_pigments.py`) da
`pigments_buscar`, `pigments_leer`, `pigments_opciones` y `pigments_crear`. Los presets nuevos van a
`presets/pigments/`. Los valores van de 0 a 1; motores, filtros y efectos se eligen por nombre segun
la version de Pigments del preset base. Falta probar que Pigments los cargue.

## Mix de temas

`python playlist.py 2038 2039 ... --semilla 11 --paleta Noche` une temas del agente a -14 LUFS con
fundido cruzado, ordenados por tempo, y renderiza un solo video con tracklist y capitulos.

### Capa de ambiente

El agente agrega un canal "Ambiente" con Pigments (preset `Starlight Ambiente`, pista 16 del mixer, sale al Bus Sintes para bombear con el kick). Toca los acordes largos una octava arriba del pad: fuerte en intro, break y outro, bajo en los coros y en crescendo en el build. La plantilla `presets/pigments_template.fst` es un canal Pigments guardado desde FL; el preset se escribe adentro sin abrir Pigments.

## Ficha de cada tema (visual + SEO)

`python ficha_tema.py 2048 2049 ...` (sin semillas: todos los temas de `Agente Frequency`). Por tema:

1. Mide la energia de la musica (BPM, bateria, bajo, densidad de la melodia) y el caracter de la escala.
2. Le pide a Ollama la escena del fondo (solo el lugar: el personaje sale de la lista del canal), paleta, deformacion,
   forma del espectro, uso (manejar, estudiar...), genero, gancho, descripcion y palabras clave. Las opciones se
   limitan segun la energia: un tema calmo no gira como un tunel.
3. Revisa la respuesta: opciones validas, escena dibujable sin texto ni personas extra (si falla, Ollama la rehace una
   vez), sin artistas ni obras, limites de YouTube (titulo 100, etiquetas 500). Lo que corrige queda anotado.
4. Pide el fondo a ComfyUI (Flux schnell) y mide brillo y contraste; si no pasa prueba hasta 3 semillas.
5. Deja `ficha.json`, `fondo.png` y `<tema> ficha.md`. No renderiza nada.

El video (`--video` del agente o `video_espectral.make(..., ficha=carpeta)`) usa esa paleta, deformacion, forma y fondo.
El titulo de YouTube sigue el patron que mejor rindio en el canal (`NOMBRE // Genero · 90s Anime Uso Ano`); los datos
estan anotados en `seo_youtube.py`.

Ambiente: cada tema elige un pad de Pigments segun el ensamble (`estilo_frequency.AMBIENTS`). Tempo, arpegio, bajo y
bateria salen de los dados: Ollama elegia siempre los mismos.

### Equipo de imagen y postproducción (2026-11-07)

La ficha arma el fondo con un equipo reutilizable (`agentes/`, `equipo_imagen.py`): escritor y director de escena,
casting, vestuario, dirección de arte, fotógrafo y productor, adaptados del equipo de Doble Fondo y de StoryForge.
El prompt sale largo (300-700 palabras) y concreto. Imágenes con Z-Image Turbo: 3 candidatas, la mejor se rehace en
grande (2880×1632) y `postproceso.py` le da el acabado (color, bloom fuerte y difuso, aberración, viñeta, grano).
Dos fases que no comparten memoria: `ficha_tema.py ... --sin-imagen` (Ollama) y `ficha_tema.py ... --solo-imagen`
(ComfyUI). El equipo descarga a Ollama al terminar.
