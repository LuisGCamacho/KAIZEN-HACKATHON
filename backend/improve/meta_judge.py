"""Meta-juez, nivel 2A de la auto-mejora: recalibra al juez LLM contra la verdad del verificador.

Compara la p_pasa del juez con el resultado del verificador en cada traza. Si hay suficientes casos donde el
juez se equivocó por mucho, le muestra esos casos al modelo y escribe una rúbrica nueva (rubrica_vN.md).
La generación siguiente se juzga con esa versión.

Solo mira trazas de train, igual que el destilador: si la rúbrica aprendiera de held-out, la correlación
del juez medida en held-out quedaría inflada.
"""
from __future__ import annotations

import json
import statistics
from typing import Callable

from core import llm, versions
from core.contracts import Trace

UMBRAL_DISCREPANCIA = 0.5  # el juez "se equivocó" si su p_pasa se aleja más que esto de la verdad (0 o 1)
MIN_DISCREPANCIAS = 3  # con menos casos no hay evidencia suficiente para reescribir la rúbrica
MAX_CASOS_AL_MODELO = 10
MAX_CARACTERES_RESPUESTA_CASO = 400
MIN_PARES_CORRELACION = 3
SPLIT_ENTRENAMIENTO = "train"
CAMPOS_OBLIGATORIOS = ('"p_pasa"', '"explicacion"')  # judge.py lee exactamente estos campos del JSON del juez

SISTEMA = """Eres el calibrador del juez de un sistema de agentes de una agencia de autos seminuevos.
El juez estima p_pasa sin ver la respuesta correcta; el verificador programático dice la verdad.
Te doy la rúbrica actual del juez y casos donde el juez se equivocó por más de 0.5.
Reescribe la rúbrica para que el juez detecte esos errores: por ejemplo, qué evidencia de las herramientas debe revisar.
Sé general: no menciones IDs de autos ni de tareas.
Conserva el formato de salida: JSON con los campos numéricos "p_pasa" y "explicacion", ambos de 0 a 1.
Devuelve JSON: {"rubrica": "<rúbrica completa nueva>", "cambio": "<una frase: qué cambiaste y por qué>"}"""

Registro = Callable[[str], None]


def trazas_de_train(trazas: list[Trace]) -> list[Trace]:
    """Solo las trazas del split de entrenamiento, con o sin acierto."""
    return [traza for traza in trazas if traza.split == SPLIT_ENTRENAMIENTO]


def correlacion_juez(trazas: list[Trace]) -> float | None:
    """Pearson entre la p_pasa del juez y el resultado del verificador (1 = pasó, 0 = falló).

    None si hay muy pocas notas o si alguno de los dos no varía (la correlación no está definida)."""
    pares = [(traza.verdict.judge_p_pass, float(traza.verdict.passed)) for traza in trazas
             if traza.verdict.judge_p_pass is not None]
    if len(pares) < MIN_PARES_CORRELACION:
        return None
    notas_juez, verdades = zip(*pares)
    if len(set(notas_juez)) < 2 or len(set(verdades)) < 2:
        return None
    return round(statistics.correlation(notas_juez, verdades), 4)


def discrepancias(trazas: list[Trace]) -> list[Trace]:
    """Trazas donde el juez se alejó de la verdad por más de UMBRAL_DISCREPANCIA."""
    return [traza for traza in trazas if traza.verdict.judge_p_pass is not None
            and abs(traza.verdict.judge_p_pass - float(traza.verdict.passed)) > UMBRAL_DISCREPANCIA]


def describir_casos(trazas: list[Trace]) -> str:
    """Casos en JSON para el modelo: lo que vio el juez, lo que opinó y lo que era verdad."""
    casos = []
    for traza in trazas[:MAX_CASOS_AL_MODELO]:
        casos.append(json.dumps({
            "peticion": traza.prompt,
            "pasos": [{"tool": paso.tool, "resultado": paso.result_summary} for paso in traza.steps],
            "respuesta": traza.final_answer[:MAX_CARACTERES_RESPUESTA_CASO],
            "p_pasa_del_juez": traza.verdict.judge_p_pass,
            "verdad": traza.verdict.passed,
            "causa_real": traza.verdict.reason,
        }, ensure_ascii=False))
    return "\n\n".join(casos)


def rubrica_valida(rubrica: str) -> bool:
    """La rúbrica nueva debe seguir pidiendo los dos campos que judge.py lee; si no, el juez dejaría de dar notas."""
    return bool(rubrica.strip()) and all(campo in rubrica for campo in CAMPOS_OBLIGATORIOS)


def calibrar(trazas: list[Trace], version_rubrica: int, generacion: int, branch: str,
             log: Registro = print) -> int:
    """Devuelve la versión de rúbrica que usará la generación `generacion`.

    Conserva `version_rubrica` si hay menos de MIN_DISCREPANCIAS casos o si el modelo no devuelve una rúbrica
    válida. Si no, guarda la rúbrica nueva con versions.guardar y devuelve su número."""
    entrenamiento = trazas_de_train(trazas)
    correlacion = correlacion_juez(entrenamiento)
    casos = discrepancias(entrenamiento)
    log(f"meta-juez: correlación {correlacion}, {len(casos)} discrepancias en train")
    if len(casos) < MIN_DISCREPANCIAS:
        return version_rubrica

    rubrica_actual = versions.texto("rubrica", version_rubrica)
    pedido = f"Rúbrica actual:\n{rubrica_actual}\n\nCasos donde el juez se equivocó:\n{describir_casos(casos)}"
    respuesta, _costo = llm.chat_json(SISTEMA, pedido)
    rubrica_nueva = str(respuesta.get("rubrica") or "").strip()
    if not rubrica_valida(rubrica_nueva):
        log("meta-juez: el modelo no devolvió una rúbrica válida, se conserva la actual")
        return version_rubrica

    version_nueva = versions.guardar("rubrica", rubrica_nueva + "\n", generacion, branch,
                                     change=str(respuesta.get("cambio") or ""), correlation_before=correlacion,
                                     discrepancies=len(casos))
    log(f"meta-juez: rúbrica v{version_nueva}")
    return version_nueva
