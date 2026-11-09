"""Harness de evaluación: corre una generación sobre las tareas, la califica y arma su GenerationReport.

Cada episodio pasa por el verificador (la métrica oficial) y por el juez LLM (solo para calibrar: su nota
nunca decide `passed`). Las trazas se guardan en data/runs/<rama>/gen_N/seed_S.jsonl, una por línea.
"""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agents import builder
from core import almacen, progress
from core.contracts import AgentSpec, GenerationReport, Task, Trace
from env.tareas import TAREAS
from env.verificador import verificar
from evaluation import judge

WORKERS = int(os.getenv("KAIZEN_WORKERS", "8"))  # episodios en paralelo; 1 con un modelo local
HERRAMIENTA_ESCALAR = "escalar_humano"
DECIMALES = 4  # métricas en fracción de 0 a 1
DECIMALES_USD = 6  # una generación del smoke cuesta centavos: con menos decimales se vería 0


# ---------------------------------------------------------------------------
# Correr una generación
# ---------------------------------------------------------------------------
def episodio(ejecutar: builder.EjecutarAgente, spec: AgentSpec, tarea: Task, semilla: int) -> Trace:
    """Un episodio completo: el agente responde, el verificador califica y el juez opina."""
    resultado = ejecutar([{"role": "user", "content": tarea["prompt"]}])
    usadas = [paso.tool for paso in resultado.steps]
    exitosas = [paso.tool for paso in resultado.steps if paso.ok]
    veredicto = verificar(tarea, resultado.final_answer, usadas, resultado.exhausted, exitosas)
    p_pasa, explicacion, costo_juez = judge.juzgar(tarea["prompt"], resultado.steps, resultado.final_answer,
                                                   spec.rubric_version)
    veredicto.judge_p_pass, veredicto.judge_explanation = p_pasa, explicacion
    progress.tarea_hecha(tarea["id"], veredicto.passed, veredicto.reason)
    return Trace(task_id=tarea["id"], family=tarea["family"], generation=spec.generation, branch=spec.branch,
                 seed=semilla, split=tarea["split"], prompt=tarea["prompt"], expected=tarea["expected"],
                 steps=resultado.steps, final_answer=resultado.final_answer, verdict=veredicto,
                 tokens=resultado.tokens, cost_usd=resultado.cost_usd + costo_juez, exhausted=resultado.exhausted)


def run_generation(spec: AgentSpec, semilla: int, tareas: list[Task] | None = None) -> list[Trace]:
    """Corre las tareas (todas por defecto) con una semilla y guarda las trazas. BudgetExceeded se propaga."""
    tareas = tareas or TAREAS
    ejecutar = builder.build(spec, seed=semilla)
    progress.iniciar(spec.generation, spec.branch, semilla, len(tareas))
    with ThreadPoolExecutor(WORKERS) as hilos:
        trazas = list(hilos.map(lambda tarea: episodio(ejecutar, spec, tarea, semilla), tareas))
    guardar_trazas(almacen.carpeta_trazas(spec.branch, spec.generation) / f"seed_{semilla}.jsonl", trazas)
    return trazas


def guardar_trazas(archivo: Path, trazas: list[Trace]) -> None:
    """Escribe el .jsonl en un temporal y lo renombra: rescore puede reescribir un archivo que export está leyendo."""
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_name(archivo.name + ".tmp")
    lineas = (json.dumps(traza.to_dict(), ensure_ascii=False) for traza in trazas)
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.replace(temporal, archivo)


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def tasa_de_exito(trazas: list[Trace]) -> float:
    if not trazas:
        return 0.0
    return sum(t.verdict.passed for t in trazas) / len(trazas)


def precision_de_herramientas(trazas: list[Trace]) -> float:
    """Contrato: fracción de llamadas con ok == True. Sin llamadas no hubo ninguna exitosa: 0."""
    pasos = [paso for traza in trazas for paso in traza.steps]
    if not pasos:
        return 0.0
    return sum(paso.ok for paso in pasos) / len(pasos)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlación de Pearson. None con menos de 2 pares o si una serie no varía (la fórmula divide entre 0)."""
    if len(xs) < 2:
        return None
    media_x, media_y = sum(xs) / len(xs), sum(ys) / len(ys)
    covarianza = sum((x - media_x) * (y - media_y) for x, y in zip(xs, ys))
    dispersion_x = math.sqrt(sum((x - media_x) ** 2 for x in xs))
    dispersion_y = math.sqrt(sum((y - media_y) ** 2 for y in ys))
    if dispersion_x == 0 or dispersion_y == 0:
        return None
    return covarianza / (dispersion_x * dispersion_y)


def correlacion_del_juez(trazas: list[Trace]) -> float | None:
    """Pearson entre p_pasa del juez y el resultado del verificador. Las trazas sin nota del juez no cuentan."""
    juzgadas = [t for t in trazas if t.verdict.judge_p_pass is not None]
    return pearson([t.verdict.judge_p_pass for t in juzgadas], [float(t.verdict.passed) for t in juzgadas])


def media_o_none(valores: list[float | None]) -> float | None:
    presentes = [v for v in valores if v is not None]
    if not presentes:
        return None
    return sum(presentes) / len(presentes)


def heldout_del_padre(spec: AgentSpec) -> float | None:
    """Media held-out del padre entre sus semillas, la misma que usa export.py para el delta."""
    if not spec.parent:
        return None
    rama_padre, nombre_gen = spec.parent.split("/")
    generacion_padre = int(nombre_gen.removeprefix("gen_"))
    reportes = [r for r in almacen.cargar_reportes(rama_padre) if r.generation == generacion_padre]
    return media_o_none([r.heldout_success for r in reportes])


def redondear(valor: float | None) -> float | None:
    return None if valor is None else round(valor, DECIMALES)


def report(spec: AgentSpec, semilla: int, trazas: list[Trace]) -> GenerationReport:
    """Métricas de una generación con una semilla. heldout_success es la métrica que se presume."""
    heldout = tasa_de_exito([t for t in trazas if t.split == "heldout"])
    resueltas = sum(t.verdict.passed for t in trazas)
    costo = sum(t.cost_usd for t in trazas)
    padre = heldout_del_padre(spec)
    return GenerationReport(
        generation=spec.generation, branch=spec.branch, seed=semilla,
        train_success=round(tasa_de_exito([t for t in trazas if t.split == "train"]), DECIMALES),
        heldout_success=round(heldout, DECIMALES),
        avg_steps=round(sum(len(t.steps) for t in trazas) / len(trazas), DECIMALES) if trazas else 0.0,
        tool_precision=round(precision_de_herramientas(trazas), DECIMALES),
        judge_correlation=redondear(correlacion_del_juez(trazas)),
        escalations=sum(any(p.tool == HERRAMIENTA_ESCALAR for p in t.steps) for t in trazas),
        tokens=sum(t.tokens for t in trazas),
        cost_usd=round(costo, DECIMALES_USD),
        cost_per_solved=round(costo / resueltas, DECIMALES_USD) if resueltas else None,
        delta_vs_parent=round(heldout - padre, DECIMALES) if padre is not None else 0.0,
        new_artifacts=list(spec.new_artifacts),
        tone=redondear(media_o_none([t.verdict.judge_tone for t in trazas])),
    )
