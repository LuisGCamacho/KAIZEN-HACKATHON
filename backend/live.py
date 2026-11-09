"""Demo en vivo: lee una conversación por stdin, corre el agente y emite eventos NDJSON por stdout.

Entrada:  {"messages": [{role, content}], "generation": N | "best" | "latest", "branch": "main"}
Salida:   un LiveEvent por línea (web/lib/types.ts). Siempre termina en "final" o en "error".
La conversación se guarda en data/runs/live/ y no entra al aprendizaje.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import almacen, archivos, paths  # noqa: E402
from core.contracts import AgentSpec  # noqa: E402

# Límites de la demo pública: acotan el gasto de una sola petición
MAX_MENSAJES = 20
MAX_CARACTERES = 2_000
ROLES_VALIDOS = {"user", "assistant"}
PATRON_RAMA = re.compile(r"^[a-z0-9_-]{1,32}$")  # misma regla que /api/live

_eventos: list[dict[str, Any]] = []


class EntradaInvalida(ValueError):
    """La petición no cumple el contrato de LiveRequest."""


def emitir(evento: dict[str, Any]) -> None:
    """Escribe un evento y hace flush: sin flush, el navegador recibiría todo al final."""
    linea = {"t": round(time.time() * 1000), **evento}
    _eventos.append(linea)
    sys.stdout.write(json.dumps(linea, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def validar(entrada: dict[str, Any]) -> tuple[list[dict[str, str]], str, int | str]:
    """Devuelve (mensajes, rama, generación pedida) o lanza EntradaInvalida."""
    mensajes = entrada.get("messages")
    if not isinstance(mensajes, list) or not mensajes:
        raise EntradaInvalida("messages debe ser una lista no vacía")
    if len(mensajes) > MAX_MENSAJES:
        raise EntradaInvalida(f"máximo {MAX_MENSAJES} mensajes por conversación")
    limpios = []
    for m in mensajes:
        if not isinstance(m, dict) or m.get("role") not in ROLES_VALIDOS or not isinstance(m.get("content"), str):
            raise EntradaInvalida("cada mensaje necesita role (user|assistant) y content (texto)")
        if len(m["content"]) > MAX_CARACTERES:
            raise EntradaInvalida(f"máximo {MAX_CARACTERES} caracteres por mensaje")
        limpios.append({"role": m["role"], "content": m["content"]})
    if limpios[-1]["role"] != "user":
        raise EntradaInvalida("el último mensaje debe ser del cliente (role user)")

    branch = entrada.get("branch") or almacen.RAMA_PRINCIPAL
    if not isinstance(branch, str) or not PATRON_RAMA.match(branch):
        raise EntradaInvalida("rama inválida")
    pedida = entrada.get("generation", "best")
    if pedida not in ("best", "latest") and not (isinstance(pedida, int) and not isinstance(pedida, bool) and pedida >= 0):
        raise EntradaInvalida('generation debe ser un entero >= 0, "best" o "latest"')
    return limpios, branch, pedida


def resolver_generacion(branch: str, pedida: int | str) -> int:
    """"best" = mayor held-out (en empate, la más nueva); "latest" = la última evaluada."""
    if isinstance(pedida, int):
        return pedida
    from evaluation import export
    filas = export.filas_de_rama(branch)
    if not filas:
        raise EntradaInvalida(f"la rama {branch} todavía no tiene generaciones evaluadas")
    return export.mejor_generacion(filas) if pedida == "best" else filas[-1]["generation"]


def construir_agente(spec: AgentSpec):
    """Punto de integración con la IA Engineer: el mismo builder que la evaluación, con temperatura 0."""
    from agents import builder
    return builder.build(spec, temperature=0.0)


def guardar_conversacion(mensajes: list[dict[str, str]], branch: str, generacion: int | None) -> None:
    sello = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archivos.escribir_json(paths.LIVE / f"{sello}.json", {"branch": branch, "generation": generacion,
                                                          "messages": mensajes, "events": _eventos})


def main() -> int:
    mensajes: list[dict[str, str]] = []
    branch, generacion = almacen.RAMA_PRINCIPAL, None
    try:
        entrada = json.loads(sys.stdin.read() or "{}")
        if not isinstance(entrada, dict):
            raise EntradaInvalida("la entrada debe ser un objeto JSON")
        mensajes, branch, pedida = validar(entrada)
        generacion = resolver_generacion(branch, pedida)
        spec = almacen.cargar_spec(branch, generacion)
        if spec is None:
            raise EntradaInvalida(f"no existe {branch}/gen_{generacion}")
        emitir({"type": "start", "generation": spec.generation, "branch": branch, "topology": spec.topology,
                "sub_agents": spec.sub_agents, "tools": spec.tools_enabled, "playbooks": len(spec.playbooks)})
        resultado = construir_agente(spec)(mensajes, emitir)
        emitir({"type": "final", "agent": f"gen_{spec.generation}", "text": resultado.final,
                "tokens": resultado.tokens, "cost_usd": round(resultado.cost_usd, 6),
                "steps": len(resultado.steps), "exhausted": resultado.exhausted})
    except Exception as e:  # frontera: el cliente de la demo debe ver el motivo, no un stream cortado
        mensaje = str(e) if isinstance(e, (EntradaInvalida, json.JSONDecodeError)) else f"{type(e).__name__}: {e}"
        emitir({"type": "error", "message": mensaje})
    finally:
        if mensajes:
            guardar_conversacion(mensajes, branch, generacion)
    return 0  # el error ya se emitió como evento; un código != 0 queda para fallos que no llegaron aquí


if __name__ == "__main__":
    sys.exit(main())
