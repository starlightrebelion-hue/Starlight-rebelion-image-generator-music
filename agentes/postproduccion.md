# Postproducción

El acabado de la imagen ya generada. No lo hace el modelo de imagen ni Ollama: lo hace `postproceso.py` con ffmpeg,
igual siempre, para que todos los fondos del canal tengan el mismo acabado de película de los 90.

## Pasos (en este orden)
1. **Tamaño final**: la imagen grande (2880×1632, segunda pasada) se achica a 1920×1080 con lanczos; achicar conserva
   el detalle fino y limpia artefactos.
2. **Nitidez suave**: un unsharp leve para que las líneas de tinta se vean firmes.
3. **Color (grade)**: sombras hacia el azul o el violeta de la paleta, luces apenas cálidas, un poco más de contraste y
   de saturación en los medios. La curva depende de la paleta del tema.
4. **Halo (halation)**: las luces fuertes sangran un brillo suave y cálido, como en la película fotográfica.
5. **Aberración cromática**: un desfase de 1 a 2 píxeles entre rojo y azul, solo hacia los bordes del cuadro.
6. **Viñeta**: oscurece apenas los bordes para llevar la mirada al centro.
7. **Grano**: grano fino de película, más visible en las sombras.

## Reglas
- Sutil: si se nota el efecto antes que la imagen, está de más.
- No tapa la zona de abajo a la derecha (ahí YouTube pone la duración): la viñeta es pareja.
- Se guarda también la imagen sin postproducción, para poder rehacer el acabado.
