"""CLI de KAIZEN: orquesta evaluar → destilar → evaluar y exporta los JSON de la web.

    python run.py smoke | gen0 | next [--branch B] [--fork-from N] [--no-meta-distiller]
    python run.py loop --until N | export | reset [--dry] | rescore [--trato]

Códigos de salida (docs/CONTRATOS.md §7): 0 ok, 1 error, 3 ya hay una corrida, 4 presupuesto agotado.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import almacen, llm, paths, progress  # noqa: E402
from core.contracts import BASE_TOOLS, AgentSpec  # noqa: E402

SALIDA_OK, SALIDA_ERROR, SALIDA_OCUPADO, SALIDA_PRESUPUESTO = 0, 1, 3, 4
RAMA_SMOKE = "smoke"
SMOKE_TAREAS_POR_FAMILIA = ("00", "10")  # 2 por familia: una held-out (00) y una de train (10)
PROMPT_GEN0 = "prompts/gen_0.md"


class CorridaOcupada(RuntimeError):
    """Ya hay otra corrida con el lock tomado."""


# ---------------------------------------------------------------------------
# Puntos de integración con Backend A (env, evals, history) y la IA Engineer (improve).
# Las firmas siguen el tutorial; si cambian, solo se tocan estas funciones.
# ---------------------------------------------------------------------------

def _tareas() -> list[dict]:
    from env.tareas import TAREAS
    return TAREAS


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


def _exportar() -> list[str]:
    from evaluation import export
    progress.fase("exportando")
    return export.export_all(log=progress.linea)


# ---------------------------------------------------------------------------
# Lock: una sola corrida a la vez
# ---------------------------------------------------------------------------

def proceso_vivo(pid: int) -> bool:
    """True si el proceso existe. En Windows no se usa os.kill: con señal 0 termina el proceso."""
    if os.name == "nt":
        import ctypes
        consulta_limitada, sigue_activo = 0x1000, 259  # PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE
        handle = ctypes.windll.kernel32.OpenProcess(consulta_limitada, False, pid)
        if not handle:
            return False
        codigo = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo))
        ctypes.windll.kernel32.CloseHandle(handle)
        return codigo.value == sigue_activo
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # existe, pero es de otro usuario
        return True
    return True


def tomar_lock() -> None:
    """Crea data/runs/.lock con el PID. Un lock de un proceso muerto (reinicio, crash) se reemplaza.

    La creación es atómica (O_EXCL): si dos run.py arrancan a la vez, solo uno obtiene el lock.
    """
    if paths.LOCK.exists():
        contenido = paths.LOCK.read_text(encoding="utf-8").strip()
        if contenido.isdigit() and proceso_vivo(int(contenido)):
            raise CorridaOcupada(f"Ya hay una corrida en curso (PID {contenido})")
        progress.linea(f"lock huérfano de PID {contenido or '?'}: se reemplaza")
        paths.LOCK.unlink(missing_ok=True)
    try:
        descriptor = os.open(paths.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise CorridaOcupada("Otra corrida tomó el lock al mismo tiempo") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
        lock.write(str(os.getpid()))


def soltar_lock() -> None:
    if paths.LOCK.exists() and paths.LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
        paths.LOCK.unlink()


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
    if not almacen.cargar_reportes(almacen.RAMA_PRINCIPAL):
        evaluar(spec_gen0(almacen.RAMA_PRINCIPAL), semillas)
    while almacen.generaciones(almacen.RAMA_PRINCIPAL)[-1] < hasta:
        siguiente(almacen.RAMA_PRINCIPAL, semillas, commit=commit)


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
        evaluar(spec_gen0(args.branch), semillas)
    elif args.cmd == "next":
        if args.branch == almacen.CONTROL and not (paths.RUNS / almacen.CONTROL / "fork.json").exists():
            almacen.fijar_fork(args.fork_from if args.fork_from is not None else almacen.FORK_POR_DEFECTO)
        siguiente(args.branch, semillas, meta_destilador=not args.no_meta_distiller, commit=args.commit)
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
        return SALIDA_ERROR if _exportar() else SALIDA_OK
    if args.cmd == "reset" and args.dry:
        reset(simulado=True)
        return SALIDA_OK
    try:
        tomar_lock()
    except CorridaOcupada as e:
        print(e, file=sys.stderr)
        return SALIDA_OCUPADO
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
