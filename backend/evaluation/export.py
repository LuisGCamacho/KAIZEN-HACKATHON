"""Escribe los JSON de web/public/data/ a partir de data/. Las formas están en web/lib/types.ts.

export_all() se puede llamar en cualquier momento: si una sección falla, conserva su archivo anterior
y sigue con las demás, porque una corrida de media hora no debe caerse por un error de la interfaz.
"""
from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from core import almacen, archivos, artifacts, paths, versions
from core.contracts import AgentSpec, GenerationReport, Trace

MAX_COMPARACIONES = 30  # traces.json: tamaño razonable para la vista Trazas
SEMILLA_COMPARACION = 1
PRECISION = 4  # decimales en medias y desviaciones


# ---------- utilidades ----------

def _leer(ruta_relativa: str) -> str:
    """Texto de un archivo bajo data/, o "" si no existe (la interfaz muestra "—")."""
    archivo = paths.DATA / ruta_relativa
    return archivo.read_text(encoding="utf-8") if ruta_relativa and archivo.exists() else ""


def _media(valores: list[float]) -> float:
    return round(statistics.fmean(valores), PRECISION) if valores else 0.0


def _desviacion(valores: list[float]) -> float:
    return round(statistics.stdev(valores), PRECISION) if len(valores) > 1 else 0.0


def _media_opcional(valores: list[float | None]) -> float | None:
    """Media de los valores presentes; None si no hay ninguno (no se inventa la nota)."""
    presentes = [v for v in valores if v is not None]
    return _media(presentes) if presentes else None


def mejor_generacion(filas: list[dict[str, Any]]) -> int | None:
    """Mayor held-out y, en empate, la más nueva. Misma regla que bestOf() en la web."""
    if not filas:
        return None
    return max(filas, key=lambda f: (f["heldout_mean"], f["generation"]))["generation"]


# ---------- reports.json ----------

def _fila(branch: str, generacion: int, reportes: list[GenerationReport],
          padre: dict[str, Any] | None) -> dict[str, Any]:
    """Una fila de Generation: media y desviación entre semillas, más datos de la spec."""
    spec = almacen.cargar_spec(branch, generacion)
    spec_padre = almacen.cargar_spec(branch, generacion - 1) if generacion > 0 else None
    heldout = [r.heldout_success for r in reportes]
    return {
        "branch": branch,
        "generation": generacion,
        "seeds": len(reportes),
        "heldout_mean": _media(heldout),
        "heldout_std": _desviacion(heldout),
        "train_mean": _media([r.train_success for r in reportes]),
        "train_std": _desviacion([r.train_success for r in reportes]),
        "avg_steps": _media([r.avg_steps for r in reportes]),
        "tool_precision": _media([r.tool_precision for r in reportes]),
        "judge_correlation": _media_opcional([r.judge_correlation for r in reportes]),
        "escalations": sum(r.escalations for r in reportes),
        "cost_usd": round(sum(r.cost_usd for r in reportes), PRECISION),
        "cost_per_solved": _media_opcional([r.cost_per_solved for r in reportes]),
        "tone": _media_opcional([r.tone for r in reportes]),
        "delta": round(_media(heldout) - padre["heldout_mean"], PRECISION) if padre else 0.0,
        "topology": spec.topology if spec else "single_react",
        "topology_changed": bool(spec and spec_padre and spec.topology != spec_padre.topology),
        "distiller_prompt_version": spec.distiller_prompt_version if spec else 0,
        "rubric_version": spec.rubric_version if spec else 0,
        "meta_rewrite": bool(spec and spec_padre and (
            spec.distiller_prompt_version != spec_padre.distiller_prompt_version
            or spec.rubric_version != spec_padre.rubric_version)),
        "new_artifacts": spec.new_artifacts if spec else [],
        "note": "; ".join(r.note for r in reportes if r.note),
    }


def filas_de_rama(branch: str) -> list[dict[str, Any]]:
    reportes = almacen.cargar_reportes(branch)
    por_generacion: dict[int, list[GenerationReport]] = {}
    for r in reportes:
        por_generacion.setdefault(r.generation, []).append(r)
    filas: list[dict[str, Any]] = []
    for generacion in sorted(por_generacion):
        padre = filas[-1] if filas else None
        filas.append(_fila(branch, generacion, por_generacion[generacion], padre))
    return filas


def reports() -> dict[str, Any]:
    ramas = almacen.ramas_con_datos()
    return {
        "branches": ramas,
        "generations": [fila for rama in ramas for fila in filas_de_rama(rama)],
        "seeds": [r.to_dict() for rama in ramas for r in almacen.cargar_reportes(rama)],
        "spend_usd": round(archivos.leer_json(paths.SPEND, {"usd": 0.0})["usd"], PRECISION),
    }


# ---------- clusters.json ----------

def clusters() -> list[dict[str, Any]]:
    """Fallos por causa y generación (media entre semillas, todos los splits) para la vista Autopsia."""
    registro = artifacts.listar()
    resultado = []
    for rama in almacen.ramas_con_datos():
        gens = almacen.generaciones(rama)
        conteos: dict[int, Counter] = {}
        for g in gens:
            n_semillas = max(len(almacen.semillas(rama, g)), 1)
            fallos = Counter(t.verdict.reason for t in almacen.cargar_trazas(rama, g) if not t.verdict.passed)
            conteos[g] = Counter({razon: n / n_semillas for razon, n in fallos.items()})
        razones = sorted({r for c in conteos.values() for r in c if r})
        for razon in razones:
            por_gen = [round(conteos[g].get(razon, 0.0), 2) for g in gens]
            cierre = next((a.name for a in sorted(registro, key=lambda a: a.generation)
                           if a.branch == rama and a.origin == razon and a.accepted), None)
            resultado.append({"branch": rama, "reason": razon, "per_generation": por_gen,
                              "generations": gens, "closed_by": cierre,
                              "open": bool(por_gen and por_gen[-1] > 0)})
    return resultado


