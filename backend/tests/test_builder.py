"""Tests del builder con carpetas temporales y herramientas de prueba: no llaman a la API."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest

# env/tools.py lo entrega Backend A. Mientras no exista, un módulo vacío permite importar el builder;
# cada test inyecta sus propias herramientas base.
try:
    import env.tools  # noqa: F401
except ModuleNotFoundError:
    sys.modules["env.tools"] = types.SimpleNamespace(FUNCIONES={}, ESQUEMAS={})

from agents import builder  # noqa: E402
from core import llm  # noqa: E402
from core.contracts import AgentSpec  # noqa: E402

CODIGO_TOOL_GENERADA = '''
def duplicar(numero: int) -> dict:
    """Generada en gen 1 por el cluster faltaron_opciones (fixture de prueba)."""
    return {"resultado": numero * 2}
'''


def esquema(nombre: str) -> dict:
    return {"type": "function", "function": {"name": nombre, "parameters": {"type": "object", "properties": {}}}}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """data/ temporal con prompt, playbook, tool generada y dos herramientas base de prueba."""
    data = tmp_path / "data"
    specs, generadas = data / "specs", data / "tools" / "generated"
    for carpeta in (data / "prompts", data / "playbooks", specs / "main", generadas):
        carpeta.mkdir(parents=True)
    (data / "prompts" / "gen_1.md").write_text("Eres un asesor.\n", encoding="utf-8")
    (data / "playbooks" / "escalado_innecesario_g1.md").write_text("No escales: usa las herramientas.\n",
                                                                     encoding="utf-8")
    (generadas / "duplicar.py").write_text(CODIGO_TOOL_GENERADA, encoding="utf-8")
    (generadas / "duplicar.json").write_text(json.dumps({"schema": esquema("duplicar")}), encoding="utf-8")

    monkeypatch.setattr(builder, "DATA", data)
    monkeypatch.setattr(builder, "SPECS", specs)
    monkeypatch.setattr(builder, "TOOLS_GENERADAS", generadas)
    monkeypatch.setattr(builder, "FUNCIONES", {"buscar_inventario": lambda: {"autos": []},
                                               "escalar_humano": lambda motivo: {"escalado": True}})
    monkeypatch.setattr(builder, "ESQUEMAS", {"buscar_inventario": esquema("buscar_inventario"),
                                              "escalar_humano": esquema("escalar_humano")})
    return SimpleNamespace(data=data, specs=specs)


def spec_de_prueba(**cambios) -> AgentSpec:
    valores = dict(generation=1, branch="main", parent="gen_0", system_prompt_path="prompts/gen_1.md",
                   topology="single_react", tools_enabled=["buscar_inventario", "duplicar"],
                   playbooks=["playbooks/escalado_innecesario_g1.md"])
    return AgentSpec(**(valores | cambios))


def test_guardar_y_cargar_spec(entorno):
    spec = spec_de_prueba()
    builder.save_spec(spec)
    assert builder.load_spec(1, "main") == spec
    assert builder.latest_generation("main") == 1
    assert builder.latest_generation("rama_vacia") == 0


def test_rama_derivada_hereda_las_generaciones_de_main(entorno):
    builder.save_spec(spec_de_prueba())
    assert builder.load_spec(1, "control").branch == "main"


def test_spec_inexistente_da_un_error_claro(entorno):
    with pytest.raises(FileNotFoundError, match="gen 7"):
        builder.load_spec(7, "main")


def test_instrucciones_pegan_los_playbooks_al_prompt(entorno):
    texto = builder.instrucciones(spec_de_prueba())
    assert texto == "Eres un asesor.\n\n## Procedimiento aprendido\nNo escales: usa las herramientas.\n"


def test_caja_de_herramientas_carga_base_y_generadas(entorno):
    herramientas = builder.caja_de_herramientas(spec_de_prueba())
    assert list(herramientas) == ["buscar_inventario", "duplicar"]
    assert herramientas["buscar_inventario"].generada is False
    assert herramientas["duplicar"].generada is True
    assert herramientas["duplicar"].funcion(numero=4) == {"resultado": 8}


def test_herramienta_inexistente_es_un_error(entorno):
    with pytest.raises(ValueError, match="tool_fantasma"):
        builder.caja_de_herramientas(spec_de_prueba(tools_enabled=["buscar_inventario", "tool_fantasma"]))


def test_topologia_supervisor_no_soportada(entorno):
    with pytest.raises(NotImplementedError, match="supervisor"):
        builder.build(spec_de_prueba(topology="supervisor"))


def test_build_arma_el_agente_de_la_spec(entorno, monkeypatch):
    opciones_recibidas: list[dict] = []

    def chat_falso(mensajes, **opciones):
        opciones_recibidas.append({"sistema": mensajes[0]["content"], **opciones})
        return SimpleNamespace(content="Sí, hay autos.", tool_calls=None), 5, 0.0

    monkeypatch.setattr(llm, "chat", chat_falso)
    ejecutar = builder.build(spec_de_prueba(), seed=2)
    resultado = ejecutar([{"role": "user", "content": "¿Hay autos?"}])

    assert resultado.final_answer == "Sí, hay autos."
    [opciones] = opciones_recibidas
    assert opciones["semilla"] == 2
    assert opciones["temperatura"] == builder.TEMPERATURA_EVALUACION
    assert "## Procedimiento aprendido" in opciones["sistema"]
    nombres_herramientas = [esquema_tool["function"]["name"] for esquema_tool in opciones["herramientas"]]
    assert nombres_herramientas == ["buscar_inventario", "duplicar"]


def test_spec_de_gen_0_es_valida():
    """La spec real de gen 0 se carga, usa el prompt escrito a mano y habilita las 8 herramientas base."""
    from core.contracts import BASE_TOOLS
    from core.paths import SPECS

    spec = AgentSpec.from_dict(json.loads((SPECS / "main" / "gen_0.json").read_text(encoding="utf-8")))
    assert (spec.generation, spec.parent, spec.topology) == (0, None, "single_react")
    assert spec.system_prompt_path == "prompts/gen_0.md"
    assert spec.tools_enabled == BASE_TOOLS
    assert spec.playbooks == []
