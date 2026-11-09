"""Libros de Doble Fondo para StoryForge, en modo lectura.

Carga `C:\\canal starlight rebelion\\scripts\\libros.py` desde su archivo (solo libreria estandar) y usa el indice que
ya armo el Estudio de Doble Fondo: fichas por libro (canal/libros/fichas), estilos de guionista por genero
(canal/libros/estilos.json) y los fragmentos para buscar pasajes (output/libros/fragmentos.jsonl). No escribe nada
en Doble Fondo: indexar o destilar fichas nuevas se sigue haciendo desde su Estudio.
"""
import importlib.util
from pathlib import Path

import proyecto_sf

SOURCE = Path(r"C:\canal starlight rebelion\scripts\libros.py")
_MODULE = {}
# que rol de libros.py recibe cada paso del guion (los de guion reciben pasajes; el resto, solo fichas)
ROLE_OF = {"premisa": "concepto", "secuencias": "guionista", "escenas": "guionista", "planos": "director",
           "estructura": "guionista"}


def module():
    if "m" not in _MODULE:
        if not SOURCE.is_file():
            raise FileNotFoundError(f"No esta {SOURCE}")
        spec = importlib.util.spec_from_file_location("libros_doble_fondo", SOURCE)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        _MODULE["m"] = loaded
    return _MODULE["m"]


def available():
    try:
        module()
        return True
    except (OSError, ImportError, SyntaxError):
        return False


def overview():
    """Estilos de guionista, catalogo con fichas y el estilo elegido por el proyecto."""
    books = module()
    styles = books.estilos()
    catalog = books.catalogo()
    items = []
    for key, entry in (catalog.get("libros") or catalog).items() if isinstance(catalog, dict) else []:
        if not isinstance(entry, dict):
            continue
        sheet = books.ficha(key) or {}
        items.append({"clave": key, "titulo": entry.get("titulo") or key, "autor": entry.get("autor", ""),
                      "tipo": entry.get("tipo", ""), "ficha": {k: sheet.get(k) for k in
                                                               ("tono", "atmosfera", "ritmo", "personajes", "dialogo",
                                                                "principios", "resumen") if sheet.get(k)}})
    return {"estilos": styles.get("estilos", {}), "por_defecto": styles.get("por_defecto"),
            "elegido": proyecto_sf.config().get("estilo_guion"), "libros": items}


def search(query, style=None, k=6):
    books = module()
    chosen = books.estilo(style) if style else None
    titles = (chosen or {}).get("ficcion", []) + (chosen or {}).get("oficio", []) if chosen else None
    results = books.buscar(query, titles or None, k=k)
    return [{key: item.get(key) for key in ("libro", "titulo", "texto", "puntaje") if key in item}
            if isinstance(item, dict) else {"texto": str(item)} for item in results]


def contexto_para(kind, query=""):
    """Bloque de tono para el agente de ese paso ("" si no hay estilo elegido o no estan los libros)."""
    style = proyecto_sf.config().get("estilo_guion")
    if not style or not available():
        return ""
    project = proyecto_sf.read_project()
    query = query or f"{project.get('idea', '')} {(project.get('premisa') or {}).get('logline', '')}"
    return module().contexto(style, query, ROLE_OF.get(kind, "guionista"), max_chars=1800)
