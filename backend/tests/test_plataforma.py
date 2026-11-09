"""Tests de la plataforma (llm, progress, archivos). No llaman a la API: el cliente se sustituye."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx2 as httpx  # openai 3.x usa httpx2
import openai
import pytest

from core import archivos, llm, paths, progress


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
    """Redirige spend.json, progress.json y registro.log a una carpeta temporal."""
    monkeypatch.setattr(paths, "SPEND", tmp_path / "spend.json")
    monkeypatch.setattr(paths, "PROGRESS", tmp_path / "progress.json")
    monkeypatch.setattr(paths, "REGISTRO", tmp_path / "registro.log")
    monkeypatch.setattr(llm, "CONTADOR", llm.Contador())
    monkeypatch.setattr(llm, "BASE_URL", None)
    monkeypatch.setattr(progress, "_estado", {"corriendo": False, "error": None, "lineas": []})
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    return tmp_path


def respuesta_falsa(contenido="hola", prompt_tokens=1_000, completion_tokens=500):
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens)
    mensaje = SimpleNamespace(content=contenido, tool_calls=None)
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=mensaje)])


def cliente_falso(monkeypatch, respuestas):
    """Cada llamada consume el siguiente elemento: una respuesta o una excepción que se lanza."""
    pendientes = list(respuestas)
    llamadas = []

    def create(**kwargs):
        llamadas.append(kwargs)
        siguiente = pendientes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    falso = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "cliente", lambda: falso)
    return llamadas


def error_de_conexion():
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))


# ---------- llm ----------

def test_chat_devuelve_mensaje_tokens_y_costo(datos_temporales, monkeypatch):
    cliente_falso(monkeypatch, [respuesta_falsa()])
    mensaje, tokens, usd = llm.chat([{"role": "user", "content": "hola"}], "gpt-4.1-mini")
    assert mensaje.content == "hola"
    assert tokens == 1_500
    assert usd == pytest.approx((1_000 * 0.40 + 500 * 1.60) / 1_000_000)
    assert json.loads((datos_temporales / "spend.json").read_text())["usd"] == pytest.approx(usd)


def test_chat_reintenta_errores_temporales(monkeypatch):
    llamadas = cliente_falso(monkeypatch, [error_de_conexion(), error_de_conexion(), respuesta_falsa()])
    mensaje, _, _ = llm.chat([{"role": "user", "content": "hola"}])
    assert mensaje.content == "hola"
    assert len(llamadas) == 3


def test_chat_se_rinde_tras_max_intentos(monkeypatch):
    cliente_falso(monkeypatch, [error_de_conexion()] * llm.MAX_INTENTOS)
    with pytest.raises(RuntimeError, match="no respondió"):
        llm.chat([{"role": "user", "content": "hola"}])


def test_chat_corta_al_llegar_al_presupuesto(monkeypatch):
    llamadas = cliente_falso(monkeypatch, [respuesta_falsa()])
    archivos.escribir_json(paths.SPEND, {"usd": llm.BUDGET_USD})
    with pytest.raises(llm.BudgetExceeded):
        llm.chat([{"role": "user", "content": "hola"}])
    assert llamadas == []  # no se gastó nada


def test_modelo_sin_precio_falla_antes_de_llamar(monkeypatch):
    llamadas = cliente_falso(monkeypatch, [respuesta_falsa()])
    with pytest.raises(ValueError, match="PRICE_MODELO_RARO"):
        llm.chat([{"role": "user", "content": "hola"}], "modelo-raro")
    assert llamadas == []


def test_precio_desde_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("PRICE_GPT_4_1_MINI", "1,2")
    assert llm.precio("gpt-4.1-mini") == (1.0, 2.0)


def test_servidor_local_no_cuesta(monkeypatch):
    monkeypatch.setattr(llm, "BASE_URL", "http://localhost:11434/v1")
    assert llm.es_local()
    assert llm.precio("cualquier-modelo") == (0.0, 0.0)


def test_chat_json_pide_formato_json(monkeypatch):
    llamadas = cliente_falso(monkeypatch, [respuesta_falsa('{"ok": true}')])
    datos, _ = llm.chat_json("sistema", "usuario")
    assert datos == {"ok": True}
    assert llamadas[0]["response_format"] == {"type": "json_object"}
    assert llamadas[0]["model"] == llm.MODEL_SMART


# ---------- progress ----------

def leer_progreso(carpeta):
    return json.loads((carpeta / "progress.json").read_text(encoding="utf-8"))


def test_progreso_de_una_semilla(datos_temporales):
    progress.iniciar(0, "smoke", 1, total=2)
    progress.tarea_hecha("coti_00", True)
    progress.tarea_hecha("gara_00", False, "garantia_mal_interpretada")
    estado = leer_progreso(datos_temporales)
    assert estado["corriendo"] is True
    assert (estado["hechas"], estado["aciertos"], estado["exito_parcial"]) == (2, 1, 0.5)
    assert "garantia_mal_interpretada" in estado["lineas"][-1]
    assert not (datos_temporales / "progress.json.tmp").exists()


def test_terminar_con_error_queda_visible(datos_temporales):
    progress.iniciar(1, "main", 1, total=10)
    progress.terminar("BudgetExceeded: tope")
    estado = leer_progreso(datos_temporales)
    assert estado["corriendo"] is False
    assert estado["error"] == "BudgetExceeded: tope"
    assert "BudgetExceeded" in (datos_temporales / "registro.log").read_text(encoding="utf-8")


def test_lineas_tienen_tope(datos_temporales):
    for i in range(progress.MAX_LINEAS + 20):
        progress.linea(f"línea {i}")
    assert len(leer_progreso(datos_temporales)["lineas"]) == progress.MAX_LINEAS


# ---------- archivos ----------

def test_escribir_json_conserva_acentos(tmp_path):
    destino = tmp_path / "x.json"
    archivos.escribir_json(destino, {"ciudad": "Mérida"})
    assert "Mérida" in destino.read_text(encoding="utf-8")
    assert archivos.leer_json(tmp_path / "no_existe.json", {"usd": 0.0}) == {"usd": 0.0}


def test_varios_procesos_no_pierden_gasto(datos_temporales):
    """run.py y varios live.py suman a la vez: ningún incremento se puede perder."""
    import subprocess
    import sys
    from pathlib import Path

    procesos, sumas, usd = 4, 50, 0.01
    script = (
        "import sys; from pathlib import Path; from core import llm, paths\n"
        "paths.SPEND = Path(sys.argv[1])\n"
        f"for _ in range({sumas}): llm.CONTADOR.sumar({usd})\n"
    )
    backend = Path(__file__).resolve().parent.parent
    hijos = [subprocess.Popen([sys.executable, "-c", script, str(datos_temporales / "spend.json")], cwd=backend)
             for _ in range(procesos)]
    assert all(h.wait(timeout=60) == 0 for h in hijos)
    assert llm.CONTADOR.total == pytest.approx(procesos * sumas * usd)


def test_escrituras_simultaneas_de_varios_procesos(tmp_path):
    """Varios procesos reescriben el mismo JSON: ninguno se cae y el archivo queda válido."""
    import subprocess
    import sys
    from pathlib import Path

    destino = tmp_path / "progress.json"
    script = ("import sys; from pathlib import Path; from core import archivos\n"
              "for i in range(100): archivos.escribir_json(Path(sys.argv[1]), {'i': i})\n")
    backend = Path(__file__).resolve().parent.parent
    hijos = [subprocess.Popen([sys.executable, "-c", script, str(destino)], cwd=backend) for _ in range(4)]
    assert all(h.wait(timeout=60) == 0 for h in hijos)
    assert json.loads(destino.read_text(encoding="utf-8")) == {"i": 99}
    assert list(tmp_path.glob("*.tmp")) == []
