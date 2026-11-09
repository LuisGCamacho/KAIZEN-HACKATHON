"""Destilador, nivel 1 de la auto-mejora: convierte los fallos de una generación en la siguiente.

Toma SOLO los fallos de train del padre, los agrupa por causa (Verdict.reason) y, para las causas más
frecuentes, escribe un playbook e intenta sintetizar una herramienta. Después reescribe el prompt del agente
y devuelve la AgentSpec de la nueva generación. Quien lo llama (run.py) la guarda con builder.save_spec.

La regla sagrada: el destilador nunca ve held-out. Si lo viera, la mejora medida en held-out sería trampa.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Callable

from core import artifacts, llm, versions
from core.contracts import AgentSpec, Artifact, Trace
from core.paths import DATA, PLAYBOOKS, PROMPTS, rel
from improve import tool_synth

MAX_CAUSAS = 3  # solo las causas más frecuentes: concentra el aprendizaje donde más se falla
MAX_EJEMPLOS_POR_CAUSA = 6
MAX_CARACTERES_RESPUESTA_EJEMPLO = 500  # recorta respuestas largas para no inflar el prompt del destilador
TEMPERATURA_PLAYBOOK = 0.2
SPLIT_ENTRENAMIENTO = "train"
RAMA_PRINCIPAL = "main"
# Nombre de un playbook: <causa>_g<generación>[_<rama>].md, por ejemplo garantia_mal_interpretada_g2_smoke.md
PATRON_PLAYBOOK = re.compile(r"^(?P<causa>.+)_g\d+(_[a-z0-9_-]+)?$")

REESCRITOR_DE_PROMPT = """Eres el arquitecto de un agente de operaciones de una agencia de autos seminuevos que se mejora solo.
Recibes su prompt de sistema actual y los fallos de su última evaluación, agrupados por causa y con su conteo.
Reescribe el prompt para corregir esas causas de forma general: no menciones IDs de autos ni de tareas.
Conserva las reglas que sigan siendo válidas y quita las que provocan fallos.
Devuelve JSON: {"prompt": "<prompt nuevo completo>", "rationale": "<2 o 3 frases: qué cambiaste y por qué, con los números de fallos>"}"""

Registro = Callable[[str], None]


def fallos_de_train(trazas: list[Trace]) -> list[Trace]:
    """Solo los episodios fallidos del split de entrenamiento. Esta es la única puerta de entrada al destilador."""
    return [traza for traza in trazas if traza.split == SPLIT_ENTRENAMIENTO and not traza.verdict.passed]


def sufijo_de_rama(rama: str) -> str:
    """Los archivos de main no llevan sufijo; los de otras ramas sí, para no pisarse entre ramas."""
    return "" if rama == RAMA_PRINCIPAL else f"_{rama}"


def formatear_ejemplos(trazas: list[Trace]) -> str:
    """Convierte episodios fallidos en ejemplos JSON legibles para el modelo: petición, pasos, respuesta y causa."""
    ejemplos = []
    for traza in trazas:
        pasos = [{"tool": paso.tool, "args": paso.args, "resultado": paso.result_summary} for paso in traza.steps]
        ejemplos.append(json.dumps({
            "peticion": traza.prompt,
            "esperado": traza.expected,
            "pasos": pasos,
            "respuesta": traza.final_answer[:MAX_CARACTERES_RESPUESTA_EJEMPLO],
            "causa": traza.verdict.reason,
        }, ensure_ascii=False))
    return "\n\n".join(ejemplos)


def leer_prompt_destilador(version: int) -> str:
    """Prompt con el que el destilador escribe playbooks. El meta-destilador crea versiones nuevas (v1, v2...)."""
    texto = versions.texto("distiller_prompt", version)
    if not texto:
        raise FileNotFoundError(f"No existe el prompt del destilador v{version}: "
                                f"{versions.ruta('distiller_prompt', version)}")
    return texto


def causa_de_playbook(ruta: str) -> str | None:
    """Causa que corrige un playbook, leída de su nombre de archivo; None si el nombre no sigue el formato."""
    nombre = ruta.rsplit("/", 1)[-1].removesuffix(".md")
    coincidencia = PATRON_PLAYBOOK.match(nombre)
    return coincidencia["causa"] if coincidencia else None


def heredar_playbooks(padre: AgentSpec) -> dict[str, str]:
    """Playbooks del padre indexados por causa. Uno nuevo de la misma causa reemplazará al heredado."""
    heredados = {}
    for ruta in padre.playbooks:
        causa = causa_de_playbook(ruta) or ruta  # un nombre fuera de formato se conserva tal cual
        heredados[causa] = ruta
    return heredados


def escribir_playbook(causa: str, cantidad_fallos: int, ejemplos: str, generacion: int, rama: str,
                      version_destilador: int) -> dict:
    """Pide al modelo un procedimiento para una causa, lo guarda en data/playbooks y lo registra como artefacto."""
    mensajes = [
        {"role": "system", "content": leer_prompt_destilador(version_destilador)},
        {"role": "user", "content": f"Causa: {causa} ({cantidad_fallos} fallos)\n\nEjemplos:\n{ejemplos}"},
    ]
    mensaje, _tokens, _costo = llm.chat(mensajes, modelo=llm.MODELO_INTELIGENTE, temperatura=TEMPERATURA_PLAYBOOK)
    contenido = (mensaje.content or "").strip() + "\n"
    ruta = PLAYBOOKS / f"{causa}_g{generacion}{sufijo_de_rama(rama)}.md"
    ruta.write_text(contenido, encoding="utf-8")

    artefacto = Artifact(name=ruta.name, kind="playbook", generation=generacion, branch=rama, origin=causa,
                         origin_failures=cantidad_fallos, accepted=True, path=rel(ruta))
    return artifacts.add(artefacto.to_dict() | {"content": contenido})


def reescribir_prompt(padre: AgentSpec, conteo_causas: Counter, generacion: int, rama: str) -> tuple[str, str]:
    """Pide al modelo un prompt nuevo que corrija las causas de fallo. Devuelve (ruta relativa, justificación).

    Si el modelo no devuelve un prompt, se conserva el del padre y la justificación lo dice."""
    prompt_actual = (DATA / padre.system_prompt_path).read_text(encoding="utf-8")
    pedido = f"Prompt actual:\n{prompt_actual}\n\nFallos por causa: {dict(conteo_causas)}"
    respuesta, _costo = llm.chat_json(REESCRITOR_DE_PROMPT, pedido)

    prompt_nuevo = str(respuesta.get("prompt") or "").strip()
    justificacion = str(respuesta.get("rationale") or "").strip()
    if not prompt_nuevo:
        prompt_nuevo = prompt_actual.strip()
        justificacion = "El modelo no devolvió un prompt nuevo: se conserva el del padre."
    ruta = PROMPTS / f"gen_{generacion}{sufijo_de_rama(rama)}.md"
    ruta.write_text(prompt_nuevo + "\n", encoding="utf-8")
    return rel(ruta), justificacion


def distill(padre: AgentSpec, trazas: list[Trace], rama: str, version_destilador: int, version_rubrica: int,
            log: Registro = print) -> AgentSpec:
    """Produce la spec de la generación siguiente a `padre` a partir de sus trazas.

    Pasos: fallos de train → conteo por causa → playbook y tool para las MAX_CAUSAS más frecuentes →
    prompt reescrito. La topología y los sub-agentes se heredan del padre sin cambios."""
    generacion = padre.generation + 1
    fallos = fallos_de_train(trazas)
    conteo_causas = Counter(traza.verdict.reason for traza in fallos)
    log(f"destilador: {len(fallos)} fallos de train en {len(conteo_causas)} causas")

    playbooks = heredar_playbooks(padre)
    herramientas = list(padre.tools_enabled)
    artefactos_nuevos: list[str] = []

    if not fallos:  # nada que aprender: no se gasta en el modelo
        ruta_prompt, justificacion = padre.system_prompt_path, "Sin fallos en train: se conserva la generación anterior."
    else:
        for causa, cantidad in conteo_causas.most_common(MAX_CAUSAS):
            ejemplos = formatear_ejemplos([traza for traza in fallos if traza.verdict.reason == causa]
                                          [:MAX_EJEMPLOS_POR_CAUSA])
            playbook = escribir_playbook(causa, cantidad, ejemplos, generacion, rama, version_destilador)
            playbooks[causa] = playbook["path"]
            artefactos_nuevos.append(playbook["path"])
            log(f"playbook {playbook['name']} ({cantidad} fallos)")

            herramienta = tool_synth.sintetizar(causa, ejemplos, cantidad, generacion, rama)
            if herramienta is None:  # el modelo decidió que una tool no ayuda a esta causa
                continue
            if herramienta["path"]:  # una tool que ni siquiera se generó (timeout) no tiene archivo
                artefactos_nuevos.append(herramienta["path"])
            if herramienta["accepted"]:
                log(f"tool {herramienta['name']}: aceptada")
                if herramienta["name"] not in herramientas:
                    herramientas.append(herramienta["name"])
            else:
                log(f"tool {herramienta['name']}: rechazada ({herramienta['rejection']})")
        ruta_prompt, justificacion = reescribir_prompt(padre, conteo_causas, generacion, rama)

    return AgentSpec(
        generation=generacion,
        branch=rama,
        parent=f"{padre.branch}/gen_{padre.generation}",
        system_prompt_path=ruta_prompt,
        topology=padre.topology,
        tools_enabled=herramientas,
        playbooks=list(playbooks.values()),
        sub_agents=list(padre.sub_agents),
        distiller_prompt_version=version_destilador,
        rubric_version=version_rubrica,
        rationale=justificacion,
        clusters=dict(conteo_causas),
        new_artifacts=artefactos_nuevos,
    )
