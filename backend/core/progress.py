"""progress.json: el registro en vivo de la corrida. La web lo lee cada 2 o 3 segundos.

Cada cambio reescribe el archivo completo de forma atómica y agrega la línea a data/runs/registro.log.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from core import archivos, paths

MAX_LINEAS = 200  # la web solo muestra el final; el historial completo queda en registro.log

_candado = threading.Lock()  # evals.py llama tarea_hecha() desde varios hilos
_estado: dict[str, Any] = {"corriendo": False, "error": None, "lineas": []}


def _guardar() -> None:
    archivos.escribir_json(paths.PROGRESS, _estado)


def _agregar_linea(texto: str) -> None:
    hora = datetime.now().strftime("%H:%M:%S")
    _estado["lineas"] = [*_estado["lineas"], f"{hora} {texto}"][-MAX_LINEAS:]
    with paths.REGISTRO.open("a", encoding="utf-8") as registro:
        registro.write(f"{datetime.now().isoformat(timespec='seconds')} {texto}\n")


def iniciar(generacion: int, branch: str, semilla: int, total: int) -> None:
    """Empieza la evaluación de una semilla. Conserva las líneas anteriores de la misma corrida."""
    with _candado:
        _estado.update(corriendo=True, fase="evaluando", generacion=generacion, branch=branch,
                       semilla=semilla, hechas=0, total=total, aciertos=0, exito_parcial=0.0, error=None)
        _agregar_linea(f"gen {generacion} · rama {branch} · semilla {semilla}: {total} tareas")
        _guardar()


def linea(texto: str) -> None:
    """Agrega una línea de log visible en la interfaz."""
    with _candado:
        _agregar_linea(texto)
        _guardar()


def fase(nombre: str) -> None:
    """Cambia la fase visible (evaluando, destilando, exportando…) y la anota en el log."""
    with _candado:
        _estado.update(corriendo=True, fase=nombre)
        _agregar_linea(f"fase: {nombre}")
        _guardar()


def tarea_hecha(task_id: str, passed: bool, reason: str | None = None) -> None:
    """Cuenta una tarea terminada y recalcula el éxito parcial de la semilla en curso."""
    with _candado:
        _estado["hechas"] = _estado.get("hechas", 0) + 1
        _estado["aciertos"] = _estado.get("aciertos", 0) + int(passed)
        _estado["exito_parcial"] = round(_estado["aciertos"] / _estado["hechas"], 4)
        resultado = "✓" if passed else f"✗ {reason or 'sin etiqueta'}"
        _agregar_linea(f"{task_id} {resultado} ({_estado['hechas']}/{_estado.get('total', '?')})")
        _guardar()


def terminar(error: str | None = None) -> None:
    """Cierra la corrida. Con error, el mensaje aparece en la web en vez de perderse en la consola."""
    with _candado:
        _estado.update(corriendo=False, fase="error" if error else "terminado", error=error)
        _agregar_linea(f"ERROR: {error}" if error else "corrida terminada")
        _guardar()


ESPERA_CANDADO_CANCELAR_S = 2  # la cancelación llega por señal: si el candado está tomado, no se espera para siempre


def cancelar(motivo: str) -> None:
    """Cierra la corrida desde el manejador de SIGTERM. El hilo principal pudo quedar con el candado tomado
    justo cuando llegó la señal: se espera un momento y, si no se libera, se escribe igual."""
    tomado = _candado.acquire(timeout=ESPERA_CANDADO_CANCELAR_S)
    try:
        _estado.update(corriendo=False, fase="cancelada", error=motivo)
        _agregar_linea(f"CANCELADA: {motivo}")
        _guardar()
    finally:
        if tomado:
            _candado.release()
