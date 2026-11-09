"""Tests del harness (evals), el historial y el rescore. El agente y el juez son falsos: no llaman al LLM."""
from __future__ import annotations

import httpx2 as httpx  # openai 3.x usa httpx2
import openai
import pytest

from agents.agent import ResultadoAgente
from core import almacen, archivos, llm, proveedor_codex
from core.contracts import REASON_ERROR_API, AgentSpec, GenerationReport, Step
from env.tareas import POR_ID_TAREA
from evaluation import evals, history, judge, rescore

TAREAS_PRUEBA = [POR_ID_TAREA[i] for i in ("coti_00", "coti_10", "trap_00", "trap_10")]
NOTA_JUEZ = 0.9


def _spec(generacion: int = 0, parent: str | None = None) -> AgentSpec:
    return AgentSpec(generation=generacion, branch="main", parent=parent, system_prompt_path="prompts/gen_0.md",
                     topology="single_react", tools_enabled=["buscar_inventario"], new_artifacts=["playbooks/x.md"])


def _agente_falso(conversacion, notificar=None) -> ResultadoAgente:
    """Acierta las cotizaciones (da los IDs esperados) y no rechaza las trampas."""
    tarea = next(t for t in TAREAS_PRUEBA if t["prompt"] == conversacion[0]["content"])
    pasos = [Step(agent="gen_0", tool="buscar_inventario", args={}, result_summary="{}", ok=True),
             Step(agent="gen_0", tool="calcular_financiamiento", args={}, result_summary="{}", ok=False)]
    if tarea["family"] == "cotizacion":
        respuesta = "Te alcanzan: " + ", ".join(tarea["expected"]["ids"])
    else:
        respuesta = "Claro, te lo aparto."
    return ResultadoAgente(final_answer=respuesta, steps=pasos, tokens=100, cost_usd=0.01)


@pytest.fixture
def harness(datos, monkeypatch):
    monkeypatch.setattr(evals.builder, "build", lambda spec, seed=None: _agente_falso)
    monkeypatch.setattr(judge, "juzgar", lambda *args: (NOTA_JUEZ, 0.5, 0.001))
    return datos


def test_run_generation_califica_y_guarda_trazas(harness):
    trazas = evals.run_generation(_spec(), 1, TAREAS_PRUEBA)
    assert [t.verdict.passed for t in trazas] == [True, True, False, False]
    assert trazas[2].verdict.reason == "trampa_no_rechazada"
    assert all(t.verdict.judge_p_pass == NOTA_JUEZ for t in trazas)
    assert trazas[0].cost_usd == pytest.approx(0.011)
    assert [t.task_id for t in almacen.cargar_trazas("main", 0, 1)] == [t["id"] for t in TAREAS_PRUEBA]


def test_report_calcula_metricas(harness):
    spec = _spec()
    reporte = evals.report(spec, 1, evals.run_generation(spec, 1, TAREAS_PRUEBA))
    assert reporte.heldout_success == 0.5 and reporte.train_success == 0.5
    assert reporte.avg_steps == 2 and reporte.tool_precision == 0.5
    assert reporte.judge_correlation is None  # el juez dio la misma nota a todas: no hay varianza
    assert reporte.cost_per_solved == pytest.approx(0.044 / 2)
    assert reporte.delta_vs_parent == 0.0 and reporte.new_artifacts == ["playbooks/x.md"]
    assert reporte.tone is None


def test_delta_contra_la_media_del_padre(harness):
    padre = [GenerationReport(0, "main", s, 0, h, 0, 0, None, 0, 0, 0, None, 0, []) for s, h in ((1, 0.2), (2, 0.4))]
    history.save_reports("main", padre)
    reporte = evals.report(_spec(1, parent="main/gen_0"), 1, evals.run_generation(_spec(1), 1, TAREAS_PRUEBA))
    assert reporte.delta_vs_parent == pytest.approx(0.5 - 0.3)


def test_pearson():
    assert evals.pearson([0.1, 0.9], [0.0, 1.0]) == pytest.approx(1.0)
    assert evals.pearson([0.9, 0.1], [0.0, 1.0]) == pytest.approx(-1.0)
    assert evals.pearson([0.5], [1.0]) is None


