"""ÚNICO cliente del modelo en KAIZEN: reintentos, costo por llamada y tope de presupuesto.

Nadie más importa openai para llamar al modelo; solo para capturar sus excepciones.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from functools import cache
from typing import Any

import openai
from dotenv import load_dotenv

from core import archivos, paths

load_dotenv(paths.ROOT / ".env")

MODEL_AGENT = os.getenv("MODEL_AGENT", "gpt-4.1-mini")  # agente evaluado
MODEL_SMART = os.getenv("MODEL_SMART", "gpt-4.1")  # destilador, síntesis de tools y meta-loop
BUDGET_USD = float(os.getenv("BUDGET_USD", "20"))
BASE_URL = os.getenv("OPENAI_BASE_URL") or None

# USD por millón de tokens (entrada, salida). Otros modelos: variable PRICE_<MODELO>=entrada,salida
PRECIOS: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}
TOKENS_POR_MILLON = 1_000_000

MAX_INTENTOS = 6  # esperas de 1, 2, 4, 8 y 16 s entre intentos: ~31 s antes de rendirse
TIMEOUT_NUBE_S = 60
TIMEOUT_LOCAL_S = 600  # un modelo local en una sola GPU puede tardar minutos por respuesta

# Errores temporales: vale la pena reintentar. APITimeoutError hereda de APIConnectionError
ERRORES_TEMPORALES = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)


class BudgetExceeded(RuntimeError):
    """Se alcanzó BUDGET_USD. run.py la traduce al código de salida 4."""


def es_local() -> bool:
    """True si OPENAI_BASE_URL apunta a esta máquina: entonces el costo es 0."""
    return bool(BASE_URL) and re.search(r"//(localhost|127\.0\.0\.1|0\.0\.0\.0)\b", BASE_URL) is not None


def precio(model: str) -> tuple[float, float]:
    """(entrada, salida) en USD por millón de tokens.

    Sin precio conocido se detiene antes de llamar: un costo inventado haría inútil el tope.
    """
    if es_local():
        return 0.0, 0.0
    variable = "PRICE_" + re.sub(r"[^A-Z0-9]", "_", model.upper())  # gpt-4.1-mini → PRICE_GPT_4_1_MINI
    valor = os.getenv(variable)
    if valor:
        entrada, salida = (float(x) for x in valor.split(","))
        return entrada, salida
    if model in PRECIOS:
        return PRECIOS[model]
    raise ValueError(f"No hay precio para '{model}'. Agrega {variable}=entrada,salida en backend/.env")


def costo(model: str, usage: Any) -> float:
    """Costo en USD de una respuesta según sus tokens. usage puede venir vacío en servidores locales."""
    if usage is None:
        return 0.0
    entrada, salida = precio(model)
    return (usage.prompt_tokens * entrada + usage.completion_tokens * salida) / TOKENS_POR_MILLON


class Contador:
    """Gasto acumulado entre corridas, guardado en data/runs/spend.json.

    La fuente de verdad es el archivo, no la memoria: run.py y cada conversación de live.py son procesos
    distintos que gastan a la vez. Por eso cada suma relee el archivo bajo un candado entre procesos;
    con un total en memoria por proceso, el último en escribir borraba lo que sumaron los demás.
    El candado de hilos evita esperas inútiles entre los hilos de evals.py del mismo proceso.
    """

    def __init__(self) -> None:
        self._candado_hilos = threading.Lock()

    @property
    def total(self) -> float:
        return float(archivos.leer_json(paths.SPEND, {"usd": 0.0})["usd"])

    def sumar(self, usd: float) -> None:
        if usd == 0:
            return
        with self._candado_hilos, archivos.candado_de_archivo(paths.SPEND):
            # Sin redondeo: en miles de llamadas el error de redondear cada suma se acumularía
            archivos.escribir_json(paths.SPEND, {"usd": self.total + usd})


CONTADOR = Contador()


@cache
def cliente() -> openai.OpenAI:
    """Cliente creado en la primera llamada, para que importar llm no exija la clave (p. ej. en pytest)."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Falta OPENAI_API_KEY en backend/.env (copia backend/.env.example)")
    # max_retries=0: los reintentos los hace chat(); si no, se multiplicarían con los del SDK
    return openai.OpenAI(base_url=BASE_URL, max_retries=0,
                         timeout=TIMEOUT_LOCAL_S if es_local() else TIMEOUT_NUBE_S)


def chat(messages: list[dict], model: str = MODEL_AGENT, tools: list[dict] | None = None,
         temperature: float = 0.0, seed: int | None = None,
         json_mode: bool = False) -> tuple[Any, int, float]:
    """Devuelve (mensaje, tokens totales, costo_usd).

    Lanza BudgetExceeded si ya se gastó BUDGET_USD y RuntimeError si la API no responde tras
    MAX_INTENTOS. Los errores que no son temporales (clave inválida, petición mal formada) suben tal cual.
    """
    if CONTADOR.total >= BUDGET_USD:
        raise BudgetExceeded(f"Se alcanzó el tope de {BUDGET_USD} USD (ver data/runs/spend.json)")
    precio(model)  # falla aquí, antes de gastar, si el modelo no tiene precio

    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
    if seed is not None:
        kwargs["seed"] = seed
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    for intento in range(MAX_INTENTOS):
        try:
            respuesta = cliente().chat.completions.create(**kwargs)
        except ERRORES_TEMPORALES:
            if intento == MAX_INTENTOS - 1:
                break
            time.sleep(2 ** intento)
            continue
        usd = costo(model, respuesta.usage)
        CONTADOR.sumar(usd)
        tokens = respuesta.usage.total_tokens if respuesta.usage else 0
        return respuesta.choices[0].message, tokens, usd
    raise RuntimeError(f"La API no respondió tras {MAX_INTENTOS} intentos")


def chat_json(system: str, user: str, model: str = MODEL_SMART,
              temperature: float = 0.2) -> tuple[dict, float]:
    """Devuelve (dict, costo_usd). Si el modelo no entrega JSON válido, lanza json.JSONDecodeError."""
    mensaje, _, usd = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                           model, temperature=temperature, json_mode=True)
    return json.loads(mensaje.content or "{}"), usd
