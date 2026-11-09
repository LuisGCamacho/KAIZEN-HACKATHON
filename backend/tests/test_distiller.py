"""Tests del destilador con un modelo falso y carpetas temporales: no llaman a la API ni gastan presupuesto."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import artifacts, llm, paths
from core.contracts import AgentSpec, Step, Trace, Verdict
from improve import distiller

MARCADOR_HELDOUT = "PETICION_HELDOUT_SECRETA"


def traza(split: str, causa: str | None, prompt: str = "¿Qué autos me alcanzan?") -> Trace:
    pasos = [Step(agent="gen_0", tool="buscar_inventario", args={"ciudad": "GDL"}, result_summary='{"autos": []}')]
    return Trace(task_id="coti_10", family="cotizacion", generation=0, branch="main", seed=1, split=split,
                 prompt=prompt, expected={"ids": ["A001"]}, steps=pasos, final_answer="No sé.",
                 verdict=Verdict(passed=causa is None, reason=causa), tokens=10, cost_usd=0.0)


def trazas_de_prueba() -> list[Trace]:
    """5 fallos de train en 4 causas, 1 acierto de train y 2 fallos de held-out que el destilador no debe ver."""
    return [
        traza("train", "escalado_innecesario"), traza("train", "escalado_innecesario"),
        traza("train", "faltaron_opciones"), traza("train", "dias_incorrectos"),
        traza("train", "tramite_incompleto"), traza("train", None),
        traza("heldout", "escalado_innecesario", MARCADOR_HELDOUT),
        traza("heldout", "garantia_mal_interpretada", MARCADOR_HELDOUT),
    ]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """data/ temporal, modelo falso que registra todo lo que recibe y síntesis de tools configurable."""
    data = tmp_path / "data"
    carpetas = SimpleNamespace(prompts=data / "prompts", playbooks=data / "playbooks", meta=data / "meta")
    for carpeta in vars(carpetas).values():
        carpeta.mkdir(parents=True)
    (carpetas.prompts / "gen_0.md").write_text("Si dudas, escala a un humano.\n", encoding="utf-8")
    (carpetas.meta / "distiller_prompt_v0.md").write_text("Escribe un procedimiento.\n", encoding="utf-8")

    for nombre, valor in [("DATA", data), ("PROMPTS", carpetas.prompts), ("PLAYBOOKS", carpetas.playbooks)]:
        monkeypatch.setattr(distiller, nombre, valor)
    monkeypatch.setattr(paths, "META", carpetas.meta)  # core/versions.py lee el prompt del destilador desde aquí
    monkeypatch.setattr(distiller, "rel", lambda ruta: ruta.relative_to(data).as_posix())
    monkeypatch.setattr(artifacts, "REGISTRO", carpetas.meta / "artifacts.json")

    textos_enviados: list[str] = []

    def chat_falso(mensajes, **_opciones):
        textos_enviados.extend(mensaje["content"] for mensaje in mensajes)
        return SimpleNamespace(content="1. Usa las herramientas antes de escalar.", tool_calls=None), 10, 0.0

    def chat_json_falso(sistema, usuario, **_opciones):
        textos_enviados.extend([sistema, usuario])
        return {"prompt": "Resuelve con las herramientas; no escales.", "rationale": "Se quitó escalar (2 fallos)."}, 0.0

    monkeypatch.setattr(llm, "chat", chat_falso)
    monkeypatch.setattr(llm, "chat_json", chat_json_falso)
    sintesis = SimpleNamespace(resultado=None, llamadas=[])

    def sintetizar_falso(causa, ejemplos, cantidad, generacion, rama):
        sintesis.llamadas.append(causa)
        textos_enviados.append(ejemplos)
        return sintesis.resultado

    monkeypatch.setattr(distiller.tool_synth, "sintetizar", sintetizar_falso)
    return SimpleNamespace(carpetas=carpetas, textos_enviados=textos_enviados, sintesis=sintesis)


def spec_gen_0(**cambios) -> AgentSpec:
    valores = dict(generation=0, branch="main", parent=None, system_prompt_path="prompts/gen_0.md",
                   topology="single_react", tools_enabled=["buscar_inventario", "escalar_humano"])
    return AgentSpec(**(valores | cambios))


def test_fallos_de_train_excluye_heldout_y_aciertos():
    fallos = distiller.fallos_de_train(trazas_de_prueba())
    assert len(fallos) == 5
    assert all(fallo.split == "train" and not fallo.verdict.passed for fallo in fallos)


def test_el_destilador_nunca_ve_heldout(entorno):
    distiller.distill(spec_gen_0(), trazas_de_prueba(), "main", 0, 0, log=lambda _texto: None)
    assert entorno.textos_enviados, "el destilador debió consultar al modelo"
    assert not any(MARCADOR_HELDOUT in texto for texto in entorno.textos_enviados)


def test_produce_la_generacion_siguiente(entorno):
    spec = distiller.distill(spec_gen_0(), trazas_de_prueba(), "main", 0, 2, log=lambda _texto: None)

    assert (spec.generation, spec.branch, spec.parent) == (1, "main", "main/gen_0")
    assert spec.clusters == {"escalado_innecesario": 2, "faltaron_opciones": 1, "dias_incorrectos": 1,
                             "tramite_incompleto": 1}
    assert spec.rubric_version == 2
    assert spec.rationale == "Se quitó escalar (2 fallos)."
    assert spec.system_prompt_path == "prompts/gen_1.md"
    assert (entorno.carpetas.prompts / "gen_1.md").read_text(encoding="utf-8").startswith("Resuelve")
    # Solo las MAX_CAUSAS más frecuentes reciben playbook e intento de tool
    assert len(spec.playbooks) == distiller.MAX_CAUSAS
    assert spec.playbooks[0] == "playbooks/escalado_innecesario_g1.md"
    assert len(entorno.sintesis.llamadas) == distiller.MAX_CAUSAS
    assert spec.new_artifacts == spec.playbooks
    assert (spec.topology, spec.sub_agents) == ("single_react", [])


def test_registra_los_playbooks_como_artefactos(entorno):
    distiller.distill(spec_gen_0(), trazas_de_prueba(), "main", 0, 0, log=lambda _texto: None)
    [primero, *_resto] = artifacts.all_artifacts()
    assert primero["kind"] == "playbook"
    assert primero["origin"] == "escalado_innecesario"
    assert primero["origin_failures"] == 2
    assert primero["content"].startswith("1. Usa las herramientas")


def test_tool_aceptada_se_habilita_y_la_rechazada_no(entorno):
    entorno.sintesis.resultado = {"name": "filtrar_por_mensualidad", "accepted": True, "rejection": "",
                                  "path": "tools/generated/filtrar_por_mensualidad.py"}
    spec = distiller.distill(spec_gen_0(), trazas_de_prueba(), "main", 0, 0, log=lambda _texto: None)
    assert spec.tools_enabled.count("filtrar_por_mensualidad") == 1  # no se duplica aunque se acepte 3 veces
    assert "tools/generated/filtrar_por_mensualidad.py" in spec.new_artifacts

    entorno.sintesis.resultado = {"name": "tool_mala", "accepted": False, "rejection": "import prohibido: os",
                                  "path": "tools/rejected/tool_mala.py"}
    spec = distiller.distill(spec_gen_0(), trazas_de_prueba(), "main", 0, 0, log=lambda _texto: None)
    assert "tool_mala" not in spec.tools_enabled
    assert "tools/rejected/tool_mala.py" in spec.new_artifacts  # la rechazada queda como evidencia


def test_playbook_nuevo_reemplaza_al_heredado_de_la_misma_causa(entorno):
    padre = spec_gen_0(generation=1, playbooks=["playbooks/escalado_innecesario_g1.md",
                                                "playbooks/trampa_no_rechazada_g1.md"])
    spec = distiller.distill(padre, trazas_de_prueba(), "main", 0, 0, log=lambda _texto: None)
    assert "playbooks/escalado_innecesario_g1.md" not in spec.playbooks
    assert "playbooks/escalado_innecesario_g2.md" in spec.playbooks
    assert "playbooks/trampa_no_rechazada_g1.md" in spec.playbooks  # causa no destilada: se hereda


def test_otras_ramas_usan_sufijo(entorno):
    spec = distiller.distill(spec_gen_0(), trazas_de_prueba(), "smoke", 0, 0, log=lambda _texto: None)
    assert spec.system_prompt_path == "prompts/gen_1_smoke.md"
    assert spec.playbooks[0] == "playbooks/escalado_innecesario_g1_smoke.md"


def test_sin_fallos_no_gasta_en_el_modelo(entorno):
    sin_fallos = [traza("train", None), traza("heldout", "escalado_innecesario")]
    spec = distiller.distill(spec_gen_0(), sin_fallos, "main", 0, 0, log=lambda _texto: None)
    assert entorno.textos_enviados == []
    assert spec.system_prompt_path == "prompts/gen_0.md"
    assert spec.clusters == {}


@pytest.mark.parametrize("ruta, causa", [
    ("playbooks/garantia_mal_interpretada_g3.md", "garantia_mal_interpretada"),
    ("playbooks/dias_incorrectos_g2_smoke.md", "dias_incorrectos"),
    ("playbooks/sin_formato.md", None),
])
def test_causa_de_playbook(ruta, causa):
    assert distiller.causa_de_playbook(ruta) == causa


def test_prompt_v0_del_destilador_existe():
    from core.paths import META
    texto = (META / "distiller_prompt_v0.md").read_text(encoding="utf-8")
    assert "herramienta" in texto
