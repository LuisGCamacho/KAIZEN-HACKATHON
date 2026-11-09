"""Historial de reportes por rama: data/runs/<rama>/reports.json, una entrada por generación y semilla.

Solo escribe. Las lecturas (con la herencia de control desde main), las medias entre semillas, los deltas
y la mejor generación ya viven en core/almacen.py y evaluation/export.py.
"""
from __future__ import annotations

from core import almacen, archivos
from core.contracts import GenerationReport


def save_reports(branch: str, reportes: list[GenerationReport]) -> None:
    """Agrega los reportes a la rama. Si ya había uno de la misma generación y semilla, lo reemplaza
    (por ejemplo, tras un rescore o al repetir una generación)."""
    ruta = almacen.ruta_reportes(branch)
    # Se lee el archivo de la rama tal cual: cargar_reportes() de control mezclaría los heredados de main
    guardados = archivos.leer_json(ruta, [])
    nuevos = {(r.generation, r.seed) for r in reportes}
    conservados = [r for r in guardados if (r["generation"], r["seed"]) not in nuevos]
    todos = conservados + [r.to_dict() for r in reportes]
    todos.sort(key=lambda r: (r["generation"], r["seed"]))
    archivos.escribir_json(ruta, todos)
