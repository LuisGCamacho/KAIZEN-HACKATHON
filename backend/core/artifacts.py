"""Registro de todo lo que produce el sistema, aceptado o rechazado (data/meta/artifacts.json).

La vista Herramientas lo muestra como evidencia de autoría de la máquina. Dueño: Backend B.
Las funciones `add` y `all_artifacts` conservan nombres en inglés porque las llaman varias áreas."""
from __future__ import annotations

import dataclasses
import threading

from core import archivos
from core.contracts import Artifact
from core.paths import META

REGISTRO = META / "artifacts.json"
_candado = threading.Lock()  # la síntesis de tools y el destilador pueden registrar desde hilos distintos
CAMPOS_ARTIFACT = {campo.name for campo in dataclasses.fields(Artifact)}


def all_artifacts() -> list[dict]:
    """Todos los artefactos registrados, en orden de creación; lista vacía si aún no hay ninguno."""
    return archivos.leer_json(REGISTRO, [])


def _clave(artefacto: dict) -> tuple:
    """Identidad de un artefacto: rehacer una generación lo reemplaza en lugar de duplicarlo."""
    return artefacto["generation"], artefacto["branch"], artefacto["name"]


def add(artefacto: dict) -> dict:
    """Registra un artefacto (formato Artifact de core/contracts.py, más content/code/tests opcionales).

    Si ya existe uno con la misma generación, rama y nombre, lo reemplaza. Devuelve el artefacto recibido."""
    with _candado:
        artefactos = [existente for existente in all_artifacts() if _clave(existente) != _clave(artefacto)]
        artefactos.append(artefacto)
        # Escritura atómica: export.py puede leerlo en cualquier momento
        archivos.escribir_json(REGISTRO, artefactos)
    return artefacto


def listar() -> list[Artifact]:
    """Los artefactos como Artifact. Los campos extra (content, code, tests) se quedan en all_artifacts()."""
    return [Artifact(**{k: v for k, v in a.items() if k in CAMPOS_ARTIFACT}) for a in all_artifacts()]


def conservar_hasta(generacion: int) -> list[dict]:
    """Deja solo los artefactos de generaciones <= generacion y devuelve los que quitó (para reset)."""
    with _candado:
        todos = all_artifacts()
        archivos.escribir_json(REGISTRO, [a for a in todos if a["generation"] <= generacion])
    return [a for a in todos if a["generation"] > generacion]
