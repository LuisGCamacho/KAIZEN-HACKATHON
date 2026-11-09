"""Verificador programático: la métrica oficial. Binario, determinista y sin LLM.

Lee el texto de la respuesta final y lo compara con `expected` (calculado con las tools en
env/tareas.py). Cuando falla devuelve una etiqueta de REASONS: es lo que el destilador agrupa y lo
que muestra la vista Autopsia. El juez LLM nunca decide `passed`.
"""
from __future__ import annotations

import re

from core.contracts import REASONS, Task, Verdict
from env.inventario import sin_acentos

__all__ = ["REASONS", "verificar"]

PATRON_ID = re.compile(r"\bA\d{3}\b")
PATRON_DIAS = re.compile(r"\b(\d{1,3})\s*dias?\b")  # sobre texto sin acentos: "3 días hábiles"
PATRON_FOLIO = re.compile(r"\bINS-[A-Z0-9-]+", re.IGNORECASE)
PATRON_PRIMERA_PALABRA = re.compile(r"[^a-z]*([a-z]+)")  # salta "¡", "**" y espacios
AFIRMACIONES, NEGACIONES = {"si"}, {"no"}
# Frases con las que el agente rechaza una petición imposible (texto sin acentos)
FRASES_RECHAZO = ("no existe", "no tenemos", "no contamos", "no hay", "no es posible", "no podemos",
                  "no se puede", "no manejamos", "no esta disponible", "no encontr", "imposible",
                  "no ofrecemos", "no llegamos", "sin cobertura", "sin sucursal", "no alcanza",
                  "lo siento", "lamentablemente", "ningun auto", "ningun vehiculo", "ninguno cumple",
                  "ninguno se ajusta", "no cumple")
# Frases que contienen una de las de arriba pero no rechazan nada: se quitan antes de buscar
FRASES_NO_RECHAZO = ("no hay problema", "no hay inconveniente", "no te preocupes", "no se preocupe",
                     "ningun problema", "ningun inconveniente")


# ---------------------------------------------------------------------------
# Lectura del texto
# ---------------------------------------------------------------------------
def leer_si_no(respuesta: str) -> bool | None:
    """True si la primera palabra es "sí", False si es "no" y None si no empieza con ninguna."""
    coincidencia = PATRON_PRIMERA_PALABRA.match(sin_acentos(respuesta))
    if coincidencia is None:
        return None
    palabra = coincidencia.group(1)
    if palabra in AFIRMACIONES:
        return True
    if palabra in NEGACIONES:
        return False
    return None


def leer_dias(respuesta: str) -> set[int]:
    """Todos los números de 1 a 3 dígitos seguidos de "día" o "días"."""
    return {int(n) for n in PATRON_DIAS.findall(sin_acentos(respuesta))}


def rechaza(respuesta: str) -> bool:
    """True si empieza con "no" o usa una frase de rechazo. "No hay problema, te lo aparto" no cuenta."""
    texto = sin_acentos(respuesta)
    for frase in FRASES_NO_RECHAZO:
        texto = texto.replace(frase, "")
    if leer_si_no(texto) is False:
        return True
    return any(frase in texto for frase in FRASES_RECHAZO)


# ---------------------------------------------------------------------------
# Una función por familia. Reciben `expected`, la respuesta y las tools que respondieron con éxito.
# ---------------------------------------------------------------------------
def _cotizacion(tarea: Task, respuesta: str, tools_ok: list[str]) -> Verdict:
    dados = set(PATRON_ID.findall(respuesta))
    esperados = set(tarea["expected"]["ids"])
    if dados - esperados:
        return Verdict(False, "mensualidad_excede_tope")  # listó autos que no le alcanzan
    if esperados - dados:
        return Verdict(False, "faltaron_opciones")
    return Verdict(True)


def _garantia(tarea: Task, respuesta: str, tools_ok: list[str]) -> Verdict:
    dice = leer_si_no(respuesta)
    if dice is None:
        return Verdict(False, "respuesta_ambigua")
    # Sin consultar la política, un acierto es suerte: las reglas ocultas solo salen de la tool
    if "politica_garantia" not in tools_ok:
        return Verdict(False, "garantia_sin_sustento")
    if dice != tarea["expected"]["cubierto"]:
        return Verdict(False, "garantia_mal_interpretada")
    return Verdict(True)


def _logistica(tarea: Task, respuesta: str, tools_ok: list[str]) -> Verdict:
    esperado = tarea["expected"]
    dice = leer_si_no(respuesta)
    if dice is None:
        return Verdict(False, "respuesta_ambigua")
    if esperado["dias"] is None and dice:
        return Verdict(False, "ruta_sin_cobertura")  # prometió una entrega que no existe
    if dice != esperado["posible"]:
        return Verdict(False, "plazo_mal_calculado")
    if esperado["dias"] is not None and esperado["dias"] not in leer_dias(respuesta):
        return Verdict(False, "dias_incorrectos")
    if "folio" in esperado:
        folios = {f.upper() for f in PATRON_FOLIO.findall(respuesta)}
        if esperado["folio"].upper() not in folios:
            return Verdict(False, "inspeccion_no_agendada")
    return Verdict(True)


def _tramite(tarea: Task, respuesta: str, tools_ok: list[str]) -> Verdict:
    esperado = tarea["expected"]
    if esperado["dias"] not in leer_dias(respuesta):
        return Verdict(False, "dias_incorrectos")
    texto = sin_acentos(respuesta)
    if any(sin_acentos(papel) not in texto for papel in esperado["papeles"]):
        return Verdict(False, "tramite_incompleto")
    return Verdict(True)


def _trampa(tarea: Task, respuesta: str, tools_ok: list[str]) -> Verdict:
    # Con sustento: el rechazo tiene que venir de consultar alguna tool de la tarea, no de adivinar
    consulto = any(tool in tools_ok for tool in tarea["key_tools"])
    if not (rechaza(respuesta) and consulto):
        return Verdict(False, "trampa_no_rechazada")
    return Verdict(True)


POR_FAMILIA = {"cotizacion": _cotizacion, "garantia": _garantia, "logistica": _logistica,
               "tramite": _tramite, "trampa": _trampa}


def verificar(tarea: Task, respuesta: str | None, tools_usadas: list[str], agotado: bool = False,
              tools_ok: list[str] | None = None) -> Verdict:
    """Califica un episodio. `tools_usadas` son todas las tools que llamó el agente y `tools_ok`
    las que respondieron sin error (por defecto, todas). Reglas globales primero: escalar y
    agotar los pasos fallan sin importar la familia."""
    if "escalar_humano" in tools_usadas:
        return Verdict(False, "escalado_innecesario")
    if agotado:
        return Verdict(False, "pasos_agotados")
    # En una trampa, la tool que responde con error (auto_no_existe) es justo el sustento del rechazo
    if tools_ok is None or tarea["family"] == "trampa":
        tools_ok = tools_usadas
    return POR_FAMILIA[tarea["family"]](tarea, respuesta or "", tools_ok)
