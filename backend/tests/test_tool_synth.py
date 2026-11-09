"""Tests de la síntesis de tools y su gate. El modelo es falso; pytest del gate corre de verdad en otro proceso."""
from __future__ import annotations

import json

import openai
import pytest

from agents import builder
from core import artifacts, llm, paths
from improve import tool_synth

CODIGO_VALIDO = '''from env.tools import calcular_enganche


def enganche_y_resto(precio: float, porcentaje: float) -> dict:
    """Generada en gen 1 por la causa faltaron_opciones (fixture de prueba)."""
    enganche = calcular_enganche(precio, porcentaje)["enganche"]
    return {"enganche": enganche, "resto": precio - enganche}
'''
TESTS_VALIDOS = '''from env.tools import calcular_enganche
from tools.generated.enganche_y_resto import enganche_y_resto


def test_resto_es_precio_menos_enganche():
    esperado = calcular_enganche(300000, 20)["enganche"]
    assert enganche_y_resto(300000, 20)["resto"] == 300000 - esperado
'''
TESTS_QUE_FALLAN = TESTS_VALIDOS.replace("300000 - esperado", "-1")


def propuesta(**cambios) -> dict:
    valores = {"name": "enganche_y_resto", "description": "Enganche y lo que falta por financiar.",
               "parameters": {"type": "object", "properties": {"precio": {"type": "number"},
                                                               "porcentaje": {"type": "number"}}},
               "code": CODIGO_VALIDO, "tests": TESTS_VALIDOS}
    return valores | cambios


@pytest.fixture
def modelo(datos, monkeypatch):
    """Modelo falso: devuelve `respuesta` o lanza `error`. Usa las rutas temporales del fixture `datos`."""
    estado = {"respuesta": propuesta(), "error": None}

    def chat_json_falso(_sistema, _usuario, **_opciones):
        if estado["error"]:
            raise estado["error"]
        return estado["respuesta"], 0.0

    monkeypatch.setattr(llm, "chat_json", chat_json_falso)
    return estado


def sintetizar() -> dict | None:
    return tool_synth.sintetizar("faltaron_opciones", "ejemplos", 4, 1, "main")


# ---------- Revisión del AST ----------
@pytest.mark.parametrize("codigo, fragmento", [
    ("import os\ndef f(): return os.getcwd()", "import prohibido: os"),
    ("from subprocess import run", "import prohibido: subprocess"),
    ("from . import algo", "import prohibido: ."),
    ("def f(): return open('x')", "nombre prohibido: open"),
    ("def f(): return eval('1')", "nombre prohibido: eval"),
    ("def f(): return __builtins__", "nombre prohibido: __builtins__"),
    ("def f(x): return x.__class__", "atributo dunder prohibido"),
    ("def f(:", "sintaxis inválida"),
])
def test_ast_rechaza_lo_peligroso(codigo, fragmento):
    assert fragmento in tool_synth.revisar_ast(codigo)


def test_ast_acepta_imports_permitidos():
    assert tool_synth.revisar_ast(CODIGO_VALIDO) is None
    assert tool_synth.revisar_ast(TESTS_VALIDOS) is None


@pytest.mark.parametrize("nombre, fragmento", [
    ("buscar_inventario", "choca con una herramienta base"),
    ("../../escapar", "nombre inválido"),
    ("Mayusculas", "nombre inválido"),
    ("class", "nombre inválido"),
])
def test_nombres_invalidos(nombre, fragmento):
    assert fragmento in tool_synth.revisar_nombre(nombre)


# ---------- Flujo completo ----------
def test_tool_valida_pasa_el_gate_y_el_builder_la_carga(modelo, monkeypatch):
    resultado = sintetizar()

    assert resultado["accepted"] is True, resultado["rejection"]
    assert resultado["path"] == "tools/generated/enganche_y_resto.py"
    esquema = json.loads((paths.TOOLS_GENERADAS / "enganche_y_resto.json").read_text(encoding="utf-8"))
    assert esquema["schema"]["function"]["name"] == "enganche_y_resto"
    assert esquema["origin"] == "faltaron_opciones"
    [registro] = artifacts.all_artifacts()
    assert (registro["kind"], registro["origin_failures"], registro["code"]) == ("tool", 4, CODIGO_VALIDO)

    monkeypatch.setattr(builder, "TOOLS_GENERADAS", paths.TOOLS_GENERADAS)
    herramienta = builder.cargar_herramienta_generada("enganche_y_resto")
    assert herramienta.generada is True
    assert herramienta.funcion(precio=100000, porcentaje=10)["resto"] > 0


def test_tool_con_tests_fallidos_se_rechaza_y_queda_como_evidencia(modelo):
    modelo["respuesta"] = propuesta(tests=TESTS_QUE_FALLAN)
    resultado = sintetizar()

    assert resultado["accepted"] is False
    assert resultado["rejection"].startswith("tests fallaron")
    assert resultado["path"] == "tools/rejected/enganche_y_resto.py"
    assert (paths.TOOLS_RECHAZADAS / "enganche_y_resto.py").exists()
    assert not (paths.TOOLS_GENERADAS / "enganche_y_resto.py").exists()
    assert not (paths.TOOLS_GENERADAS / "enganche_y_resto.json").exists()  # el builder no la verá


def test_import_prohibido_se_rechaza_sin_correr_tests(modelo, monkeypatch):
    monkeypatch.setattr(tool_synth, "correr_tests", lambda _nombre: pytest.fail("no debió correr pytest"))
    modelo["respuesta"] = propuesta(code="import os\n" + CODIGO_VALIDO)
    resultado = sintetizar()
    assert resultado["accepted"] is False
    assert resultado["rejection"] == "import prohibido: os"


def test_nombre_malicioso_no_escribe_archivos(modelo, tmp_path):
    modelo["respuesta"] = propuesta(name="../../escapar")
    resultado = sintetizar()
    assert resultado["accepted"] is False
    assert resultado["path"] == ""
    assert not list(tmp_path.rglob("escapar*"))


@pytest.mark.parametrize("cambios, fragmento", [
    ({"code": "def otra_cosa(): return {}"}, "no define la función"),
    ({"tests": "from tools.generated.enganche_y_resto import enganche_y_resto\n"}, "no define ninguna función test_"),
])
def test_codigo_o_tests_incompletos(modelo, cambios, fragmento):
    modelo["respuesta"] = propuesta(**cambios)
    assert fragmento in sintetizar()["rejection"]


def test_nombre_repetido_se_renombra_con_la_generacion(modelo):
    assert sintetizar()["name"] == "enganche_y_resto"
    segunda = sintetizar()
    assert segunda["name"] == "enganche_y_resto_g1"
    assert segunda["accepted"] is True, segunda["rejection"]  # el código y los tests también se renombraron


def test_el_modelo_decide_que_no_hace_falta(modelo):
    modelo["respuesta"] = {"skip": True, "why": "es un error de formato, no de cálculo"}
    assert sintetizar() is None
    assert artifacts.all_artifacts() == []


def test_timeout_del_modelo_se_registra_sin_cortar_la_generacion(modelo):
    modelo["error"] = openai.APITimeoutError(request=None)
    resultado = sintetizar()
    assert resultado["accepted"] is False
    assert resultado["path"] == ""
    assert resultado["rejection"] == "no generada: el modelo no respondió a tiempo"
