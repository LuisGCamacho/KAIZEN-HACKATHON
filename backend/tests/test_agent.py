"""Tests del agente con un modelo falso: no llaman a la API ni gastan presupuesto."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.agent import MAX_CARACTERES_RESUMEN, RESPUESTA_PASOS_AGOTADOS, Agente, Herramienta
from core import llm

TOKENS_POR_LLAMADA = 10
COSTO_POR_LLAMADA = 0.001


def respuesta_final(texto: str) -> SimpleNamespace:
    return SimpleNamespace(content=texto, tool_calls=None)


def pedir_herramienta(nombre: str, argumentos: dict | str, id_llamada: str = "llamada_1",
                      texto: str | None = None) -> SimpleNamespace:
    argumentos_json = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    llamada = SimpleNamespace(id=id_llamada, function=SimpleNamespace(name=nombre, arguments=argumentos_json))
    return SimpleNamespace(content=texto, tool_calls=[llamada])


@pytest.fixture
def modelo_guionado(monkeypatch):
    """Sustituye llm.chat por una lista de respuestas que se entregan en orden."""
    guion: list[SimpleNamespace] = []
    llamadas_recibidas: list[list[dict]] = []

    def chat_falso(mensajes, **_opciones):
        llamadas_recibidas.append(list(mensajes))
        return guion.pop(0), TOKENS_POR_LLAMADA, COSTO_POR_LLAMADA

    monkeypatch.setattr(llm, "chat", chat_falso)
    return SimpleNamespace(guion=guion, llamadas=llamadas_recibidas)


def herramienta(nombre: str, funcion, generada: bool = False) -> Herramienta:
    esquema = {"type": "function", "function": {"name": nombre, "parameters": {"type": "object", "properties": {}}}}
    return Herramienta(nombre, funcion, esquema, generada)


def sumar(a: int, b: int) -> dict:
    return {"total": a + b}


def test_responde_sin_herramientas(modelo_guionado):
    modelo_guionado.guion.append(respuesta_final("Sí, está cubierto."))
    resultado = Agente("gen_0", "instrucciones", {}).ejecutar([{"role": "user", "content": "hola"}])
    assert resultado.final_answer == "Sí, está cubierto."
    assert resultado.steps == []
    assert resultado.tokens == TOKENS_POR_LLAMADA
    assert resultado.cost_usd == pytest.approx(COSTO_POR_LLAMADA)
    assert not resultado.exhausted


def test_usa_herramienta_registra_step_y_eventos(modelo_guionado):
    modelo_guionado.guion += [pedir_herramienta("sumar", {"a": 2, "b": 3}), respuesta_final("Son 5.")]
    eventos: list[dict] = []
    agente = Agente("gen_0", "instrucciones", {"sumar": herramienta("sumar", sumar)})

    resultado = agente.ejecutar([{"role": "user", "content": "2+3"}], eventos.append)

    assert resultado.final_answer == "Son 5."
    [paso] = resultado.steps
    assert (paso.agent, paso.tool, paso.args, paso.ok) == ("gen_0", "sumar", {"a": 2, "b": 3}, True)
    assert json.loads(paso.result_summary) == {"total": 5}
    assert [evento["type"] for evento in eventos] == ["tool_call", "tool_result"]
    # El resultado de la tool vuelve al modelo en la segunda llamada
    assert modelo_guionado.llamadas[1][-1] == {"role": "tool", "tool_call_id": "llamada_1",
                                               "content": json.dumps({"total": 5})}


@pytest.mark.parametrize("salida, esperado", [
    ({"ok": False, "motivo": "agenda llena"}, False),
    ({"error": "auto inexistente"}, False),
    ({"ok": True, "folio": "INS-1"}, True),
])
def test_ok_sigue_el_contrato_de_step(modelo_guionado, salida, esperado):
    modelo_guionado.guion += [pedir_herramienta("tool", {}), respuesta_final("listo")]
    agente = Agente("gen_0", "instrucciones", {"tool": herramienta("tool", lambda: salida)})
    assert agente.ejecutar([]).steps[0].ok is esperado


@pytest.mark.parametrize("nombre, argumentos", [
    ("no_existe", {}),  # herramienta desconocida
    ("sumar", "{no es json"),  # argumentos inválidos
    ("sumar", {"a": 1}),  # falta un argumento: la función lanza TypeError
])
def test_los_errores_no_cortan_el_episodio(modelo_guionado, nombre, argumentos):
    modelo_guionado.guion += [pedir_herramienta(nombre, argumentos), respuesta_final("No pude calcularlo.")]
    agente = Agente("gen_0", "instrucciones", {"sumar": herramienta("sumar", sumar)})
    resultado = agente.ejecutar([])
    assert resultado.final_answer == "No pude calcularlo."
    assert resultado.steps[0].ok is False
    assert "error" in json.loads(resultado.steps[0].result_summary)


def test_agotar_pasos_marca_exhausted(modelo_guionado):
    max_pasos = 3
    modelo_guionado.guion += [pedir_herramienta("sumar", {"a": 1, "b": 1}) for _ in range(max_pasos)]
    agente = Agente("gen_0", "instrucciones", {"sumar": herramienta("sumar", sumar)}, max_pasos=max_pasos)
    resultado = agente.ejecutar([])
    assert resultado.exhausted
    assert resultado.final_answer == RESPUESTA_PASOS_AGOTADOS
    assert len(resultado.steps) == max_pasos


def test_resumen_se_recorta_al_tamano_del_contrato(modelo_guionado):
    modelo_guionado.guion += [pedir_herramienta("larga", {}), respuesta_final("ok")]
    agente = Agente("gen_0", "instrucciones", {"larga": herramienta("larga", lambda: {"texto": "x" * 1000})})
    assert len(agente.ejecutar([]).steps[0].result_summary) == MAX_CARACTERES_RESUMEN


def test_marca_las_herramientas_generadas(modelo_guionado):
    modelo_guionado.guion += [pedir_herramienta("generada", {}), respuesta_final("ok")]
    eventos: list[dict] = []
    agente = Agente("gen_1", "instrucciones", {"generada": herramienta("generada", lambda: {}, generada=True)})
    resultado = agente.ejecutar([], eventos.append)
    assert resultado.steps[0].generated
    assert eventos[0]["generated"] is True
