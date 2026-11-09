"""Síntesis de herramientas: el modelo escribe una función compuesta y sus tests; el gate decide si entra.

Para una causa de fallo, el modelo decide si una función que encadene herramientas base evitaría el error.
Si la propone, pasa tres filtros antes de que el agente la pueda usar:
1. Nombre válido y sin choque con una herramienta base.
2. Revisión del AST: allowlist de imports y prohibición de builtins peligrosos y atributos dunder.
3. Sus propios tests con pytest, en un proceso aparte y con timeout.

Una tool aceptada queda en data/tools/generated/ (<nombre>.py, test_<nombre>.py y <nombre>.json con su esquema,
que lee agents/builder.py). Una rechazada se mueve a data/tools/rejected/ como evidencia.

El gate filtra lo obviamente peligroso, pero NO es un sandbox de seguridad: úsalo solo en local.
"""
from __future__ import annotations

import ast
import inspect
import json
import keyword
import os
import re
import shutil
import subprocess
import sys

import openai

from core import artifacts, llm, paths
from core.contracts import Artifact
from env.tools import FUNCIONES

IMPORTS_PERMITIDOS = {"env.tools", "env.inventario", "math", "datetime", "typing", "__future__", "pytest"}
PREFIJO_IMPORT_GENERADAS = "tools.generated"  # los tests importan la tool desde aquí
NOMBRES_PROHIBIDOS = {"open", "eval", "exec", "__import__", "compile", "globals", "locals", "getattr",
                      "setattr", "delattr", "input", "breakpoint", "vars"}
PATRON_NOMBRE_TOOL = re.compile(r"^[a-z][a-z0-9_]{2,47}$")  # snake_case; la API limita los nombres de función

TIMEOUT_POR_TEST_S = 10
TIMEOUT_TOTAL_TESTS_S = 60
MAX_CARACTERES_SALIDA_PYTEST = 600  # lo último de la salida de pytest basta para explicar el rechazo
# Un solo intento acotado: si el modelo se atora, se pierde la tool, no la generación entera
LIMITES_MODELO = {"timeout_s": 400, "max_tokens": 2500, "reintentos": 1}

SISTEMA = """Eres un ingeniero que escribe herramientas compuestas para un agente de operaciones de una agencia de autos seminuevos.
Analiza los fallos y decide si una función de Python que ENCAPSULE una secuencia de llamadas a las herramientas base evitaría el error.
Si no aporta, responde {"skip": true, "why": "<una frase>"}.
Si aporta, responde JSON con:
- "name": snake_case, distinto de las herramientas base.
- "description": una línea que el agente leerá para saber cuándo usarla.
- "parameters": JSON Schema (type object) de sus argumentos.
- "code": módulo de Python que define la función `name` y devuelve un dict. Solo puede importar de env.tools, env.inventario, math, datetime o typing. Sin archivos, red ni sistema. Con un docstring que cite la generación y la causa de origen.
- "tests": archivo pytest que importa con `from tools.generated.<name> import <name>` y verifica casos concretos contra las herramientas base (calcula lo esperado con ellas; no escribas números a mano).
Sé breve: la función en 30 líneas o menos, y como máximo 3 tests cortos."""


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------
def revisar_ast(codigo: str) -> str | None:
    """Motivo de rechazo si el código sale de la allowlist; None si pasa la revisión."""
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as error:
        return f"sintaxis inválida: {error.msg} (línea {error.lineno})"
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name not in IMPORTS_PERMITIDOS:
                    return f"import prohibido: {alias.name}"
        elif isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            if nodo.level or (modulo not in IMPORTS_PERMITIDOS and not modulo.startswith(PREFIJO_IMPORT_GENERADAS)):
                return f"import prohibido: {'.' * nodo.level}{modulo}"
        elif isinstance(nodo, ast.Name) and (nodo.id in NOMBRES_PROHIBIDOS or nodo.id.startswith("__")):
            return f"nombre prohibido: {nodo.id}"
        elif isinstance(nodo, ast.Attribute) and nodo.attr.startswith("__"):
            return f"atributo dunder prohibido: {nodo.attr}"
    return None


def revisar_nombre(nombre: str) -> str | None:
    """Motivo de rechazo si el nombre no sirve como herramienta; None si es válido."""
    if not PATRON_NOMBRE_TOOL.match(nombre) or keyword.iskeyword(nombre):
        return f"nombre inválido: {nombre!r} (snake_case, 3 a 48 caracteres)"
    if nombre in FUNCIONES:
        return f"el nombre {nombre!r} choca con una herramienta base"
    return None


