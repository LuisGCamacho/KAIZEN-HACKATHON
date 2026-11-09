"""Tests de almacen, artifacts, versions, export, reset y run.py.

Los módulos de Backend A (env, evals, history) y de la IA Engineer (improve) se sustituyen por
dobles mínimos, así estos tests no dependen de que existan ni llaman al LLM.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from types import ModuleType

import pytest

import run
from core import almacen, archivos, artifacts, llm, paths, versions
from core import reset as reset_mod
from core.contracts import BASE_TOOLS, AgentSpec, Artifact, GenerationReport, Trace, Verdict
from evaluation import export

ARCHIVOS_WEB = ("reports.json", "clusters.json", "artifacts.json", "lineage.json", "traces.json", "progress.json")
TAREAS = [{"id": f"{p}_{n:02d}", "family": f, "split": "heldout" if n < 8 else "train", "prompt": f"¿{p} {n}?",
           "expected": {}, "key_tools": []}
          for f, p in (("cotizacion", "coti"), ("garantia", "gara"), ("logistica", "logi"),
                       ("tramite", "trmt"), ("trampa", "trap"))
          for n in range(24)]


# ---------- dobles de los módulos de otros roles ----------

def traza(spec: AgentSpec, tarea: dict, semilla: int) -> Trace:
    """Cada generación aprueba más en train y en held-out: gen N aprueba (número % 8) < 2 + 2N."""
    aprobada = int(tarea["id"][-2:]) % 8 < 2 + 2 * spec.generation
    return Trace(tarea["id"], tarea["family"], spec.generation, spec.branch, semilla, tarea["split"],
                 tarea["prompt"], {}, [], "sí", Verdict(aprobada, None if aprobada else "escalado_innecesario"),
                 100, 0.001)


def sustituir_modulo(monkeypatch, nombre: str, modulo: ModuleType) -> None:
    """Cambia paquete.modulo en sys.modules y en el paquete: si el paquete real ya se importó,
    `from paquete import modulo` lee su atributo y no pasaría por sys.modules."""
    monkeypatch.setitem(sys.modules, nombre, modulo)
    paquete, _, hijo = nombre.rpartition(".")
    monkeypatch.setattr(importlib.import_module(paquete), hijo, modulo, raising=False)


def instalar_dobles(monkeypatch) -> dict[str, list]:
    llamadas: dict[str, list] = {"meta_destilador": [], "destilar": []}

    def run_generation(spec, semilla, tareas=None):
        trazas = [traza(spec, t, semilla) for t in (tareas or TAREAS)]
        carpeta = paths.RUNS / spec.branch / f"gen_{spec.generation}"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"seed_{semilla}.jsonl").write_text(
            "\n".join(json.dumps(t.to_dict(), ensure_ascii=False) for t in trazas), encoding="utf-8")
        return trazas

    def report(spec, semilla, trazas):
        def exito(split):
            del_split = [t for t in trazas if t.split == split]
            return sum(t.verdict.passed for t in del_split) / max(len(del_split), 1)
        return GenerationReport(spec.generation, spec.branch, semilla, exito("train"), exito("heldout"),
                                3.0, 1.0, None, 0, 100, 0.01, None, 0.0, [])

    def save_reports(branch, reportes):
        ruta = almacen.ruta_reportes(branch)
        nuevas = {(r.generation, r.seed) for r in reportes}
        viejos = [r for r in archivos.leer_json(ruta, []) if (r["generation"], r["seed"]) not in nuevas]
        archivos.escribir_json(ruta, viejos + [r.to_dict() for r in reportes])

    def distill(padre, trazas, branch, version_destilador, version_rubrica, log=print):
        llamadas["destilar"].append((padre.generation, branch, version_destilador))
        g = padre.generation + 1
        playbook = f"playbooks/escalado_innecesario_g{g}.md"
        (paths.DATA / playbook).write_text("No escales.", encoding="utf-8")
        artifacts.add(Artifact(f"pb_g{g}", "playbook", g, branch, "escalado_innecesario", 3, True, playbook).to_dict())
        return AgentSpec(g, branch, f"{padre.branch}/gen_{padre.generation}", run.PROMPT_GEN0, "single_react",
                         list(BASE_TOOLS), [playbook], [], version_destilador, version_rubrica,
                         "menos escalados", {"escalado_innecesario": 3}, [f"pb_g{g}"])

    def quizas_reescribir(deltas, version, generacion, branch, log=print):
        llamadas["meta_destilador"].append(branch)
        return version

    modulos = {
        "env.tareas": {"TAREAS": TAREAS},
        "evaluation.evals": {"run_generation": run_generation, "report": report},
        "evaluation.history": {"save_reports": save_reports},
        "improve.distiller": {"distill": distill},
        "improve.meta_judge": {"calibrar": lambda trazas, version, generacion, branch, log=print: version},
        "improve.meta_distiller": {"quizas_reescribir": quizas_reescribir},
    }
    for nombre, atributos in modulos.items():
        modulo = ModuleType(nombre)
        modulo.__dict__.update(atributos)
        sustituir_modulo(monkeypatch, nombre, modulo)
    (paths.PROMPTS / "gen_0.md").write_text("Eres un asistente.", encoding="utf-8")
    return llamadas


def leer_web(nombre: str):
    return json.loads((paths.WEB_DATA / nombre).read_text(encoding="utf-8"))


# ---------- export ----------

def test_export_sin_datos_deja_seis_json_validos(datos):
    assert export.export_all() == []
    for nombre in ARCHIVOS_WEB:
        assert (paths.WEB_DATA / nombre).exists(), nombre
    assert leer_web("reports.json") == {"branches": [], "generations": [], "seeds": [], "spend_usd": 0.0}
    assert leer_web("traces.json")["after"] is None


def test_export_si_una_seccion_falla_conserva_las_demas(datos, monkeypatch):
    monkeypatch.setitem(export.SECCIONES, "clusters.json", lambda: 1 / 0)
    errores = export.export_all(log=lambda _t: None)
    assert len(errores) == 1 and "clusters.json" in errores[0]
    assert (paths.WEB_DATA / "reports.json").exists()


# ---------- run.py de punta a punta con dobles ----------

def test_smoke_produce_gen0_gen1_y_los_json(datos, monkeypatch):
    instalar_dobles(monkeypatch)
    assert run.main(["smoke"]) == run.SALIDA_OK
    assert almacen.generaciones("smoke") == [0, 1]
    assert len(almacen.cargar_trazas("smoke", 1)) == 10  # 2 tareas por familia
    reportes = leer_web("reports.json")
    assert [g["generation"] for g in reportes["generations"]] == [0, 1]
    assert reportes["generations"][1]["new_artifacts"] == ["pb_g1"]
    assert leer_web("traces.json")["after"] == 1
    assert leer_web("lineage.json")["branches"]["smoke"][1]["playbook_texts"]
    assert leer_web("artifacts.json")[0]["content"] == "No escales."
    assert leer_web("progress.json")["corriendo"] is False
    assert not paths.LOCK.exists()


def test_loop_y_rama_control(datos, monkeypatch):
    llamadas = instalar_dobles(monkeypatch)
    assert run.main(["loop", "--until", "3", "--seeds", "1,2"]) == run.SALIDA_OK
    filas = export.filas_de_rama("main")
    assert [f["generation"] for f in filas] == [0, 1, 2, 3]
    assert filas[1]["delta"] > 0 and filas[0]["seeds"] == 2

    assert run.main(["next", "--branch", "control", "--fork-from", "2", "--no-meta-distiller", "--seeds", "1"]) == 0
    assert almacen.generaciones("control") == [0, 1, 2, 3]  # 0-2 heredadas de main, 3 propia
    assert llamadas["destilar"][-1] == (2, "control", 0)  # destila desde main/gen_2
    assert "control" not in llamadas["meta_destilador"]
    assert not (paths.SPECS / "control" / "gen_2.json").exists()  # no copia datos de main


def test_next_reanuda_una_generacion_sin_evaluar(datos, monkeypatch):
    llamadas = instalar_dobles(monkeypatch)
    run.main(["gen0", "--seeds", "1"])
    almacen.guardar_spec(AgentSpec(1, "main", "main/gen_0", run.PROMPT_GEN0, "single_react", list(BASE_TOOLS)))
    assert run.main(["next", "--seeds", "1"]) == 0
    assert llamadas["destilar"] == []  # no volvió a destilar: solo evaluó gen 1
    assert almacen.semillas("main", 1) == [1]


# ---------- lock y códigos de salida ----------

def test_lock_de_proceso_vivo_devuelve_3(datos, monkeypatch):
    instalar_dobles(monkeypatch)
    paths.LOCK.write_text(str(os.getppid()), encoding="utf-8")  # el proceso padre sigue vivo
    assert run.main(["gen0"]) == run.SALIDA_OCUPADO
    assert paths.LOCK.exists()  # no borra el lock ajeno


def test_lock_huerfano_se_reemplaza(datos, monkeypatch):
    instalar_dobles(monkeypatch)
    monkeypatch.setattr(run, "proceso_vivo", lambda _pid: False)
    paths.LOCK.write_text("999999", encoding="utf-8")
    assert run.main(["gen0", "--seeds", "1"]) == run.SALIDA_OK
    assert not paths.LOCK.exists()


def test_presupuesto_agotado_devuelve_4_y_se_ve_en_la_web(datos, monkeypatch):
    instalar_dobles(monkeypatch)

    def sin_presupuesto(*_args, **_kwargs):
        raise llm.BudgetExceeded("tope")
    monkeypatch.setattr(sys.modules["evaluation.evals"], "run_generation", sin_presupuesto)
    assert run.main(["gen0"]) == run.SALIDA_PRESUPUESTO
    assert "BudgetExceeded" in leer_web("progress.json")["error"]
    assert not paths.LOCK.exists()


def test_fork_from_solo_con_control():
    with pytest.raises(SystemExit):
        run.argumentos(["next", "--fork-from", "2"])


# ---------- versions y artifacts ----------

def test_versions_guarda_e_historial(datos):
    versions.ruta("rubrica", 0).write_text("v0", encoding="utf-8")
    assert versions.guardar("rubrica", "v1", 2, "main", diagnosis="juez blando") == 1
    assert versions.ultima("rubrica") == 1
    assert versions.historial("rubrica")[0]["diagnosis"] == "juez blando"
    rubricas = export.lineage()["rubric"]
    assert [(r["version"], r["parent_text"]) for r in rubricas] == [(0, ""), (1, "v0")]


def test_artifacts_sin_duplicados(datos):
    a = Artifact("t", "tool", 1, "main", "dias_incorrectos", 2, False, "tools/rejected/t.py")
    artifacts.add(a.to_dict())
    artifacts.add({**a.to_dict(), "accepted": True, "code": "def t(): ..."})
    assert [x.accepted for x in artifacts.listar()] == [True]


# ---------- reset ----------

def test_reset_deja_solo_gen0(datos, monkeypatch):
    instalar_dobles(monkeypatch)
    run.main(["loop", "--until", "2", "--seeds", "1"])
    versions.guardar("distiller_prompt", "v1", 2, "main")
    previsto = reset_mod.plan()
    assert (paths.SPECS / "main" / "gen_1.json") in previsto
    assert (paths.SPECS / "main" / "gen_1.json").exists()  # plan no borra

    assert run.main(["reset"]) == run.SALIDA_OK
    assert almacen.generaciones("main") == [0]
    assert {r.generation for r in almacen.cargar_reportes("main")} == {0}
    assert artifacts.listar() == []
    assert versions.ultima("distiller_prompt") == 0
    assert (paths.PROMPTS / "gen_0.md").exists()
    assert list(paths.PLAYBOOKS.iterdir()) == []


def test_lock_es_atomico(datos, monkeypatch):
    """Si otro proceso crea el lock entre la revisión y la escritura, este no lo pisa."""
    original = run.os.open

    def otro_proceso_gana(ruta, banderas, *args):
        paths.LOCK.write_text("1", encoding="utf-8")
        return original(ruta, banderas, *args)
    monkeypatch.setattr(run.os, "open", otro_proceso_gana)
    with pytest.raises(run.CorridaOcupada):
        run.tomar_lock()
    assert paths.LOCK.read_text(encoding="utf-8") == "1"
