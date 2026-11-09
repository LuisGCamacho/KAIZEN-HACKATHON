import os
import sys

# Los tests importan desde backend/ igual que run.py y live.py (from env.inventario import ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- Backend B: rutas de datos temporales para los tests de plataforma ---
import pytest  # noqa: E402

from core import artifacts, llm, paths, progress  # noqa: E402

RUTAS_DE_DATOS = ("PROMPTS", "PLAYBOOKS", "SPECS", "META", "RUNS", "LIVE_RUNS", "TOOLS_GENERADAS", "TOOLS_RECHAZADAS",
                  "WEB_DATA")


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Redirige todas las rutas de paths.py a tmp_path/data y tmp_path/web."""
    raiz = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA", raiz)
    nuevas = {
        "PROMPTS": raiz / "prompts", "PLAYBOOKS": raiz / "playbooks", "SPECS": raiz / "specs",
        "META": raiz / "meta", "RUNS": raiz / "runs", "LIVE_RUNS": raiz / "runs" / "live",
        "TOOLS_GENERADAS": raiz / "tools" / "generated", "TOOLS_RECHAZADAS": raiz / "tools" / "rejected",
        "WEB_DATA": tmp_path / "web",
    }
    for nombre in RUTAS_DE_DATOS:
        monkeypatch.setattr(paths, nombre, nuevas[nombre])
        nuevas[nombre].mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "LOCK", nuevas["RUNS"] / ".lock")
    monkeypatch.setattr(paths, "SPEND", nuevas["RUNS"] / "spend.json")
    monkeypatch.setattr(paths, "REGISTRO", nuevas["RUNS"] / "registro.log")
    monkeypatch.setattr(paths, "PROGRESS", nuevas["WEB_DATA"] / "progress.json")
    # Módulos que copiaron una ruta al importarse
    monkeypatch.setattr(llm, "ARCHIVO_GASTO", paths.SPEND)
    monkeypatch.setattr(artifacts, "REGISTRO", nuevas["META"] / "artifacts.json")
    monkeypatch.setattr(progress, "_estado", {"corriendo": False, "error": None, "lineas": []})
    return raiz
