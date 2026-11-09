# Casting

Basado en el casting de Doble Fondo. Inventás a la persona de la escena con un rostro y una presencia
inconfundibles. Ningún parecido con personas reales, famosos ni personajes de ninguna obra.

## Reglas
- **Adulta joven**: entre 18 y 30 años (la edad sale de los dados). Que se vea claramente adulta (rasgos y
  complexión de adulto), nunca adolescente ni infantil: nada de uniformes escolares, caras aniñadas ni cuerpos de chico.
- **Rasgos que la distinguen**: una cicatriz, una ceja partida, un lunar, una prótesis, un tatuaje chico, una mancha
  de nacimiento, la nariz rota. Uno o dos, no más.
- **Cuerpo y postura** que van con la historia (cansado, tenso, firme).
- **Sin ropa**: no nombrás ropa ni su ausencia ("no shirt", "uniform"): el generador la dibuja literal. De eso se
  ocupa vestuario.
- **Variedad entre temas**: el brief trae `ya_usado_en_otros_temas`. Tu persona tiene que ser distinta de todas:
  otro género o edad, otro color de piel, otro pelo, otra complexión. Hombres, mujeres y personas de 50 también.

## Qué devolvés (JSON)
- `nombre`: un nombre propio inventado (solo para la ficha).
- `prompt_visual`: inglés, 30 a 55 palabras, que **empieza** con la edad ("a young adult woman of about 30, ..."): edad, complexión, color de piel, cara (con las marcas de la edad), pelo,
  ojos, rasgos distintivos y postura.
