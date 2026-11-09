"""Builder: convierte la spec de una generación (data/specs/<rama>/gen_N.json) en un agente listo para correr.

La spec dice qué prompt usar, qué playbooks pegarle y qué herramientas habilitar (base y generadas por el sistema).
evaluation/evals.py y live.py lo usan igual, así que la demo corre exactamente el agente que se evalúa.

Las funciones públicas (spec_path, load_spec, save_spec, latest_generation, build) conservan los nombres del
tutorial porque las llaman módulos de otras áreas.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Callable

from agents.agent import Agente, Herramienta, Notificador, ResultadoAgente, ignorar_evento
from core.contracts import AgentSpec
from core.paths import DATA, SPECS, TOOLS_GENERADAS
from env.tools import ESQUEMAS, FUNCIONES  # las 8 herramientas base (dueño: Backend A)

RAMA_PRINCIPAL = "main"
TOPOLOGIA_SOPORTADA = "single_react"
TEMPERATURA_EVALUACION = 0.5  # con 0 las semillas salen casi iguales y las barras de error no significan nada
TEMPERATURA_DEMO = 0.0  # en /live se usa 0 para que la demo sea estable
ENCABEZADO_PLAYBOOK = "\n\n## Procedimiento aprendido\n"

EjecutarAgente = Callable[[list[dict], Notificador], ResultadoAgente]


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------
def spec_path(generation: int, branch: str = RAMA_PRINCIPAL) -> Path:
    """Ruta del archivo de spec de una generación: data/specs/<rama>/gen_<N>.json."""
    return SPECS / branch / f"gen_{generation}.json"


def load_spec(generation: int, branch: str = RAMA_PRINCIPAL) -> AgentSpec:
    """Lee la spec de una generación y la convierte en AgentSpec.

    Si la rama derivada (por ejemplo, control) no tiene esa generación, usa la de main: comparten las
    generaciones anteriores al fork."""
    ruta = spec_path(generation, branch)
    if not ruta.exists() and branch != RAMA_PRINCIPAL:
        ruta = spec_path(generation, RAMA_PRINCIPAL)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la spec de gen {generation} en la rama {branch}: {ruta}")
    return AgentSpec.from_dict(json.loads(ruta.read_text(encoding="utf-8")))


def save_spec(spec: AgentSpec) -> Path:
    """Escribe la spec en su ruta (crea la carpeta de la rama si no existe) y devuelve esa ruta."""
    ruta =spec_path(spec.generation, spec.branch)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def latest_generation(branch: str = RAMA_PRINCIPAL) -> int:
    """Generación más alta con spec en la rama; 0 si la rama aún no tiene ninguna."""
    generaciones = [int(ruta.stem.removeprefix("gen_")) for ruta in (SPECS / branch).glob("gen_*.json")]
    return max(generaciones, default=0)


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------
def cargar_herramienta_generada(nombre: str) -> Herramienta:
    """Importa en caliente una tool que escribió el sistema y que pasó el gate.

    Cada tool aceptada vive en data/tools/generated/ como <nombre>.py (la función) y <nombre>.json (su esquema)."""
    ruta_codigo = TOOLS_GENERADAS / f"{nombre}.py"
    ruta_esquema = TOOLS_GENERADAS / f"{nombre}.json"
    especificacion = importlib.util.spec_from_file_location(f"tools_generadas.{nombre}", ruta_codigo)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    esquema = json.loads(ruta_esquema.read_text(encoding="utf-8"))["schema"]
    return Herramienta(nombre, getattr(modulo, nombre), esquema, generada=True)


def es_herramienta_generada(nombre: str) -> bool:
    """True si existe una tool generada con ese nombre: necesita su código (.py) y su esquema (.json)."""
    return (TOOLS_GENERADAS / f"{nombre}.py").exists() and (TOOLS_GENERADAS / f"{nombre}.json").exists()


def herramientas_base_que_usa(nombre: str) -> set[str]:
    """Tools base que llama por dentro una tool generada, por análisis estático de su código (no se ejecuta)."""
    ruta_codigo = TOOLS_GENERADAS / f"{nombre}.py"
    if not ruta_codigo.exists():
        return set()
    usadas = set()
    for nodo in ast.walk(ast.parse(ruta_codigo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Call):
            llamada = nodo.func
            nombre_llamada = llamada.id if isinstance(llamada, ast.Name) else getattr(llamada, "attr", None)
            if nombre_llamada in FUNCIONES:
                usadas.add(nombre_llamada)
    return usadas


def con_herramientas_base(herramientas: list[str]) -> list[str]:
    """Agrega, tras cada tool generada, las tools base que usa por dentro.

    El verificador exige haber consultado una tool clave de la tarea (respuestas con sustento). Una tool
    generada que llama a esa tool clave es igual de fundamentada; sin esta expansión el sistema se castigaba
    por crear herramientas (p. ej. trap_09 rechazado bien en gen 3, pero contado como "sin sustento")."""
    expandidas = list(herramientas)
    for nombre in herramientas:
        if nombre not in FUNCIONES:
            expandidas += sorted(herramientas_base_que_usa(nombre) - set(expandidas))
    return expandidas


def caja_de_herramientas(spec: AgentSpec) -> dict[str, Herramienta]:
    """Las herramientas que habilita la spec: primero las base y, si no, las generadas por el sistema.

    Una herramienta que no existe es un error: ignorarla cambiaría en silencio el agente que se mide."""
    herramientas: dict[str, Herramienta] = {}
    faltantes: list[str] = []
    for nombre in spec.tools_enabled:
        if nombre in FUNCIONES:
            herramientas[nombre] = Herramienta(nombre, FUNCIONES[nombre], ESQUEMAS[nombre])
        elif es_herramienta_generada(nombre):
            herramientas[nombre] = cargar_herramienta_generada(nombre)
        else:
            faltantes.append(nombre)
    if faltantes:
        raise ValueError(f"gen {spec.generation} [{spec.branch}] habilita herramientas que no existen: {faltantes}")
    return herramientas


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------
def instrucciones(spec: AgentSpec) -> str:
    """Prompt de sistema = prompt de la generación + un bloque por cada playbook aprendido."""
    texto = (DATA / spec.system_prompt_path).read_text(encoding="utf-8").strip()
    for ruta_playbook in spec.playbooks:
        texto += ENCABEZADO_PLAYBOOK + (DATA / ruta_playbook).read_text(encoding="utf-8").strip()
    return texto + "\n"


def build(spec: AgentSpec, seed: int | None = None, temperature: float = TEMPERATURA_EVALUACION) -> EjecutarAgente:
    """Devuelve una función ejecutar(conversacion, notificar) -> ResultadoAgente con el agente de la spec.

    Las herramientas e instrucciones se cargan una sola vez; cada llamada a ejecutar es un episodio nuevo."""
    if spec.topology != TOPOLOGIA_SOPORTADA:
        raise NotImplementedError(f"topología {spec.topology!r} no soportada: el agente solo corre como "
                                  f"{TOPOLOGIA_SOPORTADA} (los sub-agentes los creará el sistema como herramientas)")
    agente = Agente(nombre=f"gen_{spec.generation}", instrucciones=instrucciones(spec),
                    herramientas=caja_de_herramientas(spec), temperatura=temperature, semilla=seed)

    def ejecutar(conversacion: list[dict], notificar: Notificador = ignorar_evento) -> ResultadoAgente:
        """Corre un episodio: el agente responde a la conversación y avisa cada paso con `notificar`."""
        return agente.ejecutar(conversacion, notificar)

    return ejecutar
