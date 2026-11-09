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

from core import archivos, proveedor_codex
from core.paths import ENV_FILE, SPEND

load_dotenv(ENV_FILE)

MODELO_AGENTE = os.getenv("MODEL_AGENT", "gpt-4.1-mini")  # el agente evaluado, el juez y el trato
MODELO_INTELIGENTE = os.getenv("MODEL_SMART", "gpt-4.1")  # destilador, síntesis de tools y meta-loop
PRESUPUESTO_USD = float(os.getenv("BUDGET_USD", "20"))
# "openai" (API de pago, por defecto) o "codex" (CLI oficial con una cuenta de ChatGPT: core/proveedor_codex.py)
PROVEEDOR = os.getenv("KAIZEN_PROVIDER", "openai").strip().lower()
# Con Codex no hay USD: el tope es de tokens. 0 = sin tope (no recomendado: los créditos de la cuenta se agotan)
PRESUPUESTO_TOKENS_CODEX = int(os.getenv("CODEX_MAX_TOKENS", "0"))
ARCHIVO_GASTO = SPEND  # contrato: {"usd": float}

# USD por millón de tokens (entrada, salida). PRICE_<MODELO>=entrada,salida[,cache] en .env sobrescribe o agrega.
PRECIOS_POR_MILLON = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
PRECIO_MODELO_DESCONOCIDO = (2.00, 8.00)  # se asume caro: subestimar el gasto es peor que sobreestimarlo
# Entrada en caché (USD por millón): OpenAI cobra menos el prefijo repetido del prompt (sistema + tools),
# que en el bucle ReAct se reenvía en cada paso. Fuente: developers.openai.com/api/docs/pricing
PRECIOS_CACHE_POR_MILLON = {
    "gpt-4.1-mini": 0.10,
    "gpt-4.1": 0.50,
    "gpt-4.1-nano": 0.025,
    "gpt-4o-mini": 0.075,
    "gpt-4o": 1.25,
}
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
    """Gasto acumulado entre corridas, guardado en spend.json.

    La fuente de verdad es el archivo, no la memoria: run.py y cada conversación de live.py son procesos
    distintos que gastan a la vez. Con un total en memoria por proceso, el último en escribir borraba lo que
    sumaron los demás (4 procesos que gastaron 2.00 USD dejaban registrado 0.50) y el tope no cortaba a tiempo.
    Por eso cada suma relee el archivo bajo un candado entre procesos.
    """

    def __init__(self) -> None:
        self._candado = threading.Lock()  # la evaluación corre episodios en varios hilos del mismo proceso

    @property
    def total_usd(self) -> float:
        """Gasto acumulado en spend.json; 0 si todavía no se ha gastado nada."""
        return float(archivos.leer_json(ARCHIVO_GASTO, {"usd": 0.0})["usd"])

    @property
    def tokens_codex(self) -> int:
        """Tokens gastados con el proveedor Codex (campo agregado a spend.json; 0 si nunca se usó)."""
        return int(archivos.leer_json(ARCHIVO_GASTO, {}).get("codex_tokens", 0))

    def sumar_tokens_codex(self, tokens: int) -> None:
        if tokens == 0:
            return
        with self._candado, archivos.candado_de_archivo(ARCHIVO_GASTO):
            datos = archivos.leer_json(ARCHIVO_GASTO, {"usd": 0.0})
            archivos.escribir_json(ARCHIVO_GASTO, {**datos, "codex_tokens": datos.get("codex_tokens", 0) + tokens})

    def sumar(self, costo_usd: float) -> None:
        """Suma el costo de una llamada al total guardado, sin perder lo que sumen otros procesos."""
        if costo_usd == 0:
            return
        with self._candado, archivos.candado_de_archivo(ARCHIVO_GASTO):
            # Sin redondeo: en miles de llamadas el error de redondear cada suma se acumularía
            datos = archivos.leer_json(ARCHIVO_GASTO, {"usd": 0.0})
            archivos.escribir_json(ARCHIVO_GASTO, {**datos, "usd": float(datos["usd"]) + costo_usd})


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
    precio_configurado = os.getenv(_variable_de_precio(modelo))
    if precio_configurado:
        entrada, salida = precio_configurado.split(",")[:2]
        return float(entrada), float(salida)
    return PRECIOS_POR_MILLON.get(modelo, PRECIO_MODELO_DESCONOCIDO)


def _variable_de_precio(modelo: str) -> str:
    return "PRICE_" + modelo.upper().replace("-", "_").replace(".", "_")


