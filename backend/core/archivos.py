"""Escritura atómica de JSON: la interfaz hace polling y no debe leer un archivo a medias."""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator

# En Windows, os.replace falla si otro proceso (la web) tiene el destino abierto en ese instante
INTENTOS_REEMPLAZO = 5
ESPERA_REEMPLAZO_S = 0.05


def escribir_json(path: Path, datos: Any) -> None:
    """Escribe datos en un temporal junto a path y luego lo renombra encima de path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Un temporal por proceso e hilo: con un nombre fijo, dos escritores se renombraban el archivo entre sí
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    for intento in range(INTENTOS_REEMPLAZO):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if intento == INTENTOS_REEMPLAZO - 1:
                raise
            time.sleep(ESPERA_REEMPLAZO_S)


def _bloquear(candado: BinaryIO, esperar: bool) -> bool:
    """Toma el candado exclusivo del sistema operativo sobre el archivo abierto. Sin esperar, devuelve
    False si otro proceso lo tiene. El sistema lo libera solo si el proceso muere: no deja candados huérfanos."""
    if os.name == "nt":
        import msvcrt
        candado.seek(0)
        modo = msvcrt.LK_LOCK if esperar else msvcrt.LK_NBLCK
        while True:
            try:
                msvcrt.locking(candado.fileno(), modo, 1)
                return True
            except OSError:
                if not esperar:
                    return False
                # LK_LOCK se rinde tras ~10 s de espera; se sigue esperando
    import fcntl
    try:
        fcntl.flock(candado.fileno(), fcntl.LOCK_EX if esperar else fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _desbloquear(candado: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt
        candado.seek(0)
        msvcrt.locking(candado.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(candado.fileno(), fcntl.LOCK_UN)


@contextmanager
def candado_de_archivo(path: Path) -> Iterator[None]:
    """Exclusión entre procesos (run.py y cada live.py) sobre path, usando un archivo <path>.lock aparte.
    Bloquea hasta obtenerlo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a+b") as candado:
        _bloquear(candado, esperar=True)
        try:
            yield
        finally:
            _desbloquear(candado)


def intentar_candado(path: Path) -> BinaryIO | None:
    """Toma el candado de path sin esperar y lo deja tomado: devuelve el archivo abierto, que hay que pasar
    a soltar_candado(). None si otro proceso ya lo tiene."""
    path.parent.mkdir(parents=True, exist_ok=True)
    candado = open(path, "a+b")
    if _bloquear(candado, esperar=False):
        return candado
    candado.close()
    return None


def soltar_candado(candado: BinaryIO) -> None:
    _desbloquear(candado)
    candado.close()


def leer_json(path: Path, por_defecto: Any) -> Any:
    """Devuelve el contenido de path, o por_defecto si no existe."""
    if not path.exists():
        return por_defecto
    return json.loads(path.read_text(encoding="utf-8"))
