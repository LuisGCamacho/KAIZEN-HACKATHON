"""CLI de KAIZEN: orquesta evaluar → destilar → evaluar y exporta los JSON de la web.

    python run.py smoke | gen0 | next [--branch B] [--fork-from N] [--no-meta-distiller]
    python run.py loop --until N | export | reset [--dry] | rescore [--trato]

Códigos de salida (docs/CONTRATOS.md §7): 0 ok, 1 error, 3 ya hay una corrida, 4 presupuesto agotado.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import almacen, archivos, llm, paths, progress  # noqa: E402
from core.contracts import BASE_TOOLS, HELDOUT_PER_FAMILY, AgentSpec  # noqa: E402

SALIDA_OK, SALIDA_ERROR, SALIDA_OCUPADO, SALIDA_PRESUPUESTO, SALIDA_CANCELADA = 0, 1, 3, 4, 5
MOTIVO_CANCELACION = "Cancelada por el usuario"
RAMA_SMOKE = "smoke"
SMOKE_TAREAS_POR_FAMILIA = ("00", "10")  # 2 por familia: una held-out (00) y una de train (10)
PROMPT_GEN0 = "prompts/gen_0.md"
# KAIZEN_TASKS=reducido: subconjunto fijo y balanceado para gastar menos (p. ej. con Codex). Siempre las mismas
# tareas en todas las generaciones, para que la curva held-out sea comparable entre ellas.
TAREAS_REDUCIDAS_POR_FAMILIA = 5  # 5 held-out + 5 train por familia = 50 de 120


class CorridaOcupada(RuntimeError):
    """Ya hay otra corrida con el lock tomado."""


# ---------------------------------------------------------------------------
# Puntos de integración con Backend A (env, evals, history) y la IA Engineer (improve).
# Las firmas siguen el tutorial; si cambian, solo se tocan estas funciones.
# ---------------------------------------------------------------------------

def _tareas() -> list[dict]:
    from env.tareas import TAREAS
    return TAREAS


def tareas_de_corrida() -> list[dict] | None:
    """Tareas de gen0/next/loop: None = las 120; con KAIZEN_TASKS=reducido, las primeras 5 held-out y las
    primeras 5 de train de cada familia (el destilador sigue viendo solo train)."""
    if os.getenv("KAIZEN_TASKS", "todas").strip().lower() != "reducido":
        return None
    elegidas = []
    for tarea in _tareas():
        indice = int(tarea["id"].rsplit("_", 1)[1])  # coti_00..coti_23; las primeras 8 son held-out
        posicion = indice if tarea["split"] == "heldout" else indice - HELDOUT_PER_FAMILY
        if posicion < TAREAS_REDUCIDAS_POR_FAMILIA:
            elegidas.append(tarea)
    return elegidas


def _evaluar_semilla(spec: AgentSpec, semilla: int, tareas: list[dict] | None):
    from evaluation import evals
    trazas = evals.run_generation(spec, semilla, tareas)
    return evals.report(spec, semilla, trazas)


def _guardar_reportes(branch: str, reportes: list) -> None:
    from evaluation import history
    history.save_reports(branch, reportes)


def _destilar(padre: AgentSpec, trazas: list, branch: str, version_destilador: int, version_rubrica: int) -> AgentSpec:
    from improve import distiller
    return distiller.distill(padre, trazas, branch, version_destilador, version_rubrica, log=progress.linea)


def _calibrar_juez(trazas: list, version_rubrica: int, generacion: int, branch: str) -> int:
    from improve import meta_judge
    return meta_judge.calibrar(trazas, version_rubrica, generacion, branch, log=progress.linea)


def _quizas_reescribir_destilador(deltas: list[float], version: int, generacion: int, branch: str) -> int:
    from improve import meta_distiller
    return meta_distiller.quizas_reescribir(deltas, version, generacion, branch, log=progress.linea)


def _recalificar(trato: bool) -> None:
    from evaluation import rescore
    rescore.main(trato=trato)


def _exportar(dentro_de_corrida: bool = True) -> list[str]:
    """Escribe los JSON de la web. Fuera de una corrida (`run.py export`) no toca progress.json: marcar la
    fase dejaba corriendo=True sin nadie que lo cerrara, y la web deshabilitaba los botones de correr."""
    from evaluation import export
    if dentro_de_corrida:
        progress.fase("exportando")
        return export.export_all(log=progress.linea)
    return export.export_all()


# ---------------------------------------------------------------------------
# Lock: una sola corrida a la vez
# ---------------------------------------------------------------------------

_candado_corrida = None  # archivo con el candado del sistema, tomado mientras dura la corrida


def tomar_lock() -> None:
    """Toma el candado de corrida del sistema operativo y escribe .lock con el PID para la web.

    El candado lo mantiene el sistema, no el archivo: si run.py muere (crash, reinicio del servidor) se
    libera solo, y no hay ventana entre revisar y crear en la que dos corridas puedan entrar a la vez.
    """
    global _candado_corrida
    candado = archivos.intentar_candado(paths.CANDADO_CORRIDA)
    if candado is None:
        raise CorridaOcupada("Ya hay una corrida en curso")
    if paths.LOCK.exists():  # con el candado tomado, cualquier .lock previo es de una corrida que murió
        progress.linea("lock huérfano de una corrida anterior: se reemplaza")
    _candado_corrida = candado
    escribir_texto_atomico(paths.LOCK, str(os.getpid()))


def al_cancelar(_senal: int, _marco: object) -> None:
    """SIGTERM que manda /api/run al cancelar. Se cierra aquí y se sale con os._exit: los hilos de la
    evaluación no se detienen solos y la salida normal esperaría a que terminen todas sus llamadas al modelo.
    Si ya se destiló la generación pero no se evaluó, la siguiente corrida la evalúa (ver siguiente())."""
    progress.cancelar(MOTIVO_CANCELACION)
    soltar_lock()
    os._exit(SALIDA_CANCELADA)


def soltar_lock() -> None:
    global _candado_corrida
    if _candado_corrida is None:
        return
    paths.LOCK.unlink(missing_ok=True)
    archivos.soltar_candado(_candado_corrida)
    _candado_corrida = None


def escribir_texto_atomico(ruta: Path, texto: str) -> None:
    """Así la web nunca lee un .lock vacío a medio escribir."""
    temporal = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
    temporal.write_text(texto, encoding="utf-8")
    os.replace(temporal, ruta)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def spec_gen0(branch: str) -> AgentSpec:
    """La spec de gen 0 de la rama; si no existe, la crea con el prompt escrito a mano y las 8 tools base."""
    spec = almacen.cargar_spec(branch, 0)
    if spec is None:
        spec = AgentSpec(0, branch, None, PROMPT_GEN0, "single_react", list(BASE_TOOLS))
        almacen.guardar_spec(spec)
    return spec


def evaluar(spec: AgentSpec, semillas: list[int], tareas: list[dict] | None = None) -> None:
    progress.linea(f"evaluando {spec.branch}/gen_{spec.generation} con semillas {semillas}")
    reportes = [_evaluar_semilla(spec, s, tareas) for s in semillas]
    _guardar_reportes(spec.branch, reportes)
    _exportar()  # la web ve cada generación en cuanto termina


def deltas_heldout(branch: str) -> list[float]:
    from evaluation import export
    return [fila["delta"] for fila in export.filas_de_rama(branch)[1:]]


def siguiente(branch: str, semillas: list[int], tareas: list[dict] | None = None,
              meta_destilador: bool = True, commit: bool = False) -> AgentSpec:
    """Destila la generación siguiente a la última de la rama y la evalúa."""
    gens = almacen.generaciones(branch)
    if not gens:
        raise RuntimeError(f"La rama {branch} no tiene gen 0. Corre primero: python run.py gen0")
    padre = almacen.cargar_spec(branch, gens[-1])
    generacion = padre.generation + 1
    trazas = almacen.cargar_trazas(branch, padre.generation)
    if not trazas:
        if padre.generation == 0:
            raise RuntimeError(f"{branch}/gen_0 no tiene trazas. Corre primero: python run.py gen0")
        # La corrida anterior se cortó entre destilar y evaluar: se termina esa generación
        progress.linea(f"reanudando: {branch}/gen_{padre.generation} estaba destilada pero sin evaluar")
        evaluar(padre, semillas, tareas)
        return padre

    progress.fase("meta-juez")
    version_rubrica = _calibrar_juez(trazas, padre.rubric_version, generacion, branch)
    version_destilador = padre.distiller_prompt_version
    if meta_destilador:
        progress.fase("meta-destilador")
        version_destilador = _quizas_reescribir_destilador(deltas_heldout(branch), version_destilador,
                                                           generacion, branch)
    progress.fase("destilando")
    spec = _destilar(padre, trazas, branch, version_destilador, version_rubrica)
    almacen.guardar_spec(spec)
    _exportar()
    evaluar(spec, semillas, tareas)
    if commit:
        commit_generacion(spec)
    return spec


def smoke(semillas: list[int]) -> None:
    """Pipeline real sobre 10 tareas en la rama smoke, desde cero cada vez (no hereda de main)."""
    for carpeta in (paths.RUNS / RAMA_SMOKE, paths.SPECS / RAMA_SMOKE):
        shutil.rmtree(carpeta, ignore_errors=True)
    tareas = [t for t in _tareas() if t["id"].rsplit("_", 1)[1] in SMOKE_TAREAS_POR_FAMILIA]
    evaluar(spec_gen0(RAMA_SMOKE), semillas, tareas)
    siguiente(RAMA_SMOKE, semillas, tareas)


def loop(hasta: int, semillas: list[int], commit: bool) -> None:
    tareas = tareas_de_corrida()
    if not almacen.cargar_reportes(almacen.RAMA_PRINCIPAL):
        evaluar(spec_gen0(almacen.RAMA_PRINCIPAL), semillas, tareas)
    while almacen.generaciones(almacen.RAMA_PRINCIPAL)[-1] < hasta:
        siguiente(almacen.RAMA_PRINCIPAL, semillas, tareas, commit=commit)


def reset(simulado: bool) -> None:
    from core import reset as reset_mod
    rutas = reset_mod.plan() if simulado else reset_mod.aplicar()
    verbo = "borraría" if simulado else "borró"
    progress.linea(f"reset: {verbo} {len(rutas)} rutas")
    for ruta in rutas:
        print(f"{verbo}: {paths.rel(ruta)}")
    if not simulado:
        _exportar()


def commit_generacion(spec: AgentSpec) -> None:
    """Un commit por generación con lo que produjo (solo con --commit)."""
    mensaje = f"KAIZEN: {spec.branch}/gen_{spec.generation}"
    subprocess.run(["git", "add", str(paths.DATA)], cwd=paths.REPO, check=True)
    subprocess.run(["git", "commit", "-m", mensaje], cwd=paths.REPO, check=True)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="KAIZEN: fábrica de agentes que se mejora sola")
    ap.add_argument("cmd", choices=["smoke", "gen0", "next", "loop", "export", "reset", "rescore"])
    ap.add_argument("--seeds", default=None, help="p. ej. 1,2,3 (por defecto KAIZEN_SEEDS; smoke usa solo la primera)")
    ap.add_argument("--branch", default=almacen.RAMA_PRINCIPAL)
    ap.add_argument("--fork-from", type=int, default=None, help="solo con --branch control")
    ap.add_argument("--no-meta-distiller", action="store_true")
    ap.add_argument("--until", type=int, default=None, help="loop: última generación a producir")
    ap.add_argument("--dry", action="store_true", help="reset: solo lista lo que borraría")
    ap.add_argument("--trato", action="store_true", help="rescore: recalcula también la nota de trato (usa LLM)")
    ap.add_argument("--commit", action="store_true", help="un commit de git por generación")
    args = ap.parse_args(argv)
    if args.cmd == "loop" and args.until is None:
        ap.error("loop necesita --until N")
    if args.fork_from is not None and args.branch != almacen.CONTROL:
        ap.error("--fork-from solo aplica a --branch control")
    return args


def semillas_de(args: argparse.Namespace) -> list[int]:
    texto = args.seeds or os.getenv("KAIZEN_SEEDS", "1,2,3")
    semillas = [int(s) for s in texto.split(",") if s.strip()]
    return semillas[:1] if args.cmd == "smoke" and args.seeds is None else semillas


def ejecutar(args: argparse.Namespace) -> None:
    semillas = semillas_de(args)
    if args.cmd == "smoke":
        smoke(semillas)
    elif args.cmd == "gen0":
        evaluar(spec_gen0(args.branch), semillas, tareas_de_corrida())
    elif args.cmd == "next":
        if args.branch == almacen.CONTROL and not (paths.RUNS / almacen.CONTROL / "fork.json").exists():
            almacen.fijar_fork(args.fork_from if args.fork_from is not None else almacen.FORK_POR_DEFECTO)
        siguiente(args.branch, semillas, tareas_de_corrida(), meta_destilador=not args.no_meta_distiller,
                  commit=args.commit)
    elif args.cmd == "loop":
        loop(args.until, semillas, args.commit)
    elif args.cmd == "reset":
        reset(args.dry)
    elif args.cmd == "rescore":
        _recalificar(args.trato)
        _exportar()


def main(argv: list[str] | None = None) -> int:
    args = argumentos(argv)
    if args.cmd == "export":  # solo lee y escribe JSON: no necesita lock
        return SALIDA_ERROR if _exportar(dentro_de_corrida=False) else SALIDA_OK
    if args.cmd == "reset" and args.dry:
        reset(simulado=True)
        return SALIDA_OK
    try:
        tomar_lock()
    except CorridaOcupada as e:
        print(e, file=sys.stderr)
        return SALIDA_OCUPADO
    signal.signal(signal.SIGTERM, al_cancelar)
    try:
        progress.linea(f"run.py {' '.join(argv if argv is not None else sys.argv[1:])}")
        ejecutar(args)
        progress.terminar()
        return SALIDA_OK
    except llm.BudgetExceeded as e:
        progress.terminar(f"BudgetExceeded: {e}")
        return SALIDA_PRESUPUESTO
    except BaseException as e:  # incluye Ctrl+C: el motivo debe verse en la web
        progress.terminar(f"{type(e).__name__}: {e}")
        if isinstance(e, KeyboardInterrupt):
            return SALIDA_ERROR
        raise
    finally:
        soltar_lock()


if __name__ == "__main__":
    sys.exit(main())
