"""Tests del proveedor Codex con un `codex` falso: no gastan créditos ni requieren la CLI instalada."""
from __future__ import annotations

import json
import stat
import sys

import pytest

from core import llm, proveedor_codex

HERRAMIENTAS = [{"type": "function", "function": {"name": "politica_garantia", "description": "Garantía de un auto",
                                                  "parameters": {"type": "object", "properties": {"auto_id": {"type": "string"}}}}}]
PREGUNTA = [{"role": "system", "content": "Eres un asistente de autos."},
            {"role": "user", "content": "¿Qué garantía tiene el A010?"}]

# Un ejecutable que imita a `codex exec --json`: el escenario lo decide la variable FALSO_ESCENARIO
CODEX_FALSO = r'''#!{python}
import json, os, sys, time
argv = sys.argv
salida = argv[argv.index("-o") + 1]
prompt = sys.stdin.read()
open(os.environ["FALSO_PROMPT"], "w", encoding="utf-8").write(prompt)
escenario = os.environ["FALSO_ESCENARIO"]
def evento(e): print(json.dumps(e), flush=True)
evento({{"type": "thread.started", "thread_id": "x"}})
if escenario == "terminal":
    evento({{"type": "item.started", "item": {{"type": "command_execution", "command": "cat ~/.codex/auth.json"}}}})
    time.sleep(2)  # si no lo matan, "ejecuta" el comando
    open(os.environ["FALSO_EJECUTO"], "w").write("sí")
    sys.exit(0)
if escenario == "limite":
    evento({{"type": "error", "message": "You've hit your usage limit. Try again later."}})
    sys.exit(1)
respuesta = {{
    "herramienta": {{"content": "", "tool_calls": [{{"name": "politica_garantia", "arguments": "{{\"auto_id\": \"A010\"}}"}}]}},
    "final": {{"content": "Sí, 12 meses.", "tool_calls": []}},
    "json": {{"json": "{{\"p_pasa\": 0.7}}"}},
}}[escenario]
evento({{"type": "item.completed", "item": {{"type": "agent_message", "text": json.dumps(respuesta)}}}})
evento({{"type": "turn.completed", "usage": {{"input_tokens": 15000, "cached_input_tokens": 14000, "output_tokens": 50}}}})
open(salida, "w", encoding="utf-8").write(json.dumps(respuesta))
'''


@pytest.fixture
def codex_falso(tmp_path, monkeypatch):
    """Instala el codex falso y devuelve una función para elegir el escenario."""
    binario = tmp_path / "codex"
    binario.write_text(CODEX_FALSO.format(python=sys.executable), encoding="utf-8")
    binario.chmod(binario.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(proveedor_codex, "CODEX_BIN", str(binario))
    monkeypatch.setattr(llm, "PROVEEDOR", "codex")
    monkeypatch.setattr(llm, "ARCHIVO_GASTO", tmp_path / "spend.json")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    monkeypatch.setenv("FALSO_PROMPT", str(tmp_path / "prompt.txt"))
    monkeypatch.setenv("FALSO_EJECUTO", str(tmp_path / "ejecuto.txt"))

    def usar(escenario: str):
        monkeypatch.setenv("FALSO_ESCENARIO", escenario)
        return tmp_path
    return usar


def test_pide_una_herramienta_con_la_forma_del_sdk(codex_falso):
    carpeta = codex_falso("herramienta")
    mensaje, tokens, costo = llm.chat(PREGUNTA, modelo="gpt-5.6-luna", herramientas=HERRAMIENTAS)
    [llamada] = mensaje.tool_calls
    assert (llamada.function.name, json.loads(llamada.function.arguments)) == ("politica_garantia", {"auto_id": "A010"})
    assert llamada.id.startswith("call_") and costo == 0.0 and tokens == 15_050
    prompt = (carpeta / "prompt.txt").read_text(encoding="utf-8")
    assert "politica_garantia" in prompt and "¿Qué garantía tiene el A010?" in prompt
    assert llm.CONTADOR_GASTO.tokens_codex == 15_050


def test_respuesta_final_sin_herramientas(codex_falso):
    codex_falso("final")
    mensaje, _, _ = llm.chat(PREGUNTA, herramientas=HERRAMIENTAS)
    assert mensaje.tool_calls is None and mensaje.content == "Sí, 12 meses."


def test_chat_json(codex_falso):
    codex_falso("json")
    datos, costo = llm.chat_json("Eres un juez.", "Califica.")
    assert datos == {"p_pasa": 0.7} and costo == 0.0


def test_intento_de_usar_la_terminal_se_corta_antes_de_ejecutar(codex_falso):
    carpeta = codex_falso("terminal")
    with pytest.raises(proveedor_codex.HerramientaProhibida):
        llm.chat(PREGUNTA, herramientas=HERRAMIENTAS, reintentos=2)
    assert not (carpeta / "ejecuto.txt").exists()  # el proceso murió antes de "ejecutar" el comando


def test_limite_de_la_cuenta_detiene_la_corrida(codex_falso):
    codex_falso("limite")
    with pytest.raises(llm.BudgetExceeded, match="usage limit"):
        llm.chat(PREGUNTA)


def test_tope_de_tokens(codex_falso, monkeypatch):
    codex_falso("final")
    monkeypatch.setattr(llm, "PRESUPUESTO_TOKENS_CODEX", 20_000)
    llm.chat(PREGUNTA)  # 15 050 tokens: todavía bajo el tope
    llm.chat(PREGUNTA)  # 30 100: lo cruza, pero ya se había autorizado
    with pytest.raises(llm.BudgetExceeded, match="tokens de Codex"):
        llm.chat(PREGUNTA)
