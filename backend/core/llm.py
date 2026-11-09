"""Único cliente del modelo de lenguaje en KAIZEN.

Centraliza lo que ningún otro módulo debe repetir:
- reintentos ante errores transitorios de la API,
- costo de cada llamada y gasto acumulado en data/runs/spend.json,
- corte por presupuesto (BUDGET_USD) antes de gastar más.

Ningún otro módulo llama a `openai` directamente (ver backend/AGENTS.md)."""
from __future__ import annotations

import json
import os
import threading
import time

import openai
from dotenv import load_dotenv

from core.paths import ENV_FILE, RUNS

load_dotenv(ENV_FILE)

MODELO_AGENTE = os.getenv("MODEL_AGENT", "gpt-4.1-mini")  # el agente evaluado, el juez y el trato
MODELO_INTELIGENTE = os.getenv("MODEL_SMART", "gpt-4.1")  # destilador, síntesis de tools y meta-loop
PRESUPUESTO_USD = float(os.getenv("BUDGET_USD", "20"))
ARCHIVO_GASTO = RUNS / "spend.json"  # contrato: {"usd": float}

# USD por millón de tokens (entrada, salida). PRICE_<MODELO>=entrada,salida en .env sobrescribe o agrega.
PRECIOS_POR_MILLON = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
PRECIO_MODELO_DESCONOCIDO = (2.00, 8.00)  # se asume caro: subestimar el gasto es peor que sobreestimarlo
TOKENS_POR_MILLON = 1_000_000

HOSTS_LOCALES = ("localhost", "127.0.0.1")
TIMEOUT_API_S = 90
TIMEOUT_LOCAL_S = 600  # un modelo local en una sola GPU puede tardar minutos por respuesta
REINTENTOS = 6
ESPERA_MAXIMA_S = 30  # backoff exponencial: 1, 2, 4, 8, 16 s, con tope en este valor
ERRORES_TRANSITORIOS = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                        openai.InternalServerError)


class BudgetExceeded(RuntimeError):
    """Se alcanzó BUDGET_USD. El nombre es parte del contrato: live.py lo muestra como evento `error`."""


class _ContadorGasto:
    """Gasto acumulado entre corridas. Es seguro entre hilos porque la evaluación corre episodios en paralelo."""

    def __init__(self) -> None:
        """Arranca desde el gasto guardado, para que el presupuesto cuente todas las corridas, no solo esta."""
        self._candado = threading.Lock()
        self.total_usd = self._leer_total()

    @staticmethod
    def _leer_total() -> float:
        """Gasto acumulado en spend.json; 0 si todavía no se ha gastado nada."""
        if not ARCHIVO_GASTO.exists():
            return 0.0
        return float(json.loads(ARCHIVO_GASTO.read_text(encoding="utf-8"))["usd"])

    def sumar(self, costo_usd: float) -> None:
        """Suma el costo de una llamada al total y lo guarda en spend.json."""
        with self._candado:
            self.total_usd += costo_usd
            # Escritura atómica: un corte a mitad de escritura no deja el archivo ilegible
            temporal = ARCHIVO_GASTO.with_suffix(".json.tmp")
            temporal.write_text(json.dumps({"usd": round(self.total_usd, 6)}), encoding="utf-8")
            temporal.replace(ARCHIVO_GASTO)


CONTADOR_GASTO = _ContadorGasto()
_cliente: openai.OpenAI | None = None


def es_modelo_local() -> bool:
    """True si OPENAI_BASE_URL apunta a esta máquina (por ejemplo, Ollama): entonces no cuesta y tarda más."""
    url_base = os.getenv("OPENAI_BASE_URL", "")
    return any(host in url_base for host in HOSTS_LOCALES)


def _obtener_cliente() -> openai.OpenAI:
    """Crea el cliente de OpenAI la primera vez que se usa y lo reutiliza después.

    Se crea tarde a propósito: así los tests y los comandos sin LLM (export, reset) no exigen la API key."""
    global _cliente
    if _cliente is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Falta OPENAI_API_KEY en backend/.env (copia .env.example)")
        timeout_s = TIMEOUT_LOCAL_S if es_modelo_local() else TIMEOUT_API_S
        _cliente = openai.OpenAI(max_retries=0, timeout=timeout_s)  # los reintentos los maneja chat()
    return _cliente


def precio_por_millon(modelo: str) -> tuple[float, float]:
    """(entrada, salida) en USD por millón de tokens. Un modelo local no cuesta."""
    if es_modelo_local():
        return 0.0, 0.0
    variable = "PRICE_" + modelo.upper().replace("-", "_").replace(".", "_")
    precio_configurado = os.getenv(variable)
    if precio_configurado:
        entrada, salida = precio_configurado.split(",")
        return float(entrada), float(salida)
    return PRECIOS_POR_MILLON.get(modelo, PRECIO_MODELO_DESCONOCIDO)


def costo_usd(modelo: str, uso) -> float:
    """`uso` es el objeto `usage` de la respuesta, con prompt_tokens y completion_tokens."""
    precio_entrada, precio_salida = precio_por_millon(modelo)
    return (uso.prompt_tokens * precio_entrada + uso.completion_tokens * precio_salida) / TOKENS_POR_MILLON


def revisar_presupuesto() -> None:
    """Lanza BudgetExceeded si el gasto acumulado ya llegó a BUDGET_USD. Se llama antes de cada petición."""
    if CONTADOR_GASTO.total_usd >= PRESUPUESTO_USD:
        raise BudgetExceeded(f"Presupuesto agotado: {CONTADOR_GASTO.total_usd:.2f} / {PRESUPUESTO_USD:.2f} USD")


def chat(mensajes: list[dict], modelo: str = MODELO_AGENTE, herramientas: list[dict] | None = None,
         temperatura: float = 0.0, semilla: int | None = None, modo_json: bool = False,
         timeout_s: float | None = None, max_tokens: int | None = None, reintentos: int = REINTENTOS):
    """Devuelve (mensaje, tokens, costo_usd). Reintenta los errores transitorios con backoff exponencial."""
    revisar_presupuesto()
    parametros: dict = {"model": modelo, "messages": mensajes, "temperature": temperatura}
    if herramientas:
        parametros["tools"] = herramientas
    if semilla is not None:
        parametros["seed"] = semilla
    if modo_json:
        parametros["response_format"] = {"type": "json_object"}
    if timeout_s:
        parametros["timeout"] = timeout_s
    if max_tokens:
        parametros["max_tokens"] = max_tokens

    for intento in range(1, reintentos + 1):
        try:
            respuesta = _obtener_cliente().chat.completions.create(**parametros)
        except ERRORES_TRANSITORIOS:
            if intento == reintentos:
                raise
            time.sleep(min(2 ** (intento - 1), ESPERA_MAXIMA_S))
            continue
        costo = costo_usd(modelo, respuesta.usage)
        CONTADOR_GASTO.sumar(costo)
        return respuesta.choices[0].message, respuesta.usage.total_tokens, costo
    raise ValueError(f"reintentos debe ser al menos 1 (se recibió {reintentos})")


def chat_json(sistema: str, usuario: str, modelo: str = MODELO_INTELIGENTE, temperatura: float = 0.2,
              **limites) -> tuple[dict, float]:
    """Devuelve (dict, costo_usd). `limites` acepta timeout_s, max_tokens y reintentos (ver chat)."""
    mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    mensaje, _tokens, costo = chat(mensajes, modelo=modelo, temperatura=temperatura, modo_json=True, **limites)
    return json.loads(mensaje.content or "{}"), costo
