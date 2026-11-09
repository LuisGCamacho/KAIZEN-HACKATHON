"""Tests del cliente LLM que no llaman a la API: costo, precios y corte por presupuesto."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import llm


@pytest.fixture(autouse=True)
def sin_servidor_local(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def test_costo_usa_el_precio_del_modelo():
    uso = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    precio_entrada, precio_salida = llm.PRECIOS_POR_MILLON["gpt-4.1-mini"]
    assert llm.costo_usd("gpt-4.1-mini", uso) == pytest.approx(precio_entrada + precio_salida)


def test_precio_configurable_por_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("PRICE_MI_MODELO_1_0", "1.5,3")
    assert llm.precio_por_millon("mi-modelo-1.0") == (1.5, 3.0)


def test_modelo_desconocido_se_asume_caro():
    assert llm.precio_por_millon("modelo-inexistente") == llm.PRECIO_MODELO_DESCONOCIDO


def test_modelo_local_no_cuesta(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    assert llm.precio_por_millon("gpt-4.1") == (0.0, 0.0)


def test_corta_al_alcanzar_el_presupuesto(monkeypatch, tmp_path):
    # El gasto se lee de spend.json (compartido entre procesos), no de un atributo en memoria
    monkeypatch.setattr(llm, "ARCHIVO_GASTO", tmp_path / "spend.json")
    (tmp_path / "spend.json").write_text(f'{{"usd": {llm.PRESUPUESTO_USD}}}', encoding="utf-8")
    with pytest.raises(llm.BudgetExceeded):
        llm.chat([{"role": "user", "content": "hola"}])  # se corta antes de crear el cliente o llamar a la API
