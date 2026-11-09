"""Tests del meta-destilador con un modelo falso y data/ temporal (fixture `datos`): no gastan presupuesto."""
from __future__ import annotations

import pytest

from core import artifacts, llm, versions
from improve import meta_distiller

PROMPT_V0 = "Escribe un procedimiento.\n"
PROMPT_NUEVO = "Escribe 3 a 6 pasos y nombra la herramienta exacta de cada paso."
DELTAS_QUE_CAEN = [0.2, 0.05]


@pytest.fixture
def modelo(datos, monkeypatch):
    """Modelo falso que guarda lo que recibió; prompt v0 del destilador en el data/ temporal."""
    versions.ruta("distiller_prompt", 0).write_text(PROMPT_V0, encoding="utf-8")
    estado = {"respuesta": {"prompt": PROMPT_NUEVO, "diagnostico": "Los pasos eran vagos."}, "recibido": []}

    def chat_json_falso(sistema, usuario, **_opciones):
        estado["recibido"].append(sistema + usuario)
        return estado["respuesta"], 0.0

    monkeypatch.setattr(llm, "chat_json", chat_json_falso)
    return estado


def reescribir(deltas: list[float]) -> int:
    return meta_distiller.quizas_reescribir(deltas, 0, 3, "main", log=lambda _texto: None)


@pytest.mark.parametrize("deltas, esperado", [
    ([], False),
    ([0.1], False),  # una sola mejora: no hay con qué comparar
    ([0.1, 0.15], False),  # sigue mejorando más
    ([0.1, 0.1], False),  # mejora igual y positiva
    ([0.15, 0.05], True),  # mejora menos que antes
    ([0.2, 0.0, 0.0], True),  # se estancó
    ([0.1, -0.05], True),  # empeoró
])
def test_deberia_reescribir(deltas, esperado):
    assert meta_distiller.deberia_reescribir(deltas) is esperado


def test_si_los_deltas_no_caen_conserva_el_prompt(modelo):
    assert reescribir([0.1, 0.15]) == 0
    assert modelo["recibido"] == []  # no gasta en el modelo


def test_si_los_deltas_caen_escribe_la_v1(modelo):
    assert reescribir(DELTAS_QUE_CAEN) == 1
    assert versions.texto("distiller_prompt", 1) == PROMPT_NUEVO + "\n"
    [entrada] = versions.historial("distiller_prompt")
    assert (entrada["generation"], entrada["branch"], entrada["deltas"]) == (3, "main", DELTAS_QUE_CAEN)
    assert entrada["diagnosis"] == "Los pasos eran vagos."


def test_el_modelo_ve_su_prompt_y_los_playbooks_de_su_rama(modelo):
    for rama, contenido in (("main", "1. Llama buscar_inventario."), ("otra", "PLAYBOOK_DE_OTRA_RAMA")):
        artifacts.add({"name": f"x_g1_{rama}.md", "kind": "playbook", "generation": 1, "branch": rama,
                       "origin": "x", "origin_failures": 2, "accepted": True, "path": "", "content": contenido})
    reescribir(DELTAS_QUE_CAEN)
    [pedido] = modelo["recibido"]
    assert PROMPT_V0.strip() in pedido and "1. Llama buscar_inventario." in pedido
    assert "PLAYBOOK_DE_OTRA_RAMA" not in pedido


@pytest.mark.parametrize("respuesta", [{"prompt": "   ", "diagnostico": "nada"}, {}])
def test_prompt_vacio_se_descarta(modelo, respuesta):
    modelo["respuesta"] = respuesta
    assert reescribir(DELTAS_QUE_CAEN) == 0
    assert versions.historial("distiller_prompt") == []
