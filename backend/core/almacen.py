"""Lectura y escritura de specs, trazas y reportes en data/. La usan run.py, export.py y reset.py.

La rama control no copia datos de main: hasta su generación de fork, lee los de main.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core import archivos, paths
from core.contracts import AgentSpec, GenerationReport, Trace

CONTROL = "control"
RAMA_PRINCIPAL = "main"
FORK_POR_DEFECTO = 2  # docs: control nace de main/gen_2 salvo que run.py reciba otro --fork-from

PATRON_SPEC = re.compile(r"^gen_(\d+)\.json$")
PATRON_SEMILLA = re.compile(r"^seed_(\d+)\.jsonl$")


# ---------- rama control ----------

def _archivo_fork() -> Path:
    return paths.RUNS / CONTROL / "fork.json"


def fork_de_control() -> int:
    return archivos.leer_json(_archivo_fork(), {"fork_from": FORK_POR_DEFECTO})["fork_from"]


def fijar_fork(generacion: int) -> None:
    archivos.escribir_json(_archivo_fork(), {"fork_from": generacion})


def rama_real(branch: str, generacion: int) -> str:
    """Rama donde viven los datos de esa generación: control hereda de main hasta el fork."""
    if branch == CONTROL and generacion <= fork_de_control():
        return RAMA_PRINCIPAL
    return branch


# ---------- specs ----------

def ruta_spec(branch: str, generacion: int) -> Path:
    return paths.SPECS / branch / f"gen_{generacion}.json"


def guardar_spec(spec: AgentSpec) -> None:
    archivos.escribir_json(ruta_spec(spec.branch, spec.generation), spec.to_dict())


def cargar_spec(branch: str, generacion: int) -> AgentSpec | None:
    datos = archivos.leer_json(ruta_spec(rama_real(branch, generacion), generacion), None)
    return AgentSpec.from_dict(datos) if datos else None


def generaciones(branch: str) -> list[int]:
    """Generaciones con spec en la rama, incluidas las heredadas de main si es control."""
    propias = _numeros(paths.SPECS / branch, PATRON_SPEC)
    if branch != CONTROL:
        return propias
    heredadas = [g for g in _numeros(paths.SPECS / RAMA_PRINCIPAL, PATRON_SPEC) if g <= fork_de_control()]
    return sorted(set(heredadas) | {g for g in propias if g > fork_de_control()})


def _numeros(carpeta: Path, patron: re.Pattern) -> list[int]:
    if not carpeta.exists():
        return []
    return sorted(int(m.group(1)) for p in carpeta.iterdir() if (m := patron.match(p.name)))


# ---------- trazas ----------

def carpeta_trazas(branch: str, generacion: int) -> Path:
    return paths.RUNS / rama_real(branch, generacion) / f"gen_{generacion}"


def semillas(branch: str, generacion: int) -> list[int]:
    return _numeros(carpeta_trazas(branch, generacion), PATRON_SEMILLA)


def cargar_trazas(branch: str, generacion: int, semilla: int | None = None) -> list[Trace]:
    """Trazas de una generación: de una semilla o de todas."""
    elegidas = [semilla] if semilla is not None else semillas(branch, generacion)
    trazas: list[Trace] = []
    for s in elegidas:
        archivo = carpeta_trazas(branch, generacion) / f"seed_{s}.jsonl"
        if not archivo.exists():
            continue
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                trazas.append(Trace.from_dict(json.loads(linea)))
    return trazas


# ---------- reportes ----------

def ruta_reportes(branch: str) -> Path:
    return paths.RUNS / branch / "reports.json"


def cargar_reportes(branch: str) -> list[GenerationReport]:
    """Reportes de la rama. Control incluye los de main hasta el fork."""
    propios = [GenerationReport(**r) for r in archivos.leer_json(ruta_reportes(branch), [])]
    if branch != CONTROL:
        return propios
    fork = fork_de_control()
    heredados = [r for r in cargar_reportes(RAMA_PRINCIPAL) if r.generation <= fork]
    return heredados + [r for r in propios if r.generation > fork]


def ramas_con_datos() -> list[str]:
    """Ramas con al menos un reporte, con main primero."""
    if not paths.RUNS.exists():
        return []
    ramas = sorted(p.name for p in paths.RUNS.iterdir() if (p / "reports.json").exists())
    return sorted(ramas, key=lambda r: r != RAMA_PRINCIPAL)
