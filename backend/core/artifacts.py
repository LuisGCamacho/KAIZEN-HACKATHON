"""Registro de todo lo que produce el sistema, aceptado o rechazado (data/meta/artifacts.json).

La vista Herramientas lo muestra como evidencia de autoría de la máquina. Dueño: Backend B.
Las funciones `add` y `all_artifacts` conservan nombres en inglés porque las llaman varias áreas."""
from __future__ import annotations

import json
import threading

from core.paths import META

REGISTRO = META / "artifacts.json"
_candado = threading.Lock()  # la síntesis de tools y el destilador pueden registrar desde hilos distintos


def all_artifacts() -> list[dict]:
    """Todos los artefactos registrados, en orden de creación; lista vacía si aún no hay ninguno."""
    if not REGISTRO.exists():
        return []
    return json.loads(REGISTRO.read_text(encoding="utf-8"))


def _clave(artefacto: dict) -> tuple:
    """Identidad de un artefacto: rehacer una generación lo reemplaza en lugar de duplicarlo."""
    return artefacto["generation"], artefacto["branch"], artefacto["name"]


def add(artefacto: dict) -> dict:
    """Registra un artefacto (formato Artifact de core/contracts.py, más content/code/tests opcionales).

    Si ya existe uno con la misma generación, rama y nombre, lo reemplaza. Devuelve el artefacto recibido."""
    with _candado:
        artefactos = [existente for existente in all_artifacts() if _clave(existente) != _clave(artefacto)]
        artefactos.append(artefacto)
        temporal = REGISTRO.with_suffix(".json.tmp")  # escritura atómica: export.py puede leerlo en cualquier momento
        temporal.write_text(json.dumps(artefactos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(REGISTRO)
    return artefacto
