"""Servidor MCP: busca, lee y crea presets de Arturia Pigments desde sus archivos."""
from mcp.server.mcpserver import MCPServer

import pigments as pg

server = MCPServer("pigments")


def _row(preset):
    return {"nombre": preset.name, "banco": preset.bank, "autor": preset.author, "tipo": preset.kind,
            "etiquetas": list(preset.tags)}


@server.tool()
def pigments_buscar(texto: str = "", tipo: str = "", etiqueta: str = "", limite: int = 40) -> list:
    """Busca presets por nombre, tipo (Pad, Bass, Keys, Sequence, Lead, Strings...) y
    etiqueta (Ambient, Evolving, Airy, Cinematic, Synthwave...)."""
    return [_row(preset) for preset in pg.find(texto, tipo, etiqueta, limite)]


@server.tool()
def pigments_leer(nombre: str, contiene: str = "") -> dict:
    """Parametros de un preset con su nombre legible. Sin `contiene` da un resumen (motores,
    envolvente, filtros, efectos, macros); con `contiene` filtra, p. ej. 'Env1' o 'FX3_Reverb'.
    Casi todos los valores van de 0 a 1."""
    return pg.describe(nombre, contiene)


@server.tool()
def pigments_opciones(clase: str) -> list:
    """Opciones de motor, filtro o efecto. `clase`: Engine, Filter o FX."""
    return pg.options(clase)


@server.tool()
def pigments_crear(base: str, nombre: str, cambios: dict[str, float] | None = None,
                   tipos: dict[str, str] | None = None) -> str:
    """Crea un preset copiando `base` y cambiando valores. `cambios`: {parametro: valor de 0 a 1}.
    `tipos`: {parametro_ModuleType: nombre}, p. ej. {'FX3_ModuleType': 'Shimmer'}.
    Lo guarda en presets/pigments del proyecto y devuelve la ruta."""
    version = pg.locate(base).version
    values = dict(cambios or {})
    for key, name in (tipos or {}).items():
        values[key] = pg.choice_value(key.split("_")[0].rstrip("0123456789"), name, version)
    return str(pg.derive(base, nombre, values))


if __name__ == "__main__":
    server.run()
