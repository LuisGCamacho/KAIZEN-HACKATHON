"""Reset a gen 0: borra todo lo que produjeron las generaciones >= 1 en todas las ramas.

Se conserva lo escrito a mano (prompts/gen_0.md, estilo.md, las v0 del meta-loop), la gen 0 evaluada
y las conversaciones de la demo (runs/live/).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core import almacen, archivos, artifacts, paths, versions

PATRON_GEN_CARPETA = re.compile(r"^gen_(\d+)$")
PATRON_GEN_PROMPT = re.compile(r"^gen_(\d+)\b")  # gen_3.md, gen_3_control.md
PATRON_GEN_PLAYBOOK = re.compile(r"_g(\d+)(_[a-z0-9_-]+)?\.md$")  # <reason>_g3[_rama].md


def _gen_mayor_que_cero(patron: re.Pattern, nombre: str) -> bool:
    m = patron.search(nombre)
    return bool(m) and int(m.group(1)) >= 1


def _archivos_de_tool(ruta_codigo: Path) -> list[Path]:
    """Código, tests y esquema de una tool sintetizada."""
    return [ruta_codigo, ruta_codigo.with_name(f"test_{ruta_codigo.name}"), ruta_codigo.with_suffix(".json")]


def plan() -> list[Path]:
    """Lista lo que se borraría, sin tocar nada. reports.json se edita aparte (se quitan gens >= 1)."""
    borrar: list[Path] = []
    for carpeta_rama in _subcarpetas(paths.SPECS) + _subcarpetas(paths.RUNS):
        if carpeta_rama.name == almacen.CONTROL:
            borrar.append(carpeta_rama)  # control existe solo desde su fork, que es >= 1
            continue
        borrar += [p for p in carpeta_rama.iterdir()
                   if _gen_mayor_que_cero(PATRON_GEN_CARPETA, p.stem) and p.name != "live"]
    borrar += [p for p in _archivos(paths.PROMPTS) if _gen_mayor_que_cero(PATRON_GEN_PROMPT, p.name)]
    borrar += [p for p in _archivos(paths.PLAYBOOKS) if _gen_mayor_que_cero(PATRON_GEN_PLAYBOOK, p.name)]
    for a in artifacts.listar():
        if a.generation >= 1 and a.kind == "tool":
            borrar += [p for p in _archivos_de_tool(paths.DATA / a.path) if p.exists()]
    for tipo in versions.TIPOS:
        borrar += [versions.ruta(tipo, v) for v in versions.versiones(tipo) if v >= 1]
    return sorted(set(borrar))


def aplicar() -> list[Path]:
    """Ejecuta el reset y devuelve lo que borró. run.py lo llama con el lock tomado."""
    borrados = plan()
    for ruta in borrados:
        if ruta.is_dir():
            shutil.rmtree(ruta)
        elif ruta.exists():
            ruta.unlink()
    for carpeta_rama in _subcarpetas(paths.RUNS):
        reportes = almacen.ruta_reportes(carpeta_rama.name)
        if reportes.exists():
            archivos.escribir_json(reportes, [r for r in archivos.leer_json(reportes, []) if r["generation"] == 0])
    artifacts.conservar_hasta(0)
    versions.conservar_hasta_v0()
    return borrados


def _subcarpetas(carpeta: Path) -> list[Path]:
    return [p for p in carpeta.iterdir() if p.is_dir() and p.name != "live"] if carpeta.exists() else []


def _archivos(carpeta: Path) -> list[Path]:
    return [p for p in carpeta.iterdir() if p.is_file()] if carpeta.exists() else []