# ---------- artifacts.json ----------

def _ruta_tests(ruta_codigo: str) -> str:
    codigo = Path(ruta_codigo)
    return (codigo.parent / f"test_{codigo.name}").as_posix()


def artifacts_con_contenido() -> list[dict[str, Any]]:
    """Artefactos con su texto (playbook) o su código y tests (tool) para la vista Herramientas."""
    resultado = []
    for a in artifacts.listar():
        fila = a.to_dict()
        if a.kind == "playbook":
            fila["content"] = _leer(a.path)
        else:
            fila["code"] = _leer(a.path)
            fila["tests"] = _leer(_ruta_tests(a.path))
        resultado.append(fila)
    return resultado


# ---------- lineage.json ----------

def _agentes(spec: AgentSpec) -> list[dict[str, Any]]:
    if spec.topology != "supervisor":
        return [{"name": f"gen_{spec.generation}", "role": "agente", "tools": spec.tools_enabled}]
    # Las tools de cada sub-agente las reparte builder.py; aquí solo se conocen sus nombres
    return [{"name": "supervisor", "role": "supervisor", "tools": [f"delegar_{s}" for s in spec.sub_agents]},
            *({"name": s, "role": "sub-agente", "tools": []} for s in spec.sub_agents)]


def _generacion_de_linaje(branch: str, generacion: int) -> dict[str, Any] | None:
    spec = almacen.cargar_spec(branch, generacion)
    if spec is None:
        return None
    padre = almacen.cargar_spec(branch, generacion - 1) if generacion > 0 else None
    return {
        **spec.to_dict(),
        "parent_topology": padre.topology if padre else None,
        "agents": _agentes(spec),
        "failures_total": sum(spec.clusters.values()),
        "prompt": _leer(spec.system_prompt_path),
        "parent_prompt": _leer(padre.system_prompt_path) if padre else "",
        "playbook_texts": {pb: _leer(pb) for pb in spec.playbooks},
    }


def _meta_versiones(tipo: versions.Tipo) -> list[dict[str, Any]]:
    filas = [{"version": 0, "text": versions.texto(tipo, 0), "parent_text": ""}]
    for entrada in versions.historial(tipo):
        v = entrada["version"]
        filas.append({**entrada, "text": versions.texto(tipo, v), "parent_text": versions.texto(tipo, v - 1)})
    return filas


def lineage() -> dict[str, Any]:
    ramas: dict[str, list[dict[str, Any]]] = {}
    for rama in almacen.ramas_con_datos():
        filas = [_generacion_de_linaje(rama, g) for g in almacen.generaciones(rama)]
        ramas[rama] = [f for f in filas if f]
    return {"branches": ramas, "distiller_prompt": _meta_versiones("distiller_prompt"),
            "rubric": _meta_versiones("rubrica")}


# ---------- traces.json ----------

def _rama_para_trazas() -> str:
    """main si ya tiene datos; si no, smoke (igual que el selector de la web)."""
    ramas = almacen.ramas_con_datos()
    return almacen.RAMA_PRINCIPAL if almacen.RAMA_PRINCIPAL in ramas or not ramas else ramas[0]


def comparisons() -> dict[str, Any]:
    """Gen 0 contra la última generación, semilla 1. Primero las tareas cuyo resultado cambió."""
    rama = _rama_para_trazas()
    gens = almacen.generaciones(rama)
    ultima = gens[-1] if len(gens) > 1 else None
    if ultima is None:
        return {"branch": rama, "before": 0, "after": None, "items": []}
    antes = {t.task_id: t for t in almacen.cargar_trazas(rama, 0, SEMILLA_COMPARACION)}
    despues = {t.task_id: t for t in almacen.cargar_trazas(rama, ultima, SEMILLA_COMPARACION)}
    comunes = [tid for tid in antes if tid in despues]
    comunes.sort(key=lambda tid: antes[tid].verdict.passed == despues[tid].verdict.passed)
    items = [_comparacion(antes[tid], despues[tid]) for tid in comunes[:MAX_COMPARACIONES]]
    return {"branch": rama, "before": 0, "after": ultima, "items": items}


def _comparacion(antes: Trace, despues: Trace) -> dict[str, Any]:
    return {"task_id": antes.task_id, "family": antes.family, "split": antes.split, "prompt": antes.prompt,
            "expected": antes.expected, "before": antes.to_dict(), "after": despues.to_dict()}


# ---------- progress.json ----------

def progress_inicial() -> None:
    """Crea progress.json vacío si no existe. No lo pisa: core/progress.py es su dueño."""
    if not paths.PROGRESS.exists():
        archivos.escribir_json(paths.PROGRESS, {"corriendo": False, "error": None, "lineas": []})


# ---------- todo junto ----------

SECCIONES: dict[str, Callable[[], Any]] = {
    "reports.json": reports,
    "clusters.json": clusters,
    "artifacts.json": artifacts_con_contenido,
    "lineage.json": lineage,
    "traces.json": comparisons,
}


def export_all(log: Callable[[str], None] = print) -> list[str]:
    """Escribe los 6 JSON. Devuelve los errores; los archivos que fallaron conservan su versión anterior."""
    errores = []
    for nombre, construir in SECCIONES.items():
        try:
            archivos.escribir_json(paths.WEB_DATA / nombre, construir())
        except Exception as e:  # frontera: un error en una vista no debe tumbar la corrida
            errores.append(f"{nombre}: {type(e).__name__}: {e}")
            log(f"export: falló {nombre}: {type(e).__name__}: {e}")
    progress_inicial()
    return errores
