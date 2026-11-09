# Método de historia del canal (adaptado de Doble Fondo)

Viene de `C:\canal starlight rebelion\canal\narrativa.md` (el método de guion simbólico de Doble Fondo), aplicado a
este canal: un tema instrumental de synthwave con **una sola imagen** (más los visuales procedurales). Lo lee el
director creativo de `ficha_tema.py` antes de escribir la escena. Lo puede ajustar el usuario o Claude Code.

La imagen **no ilustra** el título. Construye una *situación paralela* que hace verdadera la emoción del tema. El
título dispara la idea, pero no es el decorado.

## 1. Tensión fija del canal (siempre presente, nunca explicada)
- **El rebelde contra el sistema que brilla**: alguien chico frente a algo enorme, ordenado y luminoso. Un gesto de
  desobediencia mínimo: una luz que se apaga, una puerta forzada, una antena casera, un cable cortado.
- **La noche como refugio y escape**: la huida ya empezó o está por empezar. Un vehículo cargado, un mapa, una
  valija, un motor caliente, una ventana abierta.
- **Nostalgia de un futuro que no llegó**: tecnología vieja que todavía funciona (casete, CRT, walkman, polaroid,
  cabina de teléfono) frente a un futuro enorme y frío.
- **Romance peligroso bajo neón**: dos que no pueden estar juntos. Se cuenta con objetos (un casco de más, dos tazas,
  una campera ajena, una nota doblada), casi nunca con dos personas abrazadas.

## 2. Reglas anti-literal
1. **Lo literal se traduce.** Lo que nombra el título (lugar, objeto, momento) se cambia por otro mundo que da la
   misma sensación. "Puerto" puede ser una estación orbital, un hangar o una terminal de micros vacía.
2. **Como mucho una ancla literal**: un solo elemento del título aparece tal cual, para que el público conecte.
3. **La imagen es una metáfora visible**: se entiende sin explicación y se describe en una frase.
4. **El símbolo se descubre**: hay un detalle que no se ve al primer vistazo y que cambia el sentido de la imagen.
5. **Nada de la escena obvia**: nada de "chica mirando la ciudad" ni "ruta vacía con luna". Mostrar la consecuencia,
   el momento justo antes o la contracara.

## 3. Dos planos en un mismo cuadro
En un videoclip son dos líneas de tiempo; acá, en una sola imagen, son **dos planos que conviven en el cuadro**:
- **Plano A, la superficie**: lo que se ve primero; el mundo ordenado, brillante, controlado.
- **Plano B, lo que se esconde**: instinto, memoria, huida, deseo; otra luz (más cálida o más roja) y otro objeto.
- **El plano B es físico y real, está en el cuadro**: alguien que se acerca al fondo, una amenaza (un dron, un
  auto negro, una patrulla), otra persona esperando, una puerta que se abre, una foto en la mano, un objeto escondido.
  Se tocan por la profundidad (primer plano contra fondo), una ventana o una puerta abierta, o la luz que entra.
- **Nada de reflejos mágicos**: en 12 imágenes seguidas Ollama puso "un reflejo que muestra una ciudad que no existe"
  y el usuario lo vio como algo sin sentido. Un reflejo solo puede mostrar lo que de verdad está ahí, y como mucho una
  imagen de cada cinco usa un reflejo. Nada flota en el aire, nada aparece porque sí.

## 4. Diseño de póster (lo que hace atractiva la imagen)
No importa la cantidad de detalle sino el diseño. Cada fondo es un póster:
- **Un solo punto focal** que se lee en un segundo, aunque la imagen sea chica (miniatura de YouTube).
- **Contraste de escala**: algo chico frente a algo enorme (una persona y una luna, una nave y una torre).
- **Espacio vacío** que deja respirar al foco: cielo, niebla, agua quieta, una pared de luz.
- **Silueta legible**: el contorno del protagonista o del objeto se entiende aunque esté a contraluz.
- **Paleta corta**: dos colores dominantes y un acento vivo (el acento cae sobre el objeto del plano B).
- **Clima**: hora, tiempo y temperatura emocional concretos (lluvia a la hora azul, niebla después de medianoche,
  tormenta a punto de estallar, nieve entre neones). El clima tiene que sentirse en la piel.
- **Una composición de la lista** (`visual_estilo.LAYOUTS`), distinta de la de los temas anteriores cuando se pueda.
- Nada de amontonar: si un elemento no ayuda al foco o al clima, sobra.

## 5. Qué devuelve el director creativo
- `tesis`: una frase en castellano que no nombre el lugar del título.
- `traducciones`: pares "literal -> alusivo".
- `plano_A` y `plano_B`: lugar, luz, objeto y qué significa cada uno.
- `tension`: cuál de las cuatro tensiones domina y cómo se ve (una imagen concreta).
- `motivos`: 1 a 3 objetos o gestos (distintos de los ya usados en otros temas: banco `simbolos_starlight.json`).
- `ancla_literal`: el único elemento del título que se muestra tal cual.
- `prohibido`: escenas literales a evitar.
- `protagonista`: en inglés, una persona adulta original (edad visible, ropa, peinado) haciendo una acción concreta.
- `fotograma`: en inglés, el cuadro completo donde se ven los dos planos, con luz, clima, profundidad y algo enorme en
  el cielo o en el fondo.
- `se_descubre`: el detalle que se lee recién en la segunda mirada.
- `composicion`: el número de la composición de póster elegida.
- `clima`: en inglés, hora, tiempo y emoción (por ejemplo "rain at blue hour, wet and lonely").
- `acento`: el color vivo y dónde cae.

## 6. Banco de símbolos
Cada tema registra sus motivos en `simbolos_starlight.json`. El director creativo recibe la lista y busca otros, así
ningún fondo se parece a otro.
