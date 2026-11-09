"""Registro de artefactos (playbooks y tools) en data/meta/artifacts.json, sin duplicados."""
from __future__ import annotations

from pathlib import Path

from core import archivos, paths
from core.contracts import Artifact


def _archivo() -> Path:
    return paths.META / "artifacts.json"


def listar() -> list[Artifact]:
    return [Artifact(**a) for a in archivos.leer_json(_archivo(), [])]


def registrar(artefacto: Artifact) -> None:
    """Agrega o reemplaza: la clave es (generación, rama, nombre), así repetir una generación no duplica."""
    clave = (artefacto.generation, artefacto.branch, artefacto.name)
    otros = [a for a in listar() if (a.generation, a.branch, a.name) != clave]
    archivos.escribir_json(_archivo(), [a.to_dict() for a in [*otros, artefacto]])


def conservar_hasta(generacion: int) -> list[Artifact]:
    """Deja solo los artefactos de generaciones <= generacion y devuelve los que quitó (para reset)."""
    todos = listar()
    quedan = [a for a in todos if a.generation <= generacion]
    archivos.escribir_json(_archivo(), [a.to_dict() for a in quedan])
    return [a for a in todos if a.generation > generacion]
