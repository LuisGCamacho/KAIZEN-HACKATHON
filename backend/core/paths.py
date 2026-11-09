"""Todas las rutas de KAIZEN en un solo lugar. Importarlo crea las carpetas que faltan."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/
REPO = ROOT.parent

# Todo lo que el sistema escribe vive bajo data/; aquí no hay código escrito a mano
DATA = ROOT / "data"
PROMPTS = DATA / "prompts"
PLAYBOOKS = DATA / "playbooks"
SPECS = DATA / "specs"
META = DATA / "meta"
RUNS = DATA / "runs"
LIVE = RUNS / "live"  # conversaciones de la demo; no entran al aprendizaje
GENERATED = DATA / "tools" / "generated"
REJECTED = DATA / "tools" / "rejected"

LOCK = RUNS / ".lock"  # existe mientras hay una corrida; /api/run lo revisa
SPEND = RUNS / "spend.json"  # gasto real acumulado: {"usd": float}
REGISTRO = RUNS / "registro.log"  # copia en disco de las líneas de progress.json

# Lo que lee la interfaz
WEB_DATA = REPO / "web" / "public" / "data"
PROGRESS = WEB_DATA / "progress.json"

for carpeta in (PROMPTS, PLAYBOOKS, SPECS, META, LIVE, GENERATED, REJECTED, WEB_DATA):
    carpeta.mkdir(parents=True, exist_ok=True)


def rel(path: str | Path) -> str:
    """Ruta relativa a data/ con '/': así se guarda en specs y artefactos, igual en Windows y Linux."""
    return Path(path).resolve().relative_to(DATA).as_posix()
