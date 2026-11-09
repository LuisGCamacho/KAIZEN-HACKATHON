"""Escribe por stdout el Excel de Evolución de una rama. Lo lanza la ruta /api/excel de la web.

    python exportar_excel.py --branch main > kaizen-main-generaciones.xlsx

Códigos de salida: 0 ok, 1 error (el motivo va por stderr).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation import excel, export  # noqa: E402

RAMAS = ("main", "smoke", "control")  # misma allowlist que la ruta: nunca llega texto libre del cliente


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Excel de Evolución de KAIZEN")
    parser.add_argument("--branch", choices=RAMAS, default="main")
    args = parser.parse_args(argv)
    try:
        contenido = excel.construir(export.filas_de_rama(args.branch), args.branch)
    except ValueError as e:  # rama sin generaciones: es un caso esperado, no un fallo del código
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.buffer.write(contenido)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