def precio_cache_por_millon(modelo: str) -> float:
    """USD por millón de tokens de entrada en caché. Sin dato, se cobra como entrada normal (no se subestima)."""
    if es_modelo_local():
        return 0.0
    partes = os.getenv(_variable_de_precio(modelo), "").split(",")
    if len(partes) == 3:
        return float(partes[2])
    return PRECIOS_CACHE_POR_MILLON.get(modelo, precio_por_millon(modelo)[0])


def tokens_en_cache(uso) -> int:
    """Tokens del prompt que vinieron de caché; 0 si la respuesta no lo informa (p. ej. un servidor local)."""
    detalle = getattr(uso, "prompt_tokens_details", None)
    return getattr(detalle, "cached_tokens", None) or 0


def costo_usd(modelo: str, uso) -> float:
    """`uso` es el objeto `usage` de la respuesta, con prompt_tokens, completion_tokens y, si hay caché,
    prompt_tokens_details.cached_tokens (incluidos en prompt_tokens, pero con otro precio)."""
    precio_entrada, precio_salida = precio_por_millon(modelo)
    en_cache = tokens_en_cache(uso)
    return ((uso.prompt_tokens - en_cache) * precio_entrada + en_cache * precio_cache_por_millon(modelo)
            + uso.completion_tokens * precio_salida) / TOKENS_POR_MILLON


def revisar_presupuesto() -> None:
    """Lanza BudgetExceeded si el gasto acumulado ya llegó a BUDGET_USD. Se llama antes de cada petición."""
    if CONTADOR_GASTO.total_usd >= PRESUPUESTO_USD:
        raise BudgetExceeded(f"Presupuesto agotado: {CONTADOR_GASTO.total_usd:.2f} / {PRESUPUESTO_USD:.2f} USD")
    if PROVEEDOR == "codex" and PRESUPUESTO_TOKENS_CODEX and CONTADOR_GASTO.tokens_codex >= PRESUPUESTO_TOKENS_CODEX:
        raise BudgetExceeded(f"Tope de tokens de Codex agotado: {CONTADOR_GASTO.tokens_codex:,} / {PRESUPUESTO_TOKENS_CODEX:,}")


def chat(mensajes: list[dict], modelo: str = MODELO_AGENTE, herramientas: list[dict] | None = None,
         temperatura: float = 0.0, semilla: int | None = None, modo_json: bool = False,
         timeout_s: float | None = None, max_tokens: int | None = None, reintentos: int = REINTENTOS):
    """Devuelve (mensaje, tokens, costo_usd). Reintenta los errores transitorios con backoff exponencial."""
    revisar_presupuesto()
    if PROVEEDOR == "codex":
        # Codex no admite temperatura, semilla ni max_tokens: se ignoran (más variación entre corridas)
        return _chat_codex(mensajes, modelo, herramientas, modo_json, reintentos)
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


def _chat_codex(mensajes: list[dict], modelo: str, herramientas: list[dict] | None, modo_json: bool,
                reintentos: int):
    """Misma interfaz que chat(), pero con la CLI de Codex. El costo en USD es 0; se cuentan tokens."""
    for intento in range(1, reintentos + 1):
        try:
            mensaje, tokens = proveedor_codex.chat(mensajes, modelo, herramientas, modo_json,
                                                   inteligente=modelo == MODELO_INTELIGENTE)
        except proveedor_codex.LimiteDeCodex as e:
            raise BudgetExceeded(f"Límite de uso de la cuenta de Codex: {e}") from e
        # Un intento de usar la terminal también se reintenta: en la evaluación suele ser casual. Si persiste
        # (p. ej. un mensaje malicioso en /live), sube el error y no se muestra nada de esa respuesta
        except (proveedor_codex.FalloTransitorio, proveedor_codex.HerramientaProhibida):
            if intento == reintentos:
                raise
            time.sleep(min(2 ** (intento - 1), ESPERA_MAXIMA_S))
            continue
        CONTADOR_GASTO.sumar_tokens_codex(tokens)
        return mensaje, tokens, 0.0
    raise ValueError(f"reintentos debe ser al menos 1 (se recibió {reintentos})")


def chat_json(sistema: str, usuario: str, modelo: str = MODELO_INTELIGENTE, temperatura: float = 0.2,
              **limites) -> tuple[dict, float]:
    """Devuelve (dict, costo_usd). `limites` acepta timeout_s, max_tokens y reintentos (ver chat)."""
    mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    mensaje, _tokens, costo = chat(mensajes, modelo=modelo, temperatura=temperatura, modo_json=True, **limites)
    return json.loads(mensaje.content or "{}"), costo
