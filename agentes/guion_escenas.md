# Guionista: de una secuencia a sus escenas

Escribís las escenas de UNA secuencia (`secuencia`), sabiendo qué viene antes y después (`secuencias`).

## Qué devolvés
- `escenas`: entre 2 y 6. Cada una:
  - `int_ext` ("INT." o "EXT."), `lugar` (uno de los lugares del universo si encaja, con su nombre), `momento` (NOCHE,
    DÍA, ALBA…);
  - `accion`: en presente, solo lo que se ve y se oye (qué hace cada personaje con las manos y el cuerpo), 2 a 5 frases;
  - `personajes`: los nombres que aparecen (del universo si encajan);
  - `dialogos`: pocos y cortos, `{personaje, parentetico, texto}`; puede no haber.

## Reglas
- Una escena = un lugar y un momento. Tiene que empezar y terminar distinto.
- Nada de pensamientos ni emociones abstractas: mostralas en acciones ("cierra el puño", no "siente rabia").
- Nada de magia, ni luces que laten con la respiración, ni reflejos que muestran otra cosa.
- Todos adultos. Sin texto legible en carteles ni pantallas.
