"""Meta-destilador, nivel 2B de la auto-mejora: el destilador reescribe su propio prompt.

Si la mejora por generación (delta de éxito en held-out) cae o se estanca, el prompt del destilador está
produciendo playbooks cada vez menos útiles. Se le muestra al modelo ese prompt, los deltas y los playbooks
que generó, y se guarda un prompt nuevo (distiller_prompt_vN.md). La generación siguiente se destila con él.

Solo recibe deltas agregados (números), nunca tareas ni trazas de held-out: no puede aprender sus respuestas.
"""
from __future__ import annotations

from typing import Callable

from core import artifacts, llm, versions

MIN_DELTAS = 2  # hace falta comparar dos mejoras: el delta de gen 1 contra el de gen 2
MAX_PLAYBOOKS_AL_MODELO = 6  # los más recientes de la rama; con más el pedido crece sin aportar
TIPO_PLAYBOOK = "playbook"

SISTEMA = """Eres el destilador de un sistema que mejora solo a un agente de una agencia de autos seminuevos.
Tu prompt convierte fallos del agente en procedimientos (playbooks). Te doy tu prompt actual, la mejora en
held-out de cada generación (deltas) y los playbooks que produjiste.
La última mejora fue menor que la anterior o nula: tus playbooks están ayudando menos.
Diagnostica qué les falta (por ejemplo: son vagos, repiten lo obvio, no dicen qué herramienta usar) y reescribe
tu prompt completo para que produzca procedimientos más accionables.
Sé general: no menciones IDs de autos ni de tareas.
Devuelve JSON: {"prompt": "<prompt nuevo completo>", "diagnostico": "<una frase: qué fallaba y qué cambiaste>"}"""

Registro = Callable[[str], None]


def deberia_reescribir(deltas: list[float]) -> bool:
    """True si la última mejora fue menor que la anterior o si ya no hubo mejora (delta <= 0)."""
    if len(deltas) < MIN_DELTAS:
        return False
    ultimo, anterior = deltas[-1], deltas[-2]
    return ultimo < anterior or ultimo <= 0


def playbooks_recientes(branch: str) -> list[str]:
    """Texto de los últimos playbooks que el destilador escribió en esta rama."""
    playbooks = [artefacto for artefacto in artifacts.all_artifacts()
                 if artefacto["kind"] == TIPO_PLAYBOOK and artefacto["branch"] == branch and artefacto.get("content")]
    return [f"[{p['name']}]\n{p['content']}" for p in playbooks[-MAX_PLAYBOOKS_AL_MODELO:]]


def quizas_reescribir(deltas: list[float], version: int, generacion: int, branch: str,
                      log: Registro = print) -> int:
    """Devuelve la versión del prompt del destilador que usará la generación `generacion`.

    Conserva `version` si los deltas no caen o si el modelo no devuelve un prompt. Si no, guarda el prompt
    nuevo con versions.guardar y devuelve su número."""
    if not deberia_reescribir(deltas):
        log(f"meta-destilador: deltas {deltas}, se conserva el prompt v{version}")
        return version

    prompt_actual = versions.texto("distiller_prompt", version)
    playbooks = "\n---\n".join(playbooks_recientes(branch)) or "(ninguno)"
    pedido = (f"Tu prompt actual:\n{prompt_actual}\n\nDeltas por generación: {deltas}\n\n"
              f"Tus playbooks recientes:\n{playbooks}")
    respuesta, _costo = llm.chat_json(SISTEMA, pedido)
    prompt_nuevo = str(respuesta.get("prompt") or "").strip()
    if not prompt_nuevo:
        log("meta-destilador: el modelo no devolvió un prompt, se conserva el actual")
        return version

    version_nueva = versions.guardar("distiller_prompt", prompt_nuevo + "\n", generacion, branch,
                                     deltas=deltas, diagnosis=str(respuesta.get("diagnostico") or ""))
    log(f"meta-destilador: el destilador reescribió su prompt (v{version_nueva})")
    return version_nueva
