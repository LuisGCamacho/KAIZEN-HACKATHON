"""Tests del meta-juez con un modelo falso y data/ temporal (fixture `datos`): no gastan presupuesto."""
from __future__ import annotations

import pytest

from core import llm, versions
from core.contracts import Step, Trace, Verdict
from improve import meta_judge

RUBRICA_V0 = 'Juzga. Devuelve JSON con "p_pasa" y "explicacion".\n'
RUBRICA_NUEVA = 'Revisa que la respuesta cite politica_garantia. Devuelve JSON con "p_pasa" y "explicacion".'
MARCADOR_HELDOUT = "PETICION_HELDOUT_SECRETA"


def traza(split: str, paso: bool, p_pasa: float | None, prompt: str = "¿Está cubierto?") -> Trace:
    pasos = [Step(agent="gen_0", tool="politica_garantia", args={}, result_summary='{"cubierto": false}')]
    veredicto = Verdict(passed=paso, reason=None if paso else "garantia_mal_interpretada", judge_p_pass=p_pasa)
    return Trace(task_id="gara_10", family="garantia", generation=0, branch="main", seed=1, split=split,
                 prompt=prompt, expected={"cubierto": False}, steps=pasos, final_answer="Sí, está cubierto.",
                 verdict=veredicto, tokens=10, cost_usd=0.0)


def juez_equivocado(cuantas: int, split: str = "train", prompt: str = "¿Está cubierto?") -> list[Trace]:
    """El juez da 0.9 a respuestas que el verificador reprobó."""
    return [traza(split, False, 0.9, prompt) for _ in range(cuantas)]


@pytest.fixture
def modelo(datos, monkeypatch):
    """Modelo falso que guarda lo que recibió; rúbrica v0 en el data/ temporal."""
    versions.ruta("rubrica", 0).write_text(RUBRICA_V0, encoding="utf-8")
    estado = {"respuesta": {"rubrica": RUBRICA_NUEVA, "cambio": "Exigir sustento de la política."},
              "recibido": []}

    def chat_json_falso(sistema, usuario, **_opciones):
        estado["recibido"].append(sistema + usuario)
        return estado["respuesta"], 0.0

    monkeypatch.setattr(llm, "chat_json", chat_json_falso)
    return estado


def calibrar(trazas: list[Trace]) -> int:
    return meta_judge.calibrar(trazas, 0, 1, "main", log=lambda _texto: None)


def test_con_pocas_discrepancias_conserva_la_rubrica(modelo):
    assert calibrar(juez_equivocado(meta_judge.MIN_DISCREPANCIAS - 1)) == 0
    assert modelo["recibido"] == []  # no gasta en el modelo


def test_con_suficientes_discrepancias_escribe_la_v1(modelo):
    trazas = juez_equivocado(3) + [traza("train", True, 0.8), traza("train", False, 0.1)]
    assert calibrar(trazas) == 1
    assert versions.texto("rubrica", 1) == RUBRICA_NUEVA + "\n"
    [entrada] = versions.historial("rubrica")
    assert (entrada["generation"], entrada["branch"], entrada["discrepancies"]) == (1, "main", 3)
    assert entrada["change"] == "Exigir sustento de la política."
    assert entrada["correlation_before"] == meta_judge.correlacion_juez(trazas)


def test_heldout_no_cuenta_ni_llega_al_modelo(modelo):
    trazas = juez_equivocado(2) + juez_equivocado(5, "heldout", MARCADOR_HELDOUT)
    assert calibrar(trazas) == 0  # las 5 discrepancias de held-out no se cuentan

    trazas = juez_equivocado(3) + juez_equivocado(5, "heldout", MARCADOR_HELDOUT)
    assert calibrar(trazas) == 1
    assert not any(MARCADOR_HELDOUT in texto for texto in modelo["recibido"])


@pytest.mark.parametrize("respuesta", [
    {"rubrica": "", "cambio": "nada"},
    {"rubrica": "Juzga con cuidado.", "cambio": "se perdió el formato de salida"},
    {},
])
def test_rubrica_invalida_se_descarta(modelo, respuesta):
    modelo["respuesta"] = respuesta
    assert calibrar(juez_equivocado(3)) == 0
    assert versions.historial("rubrica") == []


def test_correlacion_juez():
    acierta = [traza("train", True, 0.9), traza("train", True, 0.8), traza("train", False, 0.1)]
    assert meta_judge.correlacion_juez(acierta) > 0.9
    assert meta_judge.correlacion_juez(acierta[:2]) is None  # muy pocos pares
    assert meta_judge.correlacion_juez([traza("train", True, 0.5)] * 4) is None  # nada varía
    assert meta_judge.correlacion_juez([traza("train", True, None)] * 4) is None  # sin notas del juez


def test_discrepancias_ignora_trazas_sin_nota():
    trazas = [traza("train", False, None), traza("train", False, 0.4), traza("train", False, 0.6)]
    assert len(meta_judge.discrepancias(trazas)) == 1
