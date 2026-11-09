# Equipo de imagen (reutilizable)

Un equipo de agentes para hacer **una sola imagen de portada** (fondo de video, miniatura, póster) que se mira mucho
tiempo y en la que se van descubriendo cosas. Sirve para este canal y para cualquier otro: cada canal pone su
`identidad` (mundo, paleta, tensiones) en el brief y los roles no cambian.

Sale de dos trabajos anteriores del usuario:
- el equipo de Doble Fondo (`C:\canal starlight rebelion\canal\equipo\`): concepto, casting, vestuario, fotografía,
  cámara y productor. Hecho para videoclips de varias escenas; acá se condensa en un solo cuadro.
- StoryForge (`C:\canal starlight rebelion\ltx studio concept\`): las etapas y los campos de cada departamento
  (premisa, personaje, entorno, plano).

## Etapas (en este orden; cada una recibe lo anterior)

| Rol | Archivo | Qué decide |
|---|---|---|
| Escritor y director de escena | `escritor.md` | la situación: qué pasa justo ahora, el conflicto, la acción física, la mirada, los dos planos |
| Director | `director.md` | que la acción tenga sentido y se entienda qué hace la persona y para qué; si no, reescribe la escena |
| Casting | `casting.md` | la cara y el cuerpo de la persona (edad visible), sin ropa |
| Vestuario | `vestuario.md` | la ropa pieza por pieza, materiales, desgaste, objetos que lleva encima |
| Dirección de arte | `arte.md` | el lugar, los objetos y artefactos con marcas de uso, la profundidad, la atmósfera |
| Fotógrafo | `fotografo.md` | plano, ángulo, lente, foco, cada luz y su color, la paleta |
| Continuidad | `continuidad.md` | que la toma no se repita con las ya hechas (acción, objeto, lugar, encuadre); pide cambios a los departamentos |
| Productor | `productor.md` | puntúa el resultado contra la identidad y la lista de control; aprueba o pide correcciones |
| Postproducción | `postproduccion.md` | el acabado de la imagen ya generada (color, halo, grano, viñeta); lo hace Python, no el modelo |

El prompt final es la suma de escena + casting + vestuario + arte + fotografía (300 a 450 palabras). Las pruebas del
2026-11-07 mostraron que un prompt largo y concreto da imágenes mucho más ricas que uno corto.

## Cómo se usa (estudio_imagen.py)
Siempre en dos fases, para no tener Ollama (~39 GB) y Z-Image (~18 GB) cargados a la vez:

```
python estudio_imagen.py prompts briefs/*.json --salida imagenes/tanda1   # fase 1: Ollama, un .prompt.json por brief
python estudio_imagen.py imagenes imagenes/tanda1                         # fase 2: ComfyUI, un .png por prompt
python estudio_imagen.py todo briefs/*.json --salida imagenes/tanda1      # las dos, una despues de la otra
```

- Un **brief** es un JSON con `titulo`, `idea`, `emocion`, `paleta` y opcionalmente `identidad`, `concepto` y
  `semilla` (ejemplo en `briefs/ejemplo.json`). Sin `identidad` usa la cyberpunk del canal.
- Entre las dos fases se pueden **leer y editar los prompts**. También se puede poner en la carpeta un `.txt` con un
  prompt escrito a mano: la fase 2 lo toma igual.
- Para otro canal: otro brief (otra `identidad`) y, si hace falta, otro estilo en `visual_estilo.STYLE_ZIMAGE`.
- `ficha_tema.py` usa este mismo estudio para el fondo de cada tema.
- **Cada departamento queda guardado** (`equipo/escritor.json`, `casting.json`, `vestuario.json`, `arte.json`,
  `fotografo.json`, más `prompt.txt` y `productor.json`). Si algo hay que mejorar, se pide a ese departamento solo y
  el resto se reusa, así tarda lo que tarda un rol y no el equipo entero:
  - en las fichas: `python ficha_tema.py 2059 --mejorar vestuario "que use botas, no descalza" --mejorar casting "un
    hombre de unos 50"` y después `python ficha_tema.py 2059 --solo-imagen`;
  - en el estudio: el brief lleva `"mejorar": {"vestuario": "..."}` y se vuelve a correr la fase `prompts`.

## Decisiones tomadas (2026-11-07, con el usuario)
Están en `estudio_imagen.DECISIONES`. En corto: Z-Image Turbo; prompts largos del equipo con la persona primero;
3 candidatas y la mejor en grande (2880×1632); acabado con bloom fuerte y difuso y negros suaves; personas adultas, sin
texto legible ni obras existentes; si Ollama falla, no se inventa nada.

## Reglas comunes a todos los roles
- Solo cosas que se ven, en frases concretas, en inglés lo que va al prompt. Nada de sentimientos explicados.
- Personas siempre adultas, con la edad visible en la cara (arrugas, canas, rasgos), no solo un número.
- Diseño propio: ningún personaje, robot, nave, logo, traje ni cuadro de una obra existente. Nada de texto legible.
- **Cada rol describe solo lo suyo**: vestuario la ropa, arte el lugar, casting la cara. No repitas a la persona ni
  lo que ya escribió otro rol: el prompt final los junta y las repeticiones lo hacen largo y confuso.
- Nada de texto legible en ningún objeto: etiquetas con palabras, números en relojes, cuentas regresivas, pantallas
  con letras. Las pantallas muestran formas (ondas, radar, líneas).
- Todo lo que va al prompt en inglés: nada de palabras en castellano mezcladas ("lana", "goma").
- **Dados** (`dados` en el brief): género, edad, piel, pelo, prenda principal, lugar y esquema de luz salen de
  la semilla, también la acción con su objeto y el color del acento. Son
  obligatorios: casting usa ese género, edad, piel y pelo; vestuario, esa prenda principal; arte, ese tipo de lugar; el fotógrafo, ese esquema de
  luz (la línea láser solo con "Mira laser"). Ollama repetía siempre lo mismo; los dados lo obligan a variar.
- La pantalla CRT y el cable rojo aparecían en todos los temas: ahora solo van si los dados lo piden; el acento
  de color es el de los dados.

## Universo y revisión (2026-11-07)
- **Universo** (`universo/universo.json`, `universo.py`): 12 personajes originales sobre arquetipos del cyberpunk
  (netrunner, cirujana clandestina, mensajera, desertora corporativa, locutor pirata...) y 17 lugares, con historia,
  deseo, miedo, secreto, gestos y relaciones. Cada tema recibe un personaje (rotan sin repetir seguidos), uno de sus
  lugares y un gesto que encaja ahí. Lo que hizo queda en su arco y el próximo tema lo sabe.
  `python universo.py elenco 2048 2087` muestra quién sale en cada tema.
- **Revisión antes de las imágenes** (`revisar_prompts.py`): por tema, quién, dónde, qué hace y para qué, puntajes,
  continuidad, parecidos dentro de la tanda y problemas conocidos (cable a una pantalla, ojos cerrados, linterna a la
  nada, mano contra el vidrio, texto legible). Deja `Agente Frequency/revision_prompts.md`. Las imágenes se hacen
  después, con lo que esté OK; lo demás se corrige con `--mejorar`.
