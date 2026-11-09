"""Agente ReAct de KAIZEN: un solo agente que usa herramientas hasta responder.

El mismo código atiende la evaluación y la demo en vivo: la métrica mide exactamente al agente que ve el cliente.
Cada paso se notifica con `notificar` en cuanto ocurre, para transmitirlo en tiempo real (eventos de docs/CONTRATOS.md §6).

Este módulo no conoce supervisores ni sub-agentes. Si el sistema decide crearlos, los expone al agente como
herramientas más (artefactos generados), sin cambiar este código.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from core import llm
from core.contracts import Step

Notificador = Callable[[dict], None]

MAX_PASOS = 10  # llamadas al modelo antes de cortar el episodio; el verificador lo califica como pasos_agotados
MAX_CARACTERES_RESUMEN = 300  # contrato: Step.result_summary va recortado a 300 caracteres
MAX_CARACTERES_SALIDA_AL_MODELO = 4000  # tope por tool para no inflar el contexto del modelo
RESPUESTA_PASOS_AGOTADOS = "(se agotaron los pasos)"


def ignorar_evento(_evento: dict) -> None:
    """Notificador por defecto cuando nadie escucha los eventos (por ejemplo, durante la evaluación)."""


@dataclass
class Herramienta:
    """Una herramienta que el agente puede pedir: su función de Python y el esquema que lee el modelo."""
    nombre: str
    funcion: Callable[..., object]
    esquema: dict  # formato "function" de la API de chat
    generada: bool = False  # True si la escribió el sistema (data/tools/generated)


@dataclass
class ResultadoAgente:
    """Lo que produce un episodio. Los nombres de campo siguen a Trace en core/contracts.py."""
    final_answer: str = ""
    steps: list[Step] = field(default_factory=list)
    tokens: int = 0
    cost_usd: float = 0.0
    exhausted: bool = False

    def sumar_consumo(self, tokens: int, cost_usd: float) -> None:
        """Acumula los tokens y el costo de una llamada al modelo en el total del episodio."""
        self.tokens += tokens
        self.cost_usd += cost_usd


def resumir_salida(salida: object) -> str:
    """Convierte la salida de una tool a JSON y la recorta a MAX_CARACTERES_RESUMEN para guardarla en el Step."""
    texto = json.dumps(salida, ensure_ascii=False, default=str)
    if len(texto) <= MAX_CARACTERES_RESUMEN:
        return texto
    return texto[:MAX_CARACTERES_RESUMEN - 3] + "..."


def salida_exitosa(salida: object) -> bool:
    """Contrato de Step.ok: es False si la tool devolvió "error" u "ok": false."""
    if not isinstance(salida, dict):
        return True
    return "error" not in salida and salida.get("ok") is not False


def leer_argumentos(argumentos_json: str | None) -> tuple[dict, str | None]:
    """Devuelve (argumentos, error). El modelo puede mandar JSON inválido; en ese caso no se ejecuta la tool."""
    try:
        argumentos = json.loads(argumentos_json or "{}")
    except json.JSONDecodeError as error:
        return {}, f"los argumentos no son JSON válido: {error.msg}"
    if not isinstance(argumentos, dict):
        return {}, "los argumentos deben ser un objeto JSON"
    return argumentos, None


def mensaje_de_llamadas(mensaje) -> dict:
    """Reconstruye el turno del asistente con sus tool_calls para devolverlo al historial del modelo."""
    llamadas = [
        {"id": llamada.id, "type": "function",
         "function": {"name": llamada.function.name, "arguments": llamada.function.arguments}}
        for llamada in mensaje.tool_calls
    ]
    return {"role": "assistant", "content": mensaje.content, "tool_calls": llamadas}


@dataclass
class Agente:
    """Un modelo con instrucciones y herramientas. `nombre` identifica sus pasos y eventos (por ejemplo, gen_3)."""
    nombre: str
    instrucciones: str
    herramientas: dict[str, Herramienta]
    modelo: str = llm.MODELO_AGENTE
    temperatura: float = 0.0
    semilla: int | None = None
    max_pasos: int = MAX_PASOS

    def ejecutar(self, conversacion: list[dict], notificar: Notificador = ignorar_evento,
                 resultado: ResultadoAgente | None = None) -> ResultadoAgente:
        """Bucle ReAct: el modelo pide herramientas hasta que responde sin pedir ninguna o se agotan los pasos.

        `resultado` permite acumular pasos y consumo de varias ejecuciones en el mismo episodio."""
        resultado = resultado or ResultadoAgente()
        mensajes = [{"role": "system", "content": self.instrucciones}, *conversacion]
        esquemas = [herramienta.esquema for herramienta in self.herramientas.values()] or None

        for _paso in range(self.max_pasos):
            mensaje, tokens, costo = llm.chat(mensajes, modelo=self.modelo, herramientas=esquemas,
                                              temperatura=self.temperatura, semilla=self.semilla)
            resultado.sumar_consumo(tokens, costo)

            if not mensaje.tool_calls:
                resultado.final_answer = mensaje.content or ""
                return resultado

            if mensaje.content:  # razonamiento visible que el modelo escribió junto con las llamadas
                notificar({"type": "message", "agent": self.nombre, "text": mensaje.content})
            mensajes.append(mensaje_de_llamadas(mensaje))
            for llamada in mensaje.tool_calls:
                salida = self._usar_herramienta(llamada.function.name, llamada.function.arguments,
                                                notificar, resultado)
                contenido = json.dumps(salida, ensure_ascii=False, default=str)[:MAX_CARACTERES_SALIDA_AL_MODELO]
                mensajes.append({"role": "tool", "tool_call_id": llamada.id, "content": contenido})

        resultado.exhausted = True
        resultado.final_answer = RESPUESTA_PASOS_AGOTADOS
        return resultado

    def _usar_herramienta(self, nombre: str, argumentos_json: str | None, notificar: Notificador,
                          resultado: ResultadoAgente) -> object:
        """Ejecuta una herramienta, mide su latencia, registra el Step y emite tool_call y tool_result."""
        herramienta = self.herramientas.get(nombre)
        generada = bool(herramienta and herramienta.generada)
        argumentos, error_argumentos = leer_argumentos(argumentos_json)
        notificar({"type": "tool_call", "agent": self.nombre, "tool": nombre, "args": argumentos,
                   "generated": generada})

        inicio = time.perf_counter()
        salida = self._invocar(herramienta, nombre, argumentos, error_argumentos)
        latencia_ms = int((time.perf_counter() - inicio) * 1000)

        exitosa = salida_exitosa(salida)
        resumen = resumir_salida(salida)
        resultado.steps.append(Step(agent=self.nombre, tool=nombre, args=argumentos, result_summary=resumen,
                                    ok=exitosa, generated=generada, latency_ms=latencia_ms))
        notificar({"type": "tool_result", "agent": self.nombre, "tool": nombre, "summary": resumen,
                   "ok": exitosa, "ms": latencia_ms})
        return salida

    @staticmethod
    def _invocar(herramienta: Herramienta | None, nombre: str, argumentos: dict,
                 error_argumentos: str | None) -> object:
        """Los errores se devuelven al modelo como {"error": ...} para que pueda corregir; nunca cortan el episodio."""
        if error_argumentos:
            return {"error": error_argumentos}
        if herramienta is None:
            return {"error": f"herramienta desconocida: {nombre}"}
        try:
            return herramienta.funcion(**argumentos)
        except Exception as error:  # el modelo puede inventar argumentos o tipos; una tool generada puede fallar
            return {"error": f"{type(error).__name__}: {error}"}