def define_funcion(codigo: str, nombre: str) -> bool:
    """True si el módulo define en su nivel superior una función con ese nombre."""
    return any(isinstance(nodo, ast.FunctionDef) and nodo.name == nombre for nodo in ast.parse(codigo).body)


def tiene_tests(codigo_tests: str) -> bool:
    """True si el archivo de tests define al menos una función test_*; sin tests, el gate no prueba nada."""
    return any(isinstance(nodo, ast.FunctionDef) and nodo.name.startswith("test_")
               for nodo in ast.parse(codigo_tests).body)


def correr_tests(nombre: str) -> tuple[bool, str]:
    """Corre test_<nombre>.py con pytest en un proceso aparte. Devuelve (pasaron, final de la salida).

    PYTHONPATH incluye backend/ (para env.tools) y data/ (para tools.generated)."""
    entorno = {**os.environ, "PYTHONPATH": os.pathsep.join([str(paths.BACKEND), str(paths.DATA)]),
               "PYTHONIOENCODING": "utf-8"}
    comando = [sys.executable, "-m", "pytest", str(paths.TOOLS_GENERADAS / f"test_{nombre}.py"), "-q",
               f"--timeout={TIMEOUT_POR_TEST_S}", "-p", "no:cacheprovider"]
    try:
        proceso = subprocess.run(comando, cwd=paths.DATA, env=entorno, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=TIMEOUT_TOTAL_TESTS_S)
    except subprocess.TimeoutExpired:
        return False, f"los tests excedieron {TIMEOUT_TOTAL_TESTS_S} s"
    salida = (proceso.stdout + proceso.stderr)[-MAX_CARACTERES_SALIDA_PYTEST:]
    return proceso.returncode == 0, salida


def pasar_gate(nombre: str, codigo: str, tests: str) -> str | None:
    """Aplica los tres filtros en orden. None si la tool pasa; si no, el motivo del rechazo.

    Escribe el código y los tests en data/tools/generated/ solo si pasaron las revisiones estáticas."""
    motivo = revisar_nombre(nombre)
    if motivo:
        return motivo
    for fuente in (codigo, tests):
        motivo = revisar_ast(fuente)
        if motivo:
            return motivo
    if not define_funcion(codigo, nombre):
        return f"el módulo no define la función {nombre}"
    if not tiene_tests(tests):
        return "el archivo de tests no define ninguna función test_*"

    (paths.TOOLS_GENERADAS / f"{nombre}.py").write_text(codigo, encoding="utf-8")
    (paths.TOOLS_GENERADAS / f"test_{nombre}.py").write_text(tests, encoding="utf-8")
    pasaron, salida = correr_tests(nombre)
    return None if pasaron else f"tests fallaron:\n{salida}"


# ---------------------------------------------------------------------------
# Archivos y registro
# ---------------------------------------------------------------------------
def mover_a_rechazadas(nombre: str, codigo: str, tests: str) -> str:
    """Deja el código y los tests en data/tools/rejected/ y devuelve la ruta relativa del código."""
    for archivo in (f"{nombre}.py", f"test_{nombre}.py"):
        (paths.TOOLS_GENERADAS / archivo).unlink(missing_ok=True)
    (paths.TOOLS_RECHAZADAS / f"{nombre}.py").write_text(codigo, encoding="utf-8")
    (paths.TOOLS_RECHAZADAS / f"test_{nombre}.py").write_text(tests, encoding="utf-8")
    return paths.rel(paths.TOOLS_RECHAZADAS / f"{nombre}.py")


def guardar_esquema(nombre: str, descripcion: str, parametros: dict, generacion: int, rama: str,
                    causa: str, cantidad_fallos: int) -> None:
    """Escribe <nombre>.json: el esquema que el builder le da al agente y el origen de la tool."""
    esquema = {"type": "function", "function": {"name": nombre, "description": descripcion,
                                                "parameters": parametros}}
    origen = {"generation": generacion, "branch": rama, "origin": causa, "origin_failures": cantidad_fallos}
    (paths.TOOLS_GENERADAS / f"{nombre}.json").write_text(
        json.dumps({"schema": esquema, **origen}, ensure_ascii=False, indent=2), encoding="utf-8")


