"""Garantías de la auto-mejora recursiva (RSI) en un solo lugar.

Si alguno falla, los números de la demo dejan de ser creíbles:
- held-out nunca llega al destilador ni al meta-juez (si no, el éxito en held-out estaría inflado);
- el gate de tools rechaza código peligroso y solo acepta tools cuyos tests pasan de verdad;
- los meta-niveles solo actúan cuando hay evidencia (discrepancias del juez o deltas que caen).
Los tests detallados de cada pieza están en test_distiller, test_tool_synth, test_meta_judge y test_meta_distiller.
"""
from __future__ import annotations

from core.contracts import Step, Trace, Verdict
from improve import distiller, meta_distiller, meta_judge, tool_synth

CODIGO_TOOL = '''from env.tools import calcular_enganche


def enganche_mas_mil(precio: float, porcentaje: float) -> dict:
    return {"total": calcular_enganche(precio, porcentaje)["enganche"] + 1000}
'''
TESTS_TOOL = '''from env.tools import calcular_enganche
from tools.generated.enganche_mas_mil import enganche_mas_mil


def test_suma_mil():
    assert enganche_mas_mil(200000, 10)["total"] == calcular_enganche(200000, 10)["enganche"] + 1000
'''


def traza(split: str, paso: bool, p_pasa: float | None = None) -> Trace:
    pasos = [Step(agent="gen_0", tool="buscar_inventario", args={}, result_summary="[]")]
    veredicto = Verdict(passed=paso, reason=None if paso else "faltaron_opciones", judge_p_pass=p_pasa)
    return Trace(task_id="cot_1", family="cotizacion", generation=0, branch="main", seed=1, split=split,
                 prompt="Busco un sedán", expected={}, steps=pasos, final_answer="No hay.",
                 verdict=veredicto, tokens=0, cost_usd=0.0)


# ---------- held-out nunca se usa para aprender ----------
def test_destilador_nunca_ve_heldout():
    trazas = [traza("train", False), traza("heldout", False), traza("train", True)]
    assert [t.split for t in distiller.fallos_de_train(trazas)] == ["train"]


def test_meta_juez_nunca_ve_heldout():
    trazas = [traza("heldout", False, 0.9), traza("train", False, 0.9)]
    assert [t.split for t in meta_judge.trazas_de_train(trazas)] == ["train"]


# ---------- el gate de tools ----------
def test_gate_rechaza_codigo_peligroso():
    assert "import prohibido" in tool_synth.revisar_ast("import os\ndef f(): return os.getcwd()")
    assert "nombre prohibido" in tool_synth.revisar_ast("def f(): return open('x')")
    assert "dunder" in tool_synth.revisar_ast("def f(): return ().__class__")
    assert tool_synth.revisar_ast(CODIGO_TOOL) is None


def test_gate_corre_pytest_de_verdad(datos):
    assert tool_synth.pasar_gate("enganche_mas_mil", CODIGO_TOOL, TESTS_TOOL) is None
    tests_mal = TESTS_TOOL.replace("+ 1000", "+ 1")
    assert tool_synth.pasar_gate("enganche_mas_mil", CODIGO_TOOL, tests_mal).startswith("tests fallaron")


# ---------- los meta-niveles solo actúan con evidencia ----------
def test_meta_juez_necesita_discrepancias():
    juez_equivocado = [traza("train", False, 0.9)] * meta_judge.MIN_DISCREPANCIAS
    assert len(meta_judge.discrepancias(juez_equivocado)) >= meta_judge.MIN_DISCREPANCIAS
    juez_acertado = [traza("train", False, 0.1)] * meta_judge.MIN_DISCREPANCIAS
    assert meta_judge.discrepancias(juez_acertado) == []


def test_meta_destilador_solo_si_el_delta_cae():
    assert not meta_distiller.deberia_reescribir([0.1])
    assert not meta_distiller.deberia_reescribir([0.1, 0.15])
    assert meta_distiller.deberia_reescribir([0.15, 0.05])
    assert meta_distiller.deberia_reescribir([0.2, 0.0, 0.0])
