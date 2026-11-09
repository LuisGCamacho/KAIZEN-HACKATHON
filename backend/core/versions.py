"""Versionado de lo que reescribe el meta-loop: rubrica_vN.md y distiller_prompt_vN.md.

Cada versión es un archivo en data/meta/ más una entrada en <tipo>_history.json con quién, cuándo y por qué.
La v0 de cada tipo se escribe a mano y no lleva entrada en el historial.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from core import archivos, paths

Tipo = Literal["rubrica", "distiller_prompt"]
TIPOS: tuple[Tipo, ...] = ("rubrica", "distiller_prompt")


def ruta(tipo: Tipo, version: int) -> Path:
    return paths.META / f"{tipo}_v{version}.md"


def _archivo_historial(tipo: Tipo) -> Path:
    return paths.META / f"{tipo}_history.json"


def historial(tipo: Tipo) -> list[dict[str, Any]]:
    return archivos.leer_json(_archivo_historial(tipo), [])


def versiones(tipo: Tipo) -> list[int]:
    """Versiones con archivo en disco, de menor a mayor."""
    patron = re.compile(rf"^{tipo}_v(\d+)\.md$")
    if not paths.META.exists():
        return []
    return sorted(int(m.group(1)) for p in paths.META.iterdir() if (m := patron.match(p.name)))


def ultima(tipo: Tipo) -> int:
    """Versión más reciente; 0 si solo existe la escrita a mano (o ninguna)."""
    return max(versiones(tipo), default=0)


def texto(tipo: Tipo, version: int) -> str:
    """Contenido de la versión, o "" si el archivo no existe."""
    archivo = ruta(tipo, version)
    return archivo.read_text(encoding="utf-8") if archivo.exists() else ""


def guardar(tipo: Tipo, contenido: str, generation: int, branch: str, **detalle: Any) -> int:
    """Escribe la siguiente versión y la anota en el historial. Devuelve el número de versión.

    detalle admite los campos de MetaVersion en web/lib/types.ts: deltas, diagnosis, change, correlation_before.
    """
    version = ultima(tipo) + 1
    ruta(tipo, version).write_text(contenido, encoding="utf-8")
    entrada = {"version": version, "generation": generation, "branch": branch, **detalle}
    archivos.escribir_json(_archivo_historial(tipo), [*historial(tipo), entrada])
    return version


def conservar_hasta_v0() -> list[Path]:
    """Borra las versiones >= 1 y vacía el historial (para reset). Devuelve los archivos borrados."""
    borrados = []
    for tipo in TIPOS:
        for version in versiones(tipo):
            if version >= 1:
                ruta(tipo, version).unlink()
                borrados.append(ruta(tipo, version))
        if _archivo_historial(tipo).exists():
            archivos.escribir_json(_archivo_historial(tipo), [])
    return borrados