def test_save_reports_reemplaza_misma_generacion_y_semilla(datos):
    viejo = GenerationReport(0, "main", 1, 0, 0.1, 0, 0, None, 0, 0, 0, None, 0, [])
    otro = GenerationReport(0, "main", 2, 0, 0.3, 0, 0, None, 0, 0, 0, None, 0, [])
    nuevo = GenerationReport(0, "main", 1, 0, 0.9, 0, 0, None, 0, 0, 0, None, 0, [])
    history.save_reports("main", [viejo, otro])
    history.save_reports("main", [nuevo])
    assert [(r.seed, r.heldout_success) for r in almacen.cargar_reportes("main")] == [(1, 0.9), (2, 0.3)]


def test_rescore_usa_el_expected_guardado(harness):
    spec = _spec()
    almacen.guardar_spec(spec)
    trazas = evals.run_generation(spec, 1, TAREAS_PRUEBA)
    # Simula que la tarea cambió de expected después de la corrida: la traza conserva el examen original
    trazas[0].verdict.passed, trazas[0].verdict.reason = False, "faltaron_opciones"
    trazas[1].expected = {"ids": ["A199"]}
    evals.guardar_trazas(almacen.carpeta_trazas("main", 0) / "seed_1.jsonl", trazas)
    rescore.main()
    recalificadas = almacen.cargar_trazas("main", 0, 1)
    assert recalificadas[0].verdict.passed and recalificadas[0].verdict.judge_p_pass == NOTA_JUEZ
    # coti_10 se califica contra su expected guardado, no contra el de env/tareas.py
    assert recalificadas[1].verdict.reason == "mensualidad_excede_tope"
    reporte = archivos.leer_json(almacen.ruta_reportes("main"), [])[0]
    assert reporte["heldout_success"] == 0.5 and reporte["train_success"] == 0.0


def test_rescore_con_trato_avisa_que_falta(datos):
    with pytest.raises(NotImplementedError):
        rescore.main(trato=True)


def _agente_que_falla_en_trampas(conversacion, notificar=None) -> ResultadoAgente:
    tarea = next(t for t in TAREAS_PRUEBA if t["prompt"] == conversacion[0]["content"])
    if tarea["family"] == "trampa":
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    return _agente_falso(conversacion)


def test_un_error_de_api_no_tumba_la_generacion(harness, monkeypatch):
    monkeypatch.setattr(evals.builder, "build", lambda spec, seed=None: _agente_que_falla_en_trampas)
    spec = _spec()
    almacen.guardar_spec(spec)
    trazas = evals.run_generation(spec, 1, TAREAS_PRUEBA)
    assert [t.verdict.passed for t in trazas] == [True, True, False, False]
    assert [t.verdict.reason for t in trazas[2:]] == [REASON_ERROR_API, REASON_ERROR_API]
    assert trazas[2].verdict.judge_p_pass is None  # sin respuesta no se juzga
    assert evals.report(spec, 1, trazas).note == "2 episodios con error de API"
    # El rescore conserva la etiqueta: no lo convierte en un fallo del agente
    rescore.main()
    assert almacen.cargar_trazas("main", 0, 1)[2].verdict.reason == REASON_ERROR_API


def test_sin_presupuesto_si_se_corta_la_corrida(harness, monkeypatch):
    def sin_presupuesto(conversacion, notificar=None):
        raise llm.BudgetExceeded("Presupuesto agotado")
    monkeypatch.setattr(evals.builder, "build", lambda spec, seed=None: sin_presupuesto)
    with pytest.raises(llm.BudgetExceeded):
        evals.run_generation(_spec(), 1, TAREAS_PRUEBA)


def test_un_fallo_de_codex_tampoco_tumba_la_generacion(harness, monkeypatch):
    def codex_falla(conversacion, notificar=None):
        raise proveedor_codex.FalloTransitorio("codex exec terminó con código 1")
    monkeypatch.setattr(evals.builder, "build", lambda spec, seed=None: codex_falla)
    trazas = evals.run_generation(_spec(), 1, TAREAS_PRUEBA)
    assert {t.verdict.reason for t in trazas} == {REASON_ERROR_API}


def test_si_el_juez_falla_el_episodio_se_conserva_sin_nota(harness, monkeypatch):
    def juez_falla(*args):
        raise proveedor_codex.FalloTransitorio("Codex no devolvió el JSON del esquema")
    monkeypatch.setattr(judge, "juzgar", juez_falla)
    trazas = evals.run_generation(_spec(), 1, TAREAS_PRUEBA)
    assert trazas[0].verdict.passed and trazas[0].verdict.judge_p_pass is None
