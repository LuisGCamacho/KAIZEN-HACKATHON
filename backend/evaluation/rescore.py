"""Recalifica las trazas guardadas con el verificador actual, sin volver a correr el agente ni gastar.

Se usa después de cambiar env/verificador.py. Califica contra el `expected` guardado en cada traza y no
contra el de env/tareas.py: las fechas de inspección dependen del día (env/tools.HOY), y recalificar otro
día con el expected nuevo cambiaría el examen que el agente realmente presentó.
"""
from __future__ import annotations

from agents import builder
from core import almacen, paths, progress
from core.contracts import REASON_ERROR_API, Task, Trace
from env.tareas import POR_ID_TAREA
from env.verificador import verificar
from evaluation import evals, history


def tarea_de_la_traza(traza: Trace) -> Task:
    """La tarea tal como se presentó. key_tools no depende de la fecha, así que se toma de env/tareas.py."""
    return {"id": traza.task_id, "family": traza.family, "split": traza.split, "prompt": traza.prompt,
            "expected": traza.expected, "key_tools": POR_ID_TAREA[traza.task_id]["key_tools"]}


def recalificar(traza: Trace) -> bool:
    """Vuelve a pasar el verificador y conserva las notas del juez. Devuelve True si el resultado cambió."""
    if traza.verdict.reason == REASON_ERROR_API:  # el agente nunca respondió: no hay nada que recalificar
        return False
    # Misma regla que evals.py: una tool generada cuenta como las tools base que usa por dentro
    usadas = builder.con_herramientas_base([paso.tool for paso in traza.steps])
    exitosas = builder.con_herramientas_base([paso.tool for paso in traza.steps if paso.ok])
    nuevo = verificar(tarea_de_la_traza(traza), traza.final_answer, usadas, traza.exhausted, exitosas)
    cambio = (nuevo.passed, nuevo.reason) != (traza.verdict.passed, traza.verdict.reason)
    traza.verdict.passed, traza.verdict.reason = nuevo.passed, nuevo.reason
    return cambio


def ramas_propias() -> list[str]:
    """Ramas con trazas propias. Control no se recorre por lo heredado de main: eso se recalifica en main."""
    if not paths.RUNS.exists():
        return []
    return sorted(p.name for p in paths.RUNS.iterdir() if p.is_dir() and any(p.glob("gen_*/seed_*.jsonl")))


def main(trato: bool = False) -> None:
    if trato:
        raise NotImplementedError("--trato necesita evaluation/trato.py, que todavía no existe")
    progress.fase("recalificando")
    for rama in ramas_propias():
        for generacion in almacen.generaciones(rama):
            if almacen.rama_real(rama, generacion) != rama:
                continue
            spec = almacen.cargar_spec(rama, generacion)
            if spec is None:  # trazas huérfanas: sin spec no se puede rearmar el reporte
                progress.linea(f"rescore {rama}/gen_{generacion}: sin spec, se omite")
                continue
            reportes = []
            for semilla in almacen.semillas(rama, generacion):
                trazas = almacen.cargar_trazas(rama, generacion, semilla)
                cambios = sum(recalificar(t) for t in trazas)
                evals.guardar_trazas(almacen.carpeta_trazas(rama, generacion) / f"seed_{semilla}.jsonl", trazas)
                reportes.append(evals.report(spec, semilla, trazas))
                progress.linea(f"rescore {rama}/gen_{generacion} semilla {semilla}: {cambios} cambiaron")
            history.save_reports(rama, reportes)
