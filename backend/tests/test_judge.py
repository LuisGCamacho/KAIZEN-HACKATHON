"""Tests del juez con un modelo falso: no llaman a la API ni gastan presupuesto."""
from __future__ import annotations

import inspect
import json

import pytest

from core import llm
from core.contracts import Step
from evaluation import judge

PASOS = [Step(agent="gen_0", tool="politica_garantia", args={"auto_id": "A001", "tipo_falla": "motor"},
              result_summary='{"cubierto": true}')]


@pytest.fixture
def modelo_falso(monkeypatch):
    """Sustituye llm.chat_json: devuelve `respuesta` (o lanza `error`) y guarda lo que recibió."""
    estado = {"respuesta": {"p_pasa": 0.8, "explicacion": 0.6}, "error": None, "recibido": None}

    def chat_json_falso(sistema, usuario, **opciones):
        estado["recibido"] = {"sistema": sistema, "usuario": usuario, **opciones}
        if estado["error"]:
            raise estado["error"]
        return estado["respuesta"], 0.0004

    monkeypatch.setattr(llm, "chat_json", chat_json_falso)
    return estado


def test_devuelve_las_notas_y_el_costo(modelo_falso):
    assert judge.juzgar("¿Está cubierto?", PASOS, "Sí, está cubierto.", 0) == (0.8, 0.6, 0.0004)


def test_el_juez_recibe_rubrica_pasos_y_respuesta(modelo_falso):
    judge.juzgar("¿Está cubierto?", PASOS, "Sí, está cubierto.", 0)
    recibido = modelo_falso["recibido"]
    assert recibido["sistema"] == judge.leer_rubrica(0)
    assert "¿Está cubierto?" in recibido["usuario"]
    assert '"cubierto": true' in recibido["usuario"]
    assert "Sí, está cubierto." in recibido["usuario"]
    assert recibido["temperatura"] == judge.TEMPERATURA_JUEZ


def test_el_juez_no_puede_recibir_la_respuesta_esperada():
    """La firma no tiene ningún parámetro para la respuesta correcta: el juez opina sin conocerla."""
    parametros = set(inspect.signature(judge.juzgar).parameters)
    assert parametros == {"peticion", "pasos", "respuesta", "version_rubrica"}


@pytest.mark.parametrize("respuesta, esperado", [
    ({"p_pasa": 1.7, "explicacion": -0.2}, (1.0, 0.0)),  # fuera de rango: se acota a [0, 1]
    ({"p_pasa": "0.3", "explicacion": "alta"}, (0.3, None)),  # texto numérico sí, texto libre no
    ({}, (None, None)),  # faltan campos: sin nota
])
def test_notas_se_acotan_o_quedan_vacias(modelo_falso, respuesta, esperado):
    modelo_falso["respuesta"] = respuesta
    p_pasa, explicacion, _costo = judge.juzgar("x", [], "y", 0)
    assert (p_pasa, explicacion) == esperado


def test_si_el_modelo_falla_no_se_inventa_nota(modelo_falso):
    modelo_falso["error"] = json.JSONDecodeError("JSON cortado", "{", 1)
    assert judge.juzgar("x", [], "y", 0) == (None, None, 0.0)


def test_sin_presupuesto_se_detiene_la_corrida(modelo_falso):
    modelo_falso["error"] = llm.BudgetExceeded("Presupuesto agotado")
    with pytest.raises(llm.BudgetExceeded):
        judge.juzgar("x", [], "y", 0)


def test_rubrica_inexistente_es_un_error():
    with pytest.raises(FileNotFoundError):
        judge.leer_rubrica(999)


def test_rubrica_v0_pide_las_dos_notas():
    rubrica = judge.leer_rubrica(0)
    assert '"p_pasa"' in rubrica and '"explicacion"' in rubrica


def test_juez_apagado_no_llama_al_modelo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: llamadas.append(1) or ({"p_pasa": 1}, 0.1))
    monkeypatch.setenv("KAIZEN_JUDGE", "off")
    assert judge.juzgar("¿Hola?", [], "Sí.", 0) == (None, None, 0.0)
    assert llamadas == []
