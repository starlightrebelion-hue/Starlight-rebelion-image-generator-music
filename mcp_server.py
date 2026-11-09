"""Servidor MCP: expone FL Studio como herramientas para Claude."""
from typing import Any

from mcp.server.mcpserver import MCPServer

import flbridge as fl

server = MCPServer("fl-studio")


@server.tool()
def fl_status() -> dict:
    """Estado de FL Studio: version, tempo, reproduccion, canales y mixer."""
    return fl.status()


@server.tool()
def fl_functions(module: str) -> list:
    """Funciones reales de un modulo: arrangement, bridge, channels, device,
    general, mixer, patterns, playlist, plugins, transport o ui."""
    return fl.call("bridge", "functions", module)


@server.tool()
def fl_call(module: str, function: str, args: list[Any] | None = None) -> Any:
    """Llama a una funcion de la API de scripting de FL, p. ej.
    mixer.setTrackVolume con args [1, 0.8], o bridge.setTempo con args [128]."""
    return fl.call(module, function, *(args or []))


@server.tool()
def fl_batch(commands: list[list[Any]]) -> list:
    """Ejecuta [[modulo, funcion, ...args], ...] en orden; se detiene en el primer error."""
    return fl.batch(commands, timeout=10.0)


@server.tool()
def fl_render(project: str, format: str = "wav") -> str:
    """Exporta un .flp guardado a wav o mp3, junto al proyecto. FL Studio debe estar cerrado."""
    return str(fl.render(project, format))


@server.tool()
def fl_list_presets() -> dict:
    """Presets de proyecto disponibles, con su descripcion."""
    return fl.list_presets()


@server.tool()
def fl_run_preset(name: str) -> int:
    """Aplica un preset de proyecto y devuelve cuantos comandos ejecuto."""
    return fl.run_preset(name)


@server.tool()
def fl_list_themes() -> list:
    """Temas visuales instalados."""
    return fl.list_themes()


@server.tool()
def fl_create_theme(name: str, base: str = "Dark", values: dict[str, Any] | None = None) -> str:
    """Crea un tema visual desde `base`. `values` usa las claves de .flstheme
    (Hue, Saturation, Lightness, Contrast, Selected, Highlight...); colores como '#RRGGBB'."""
    return str(fl.create_theme(name, base, **(values or {})))


@server.tool()
def fl_apply_theme(name: str) -> str:
    """Activa un tema para el proximo arranque. FL Studio debe estar cerrado."""
    return str(fl.apply_theme(name))


@server.tool()
def fl_reset_theme() -> None:
    """Vuelve al tema por defecto en el proximo arranque. FL Studio debe estar cerrado."""
    fl.reset_theme()


if __name__ == "__main__":
    server.run()
