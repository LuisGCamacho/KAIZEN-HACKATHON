"""Juez LLM: opina qué tan probable es que una respuesta del agente sea correcta.

No decide la métrica oficial (eso lo hace env/verificador.py). Existe para medir si un juez de IA es confiable:
evaluation/evals.py calcula la correlación entre su p_pasa y el verificador, y el meta-juez reescribe su
rúbrica (data/meta/rubrica_vN.md) cuando discrepan.

El juez nunca recibe la respuesta esperada: solo la petición, los pasos con sus resultados y la respuesta final.
"""
from __future__ import annotations

import json

import openai

from core import llm
from core.contracts import Step
from core.paths import META

TEMPERATURA_JUEZ = 0.0  # la misma respuesta debe recibir la misma nota en cada corrida
MAX_TOKENS_JUEZ = 200  # la salida es un JSON de dos números: acota el costo si el modelo divaga
REINTENTOS_JUEZ = 2  # si el juez falla, la traza queda sin nota; no vale la pena insistir más
NOTA_MINIMA, NOTA_MAXIMA = 0.0, 1.0
SIN_HERRAMIENTAS = "(ninguna)"  # lo que ve el juez cuando el agente respondió sin consultar nada


def leer_rubrica(version: int) -> str:
    """Texto de la rúbrica vigente. El meta-juez escribe versiones nuevas (v1, v2...) a partir de la v0."""
    return (META / f"rubrica_v{version}.md").read_text(encoding="utf-8")


def describir_paso(paso: Step) -> str:
    """Una línea por herramienta: nombre(argumentos) -> resultado.

    El resultado ya es texto JSON; meterlo de nuevo en JSON lo llenaría de escapes difíciles de leer."""
    argumentos = json.dumps(paso.args, ensure_ascii=False)
    return f"- {paso.tool}({argumentos}) -> {paso.result_summary}"


def describir_episodio(peticion: str, pasos: list[Step], respuesta: str) -> str:
    """Lo único que ve el juez: la petición, cada herramienta con sus argumentos y resultado, y la respuesta."""
    herramientas = "\n".join(describir_paso(paso) for paso in pasos) or SIN_HERRAMIENTAS
    return (f"Petición del cliente:\n{peticion}\n\n"
            f"Herramientas usadas:\n{herramientas}\n\n"
            f"Respuesta final del agente:\n{respuesta}")


def acotar_nota(valor: object) -> float | None:
    """Convierte la nota del modelo a un número entre 0 y 1; None si no es un número."""
    try:
        nota = float(valor)
    except (TypeError, ValueError):
        return None
    return max(NOTA_MINIMA, min(NOTA_MAXIMA, nota))


def juzgar(peticion: str, pasos: list[Step], respuesta: str, version_rubrica: int) -> tuple[float | None, float | None, float]:
    """Devuelve (p_pasa, explicacion, costo_usd) según la rúbrica de esa versión.

    Si el modelo falla o no devuelve JSON válido, las notas quedan en None (nunca se inventan) y la evaluación
    sigue. BudgetExceeded sí se propaga: sin presupuesto hay que detener la corrida completa."""
    rubrica = leer_rubrica(version_rubrica)
    try:
        notas, costo = llm.chat_json(rubrica, describir_episodio(peticion, pasos, respuesta),
                                     modelo=llm.MODELO_AGENTE, temperatura=TEMPERATURA_JUEZ,
                                     max_tokens=MAX_TOKENS_JUEZ, reintentos=REINTENTOS_JUEZ)
    except (json.JSONDecodeError, openai.APIError):
        return None, None, 0.0
    return acotar_nota(notas.get("p_pasa")), acotar_nota(notas.get("explicacion")), costo
