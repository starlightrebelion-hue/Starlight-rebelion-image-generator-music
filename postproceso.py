"""Postproduccion de los fondos: acabado de pelicula de los 90 con ffmpeg (ver agentes/postproduccion.md).

Achica la imagen grande a 1920x1080 (conserva el detalle fino), da nitidez suave, corrige color segun la paleta,
agrega halo en las luces, un poco de aberracion cromatica, vineta y grano. Siempre igual: todos los fondos del canal
terminan con el mismo acabado.

Uso: python postproceso.py entrada.png salida.png [--paleta Noche]
"""
import argparse
import subprocess
from pathlib import Path

SIZE = (1920, 1080)
# hacia donde van las sombras y las luces de cada paleta (colorbalance: -1 a 1 por canal)
GRADES = {
    "Noche": "rs=-.015:bs=.035:rh=.02:bh=-.015",
    "Nebula": "rs=.01:bs=.04:rh=.02:bh=-.01",
    "Plasma": "rs=.015:bs=.035:rh=.015:bh=-.005",
    "Cristal": "rs=-.02:gs=.005:bs=.03:rh=.005:bh=.005",
    "Cuantico": "rs=-.025:gs=.015:bs=.02:rh=.015:bh=-.015",
    "Supernova": "rs=.01:bs=.025:rh=.03:gh=.01:bh=-.025",
}
GRAIN = 6          # intensidad del grano (ruido de ffmpeg)
# bloom: los blancos y las luces fuertes se abren en un brillo difuso, como en las peliculas de anime de los 90.
# umbral (desde que brillo empieza), fuerza de la capa cercana y de la amplia, y su tinte (r, g, b).
# difusion: toda la imagen desenfocada y sumada encima, como un filtro de difusion delante de la lente.
BLOOMS = {
    "suave": {"umbral": .75, "cerca": .22, "lejos": .0, "difusion": .0, "tinte": (1, .6, .3)},
    "medio": {"umbral": .55, "cerca": .45, "lejos": .35, "difusion": .12, "tinte": (1, .85, .7)},
    "fuerte": {"umbral": .4, "cerca": .7, "lejos": .6, "difusion": .25, "tinte": (.85, 1, .95)},  # frio y verdoso
}
# negros: curva final que devuelve profundidad a las sombras (el bloom las levanta y quedan grises)
BLACKS = {"suave": "0/0 0.06/0.02 0.5/0.49 1/1", "medio": "0/0 0.1/0.02 0.5/0.47 1/1",
          "fuerte": "0/0 0.14/0.015 0.35/0.27 0.6/0.6 1/1"}
NEGROS = "suave"  # el usuario eligio negros suaves con el bloom fuerte
BLOOM = "fuerte"  # el usuario eligio el bloom fuerte, difuso y soniador


def chain(palette=None, bloom=None, blacks=None, gamma=1.0):
    width, height = SIZE
    grade = GRADES.get(palette, GRADES["Noche"])
    glow = BLOOMS[bloom or BLOOM]
    red, green, blue = glow["tinte"]
    knee = glow["umbral"]
    return (
        # todo en RGB planar: mezclar el halo en YUV tine la imagen de rosa
        f"[0:v]format=gbrp,scale={width}:-2:flags=lanczos,crop={width}:{height},unsharp=5:5:0.5:5:5:0,"
        f"colorbalance={grade},eq=contrast=1.05:saturation=1.05:gamma={gamma},format=gbrp,split=4[base][a][b][c];"
        f"[c]gblur=sigma=28,format=gbrp[mist];"
        # dos capas de brillo de las luces altas: una cercana y otra amplia, sumadas en modo pantalla
        f"[a]curves=all='0/0 {knee}/0 1/1',gblur=sigma=14,"
        f"colorchannelmixer=rr={red}:gg={green}:bb={blue},format=gbrp[near];"
        f"[b]curves=all='0/0 {knee}/0 1/1',gblur=sigma=60,"
        f"colorchannelmixer=rr={red}:gg={green}:bb={blue},format=gbrp[far];"
        f"[base][near]blend=all_mode=screen:all_opacity={glow['cerca']}[lit];"
        f"[lit][far]blend=all_mode=screen:all_opacity={glow['lejos']}[glowed];"
        f"[glowed][mist]blend=all_mode=screen:all_opacity={glow['difusion']},"
        f"curves=all='{BLACKS[blacks or NEGROS]}',eq=contrast=1.04,"
        "rgbashift=rh=-1:bh=1,vignette=angle=PI/5:mode=forward,"
        f"noise=alls={GRAIN}:allf=u,format=rgb24"
    )


def postprocess(source, target, palette=None, bloom=None, blacks=None, gamma=1.0):
    """Guarda en `target` la imagen terminada. La fuente no se toca."""
    source, target = Path(source), Path(target)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-filter_complex", chain(palette, bloom, blacks, gamma),
                    "-frames:v", "1", str(target)], check=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entrada")
    parser.add_argument("salida")
    parser.add_argument("--paleta", choices=sorted(GRADES))
    parser.add_argument("--bloom", choices=sorted(BLOOMS), help=f"brillo de las luces (por defecto {BLOOM})")
    parser.add_argument("--negros", choices=sorted(BLACKS), help=f"profundidad de las sombras (por defecto {NEGROS})")
    args = parser.parse_args()
    print(postprocess(args.entrada, args.salida, args.paleta, args.bloom, args.negros))


if __name__ == "__main__":
    main()
