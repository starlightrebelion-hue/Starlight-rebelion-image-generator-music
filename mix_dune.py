"""Mezcla de Ruta Neon Dune por el tunel: con el proyecto abierto en FL, ajusta y guarda."""
import sys

import build_dune
import mix_epico as mix

# Canales de Dune: mas bajo y menos pad que con Harmless
mix.FADERS = ((1, .62), (2, .55), (3, .6), (4, .65), (5, .9), (6, .42), (7, .45), (8, .58), (9, .4), (10, .5), (11, .6))
mix.MASTER_EQ = ((1, mix.PEAKING, 250, -4), (3, mix.PEAKING, 700, 1), (4, mix.PEAKING, 2000, 1),
                 (6, mix.HIGH_SHELF, 5000, 3))

if __name__ == "__main__":
    mix.main(sys.argv[1], build_dune.NOT_USED)