def nombre_disponible(nombre: str, generacion: int) -> str:
    """Si ya existe una tool (aceptada o rechazada) con ese nombre, agrega _g<generación> para no pisarla."""
    ocupado = any((carpeta / f"{nombre}.py").exists() for carpeta in (paths.TOOLS_GENERADAS, paths.TOOLS_RECHAZADAS))
    return f"{nombre}_g{generacion}" if ocupado else nombre


def renombrar_funcion(texto: str, anterior: str, nuevo: str) -> str:
    """Cambia el nombre de la función en el código y en los tests (solo palabras completas)."""
    return re.sub(rf"\b{re.escape(anterior)}\b", nuevo, texto)


def firmas_base() -> str:
    """Firma de cada herramienta base, para que el modelo sepa qué puede encadenar."""
    return "\n".join(f"{nombre}{inspect.signature(funcion)}" for nombre, funcion in FUNCIONES.items())


def registrar(nombre: str, causa: str, cantidad_fallos: int, generacion: int, rama: str, aceptada: bool,
              ruta: str, descripcion: str = "", rechazo: str = "", codigo: str = "", tests: str = "") -> dict:
    """Registra la tool en artifacts.json (aceptada o no) y devuelve el registro que usa el destilador."""
    artefacto = Artifact(name=nombre, kind="tool", generation=generacion, branch=rama, origin=causa,
                         origin_failures=cantidad_fallos, accepted=aceptada, path=ruta, description=descripcion,
                         rejection=rechazo)
    return artifacts.add(artefacto.to_dict() | {"code": codigo, "tests": tests})


# ---------------------------------------------------------------------------
# Entrada pública (la llama improve/distiller.py)
# ---------------------------------------------------------------------------
def sintetizar(causa: str, ejemplos: str, cantidad_fallos: int, generacion: int, rama: str) -> dict | None:
    """Intenta crear una herramienta para una causa de fallo.

    Devuelve None si el modelo decide que una tool no ayuda. Si no, devuelve el artefacto registrado, con
    `name`, `accepted`, `rejection` y `path` ("" si el modelo no llegó a escribirla)."""
    pedido = (f"Herramientas base disponibles:\n{firmas_base()}\n\nGeneración que se está construyendo: {generacion}\n"
              f"Causa: {causa} ({cantidad_fallos} fallos)\n\nEpisodios fallidos:\n{ejemplos}")
    try:
        propuesta, _costo = llm.chat_json(SISTEMA, pedido, **LIMITES_MODELO)
    except (openai.APIError, json.JSONDecodeError) as error:  # timeout, error de API o JSON cortado
        motivo = "el modelo no respondió a tiempo" if isinstance(error, openai.APITimeoutError) else "respuesta incompleta"
        return registrar(f"{causa}_g{generacion}", causa, cantidad_fallos, generacion, rama, aceptada=False,
                         ruta="", rechazo=f"no generada: {motivo}")

    if propuesta.get("skip") or not propuesta.get("name"):
        return None

    nombre_propuesto = str(propuesta["name"]).strip()
    codigo, tests = str(propuesta.get("code", "")), str(propuesta.get("tests", ""))
    descripcion = str(propuesta.get("description", ""))
    # El nombre se valida antes de usarlo en una ruta: un nombre como "../x" escribiría fuera de data/tools
    motivo = revisar_nombre(nombre_propuesto)
    if motivo:
        return registrar(f"{causa}_g{generacion}", causa, cantidad_fallos, generacion, rama, aceptada=False,
                         ruta="", descripcion=descripcion, rechazo=motivo, codigo=codigo, tests=tests)

    nombre = nombre_disponible(nombre_propuesto, generacion)
    codigo = renombrar_funcion(codigo, nombre_propuesto, nombre)
    tests = renombrar_funcion(tests, nombre_propuesto, nombre)

    motivo = pasar_gate(nombre, codigo, tests)
    if motivo:
        ruta = mover_a_rechazadas(nombre, codigo, tests)
        return registrar(nombre, causa, cantidad_fallos, generacion, rama, aceptada=False, ruta=ruta,
                         descripcion=descripcion, rechazo=motivo, codigo=codigo, tests=tests)

    parametros = propuesta.get("parameters") or {"type": "object", "properties": {}}
    guardar_esquema(nombre, descripcion, parametros, generacion, rama, causa, cantidad_fallos)
    return registrar(nombre, causa, cantidad_fallos, generacion, rama, aceptada=True,
                     ruta=paths.rel(paths.TOOLS_GENERADAS / f"{nombre}.py"), descripcion=descripcion,
                     codigo=codigo, tests=tests)
