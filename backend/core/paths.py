"""Rutas del proyecto. Todo se resuelve desde backend/, sin importar desde dónde se ejecute el script."""
from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
ENV_FILE = BACKEND / ".env"

DATA = BACKEND / "data"  # todo lo que escribe el sistema; aquí no vive código escrito a mano
PROMPTS = DATA / "prompts"  # prompt de sistema de cada generación + estilo.md
PLAYBOOKS = DATA / "playbooks"  # procedimientos que escribe el destilador
SPECS = DATA / "specs"  # AgentSpec de cada generación, por rama
META = DATA / "meta"  # rúbrica del juez y prompt del destilador, versionados
RUNS = DATA / "runs"  # trazas, reportes, gasto y lock de corrida
LIVE_RUNS = RUNS / "live"  # conversaciones de la demo; no entran al aprendizaje
TOOLS_GENERADAS = DATA / "tools" / "generated"  # tools que pasaron el gate
TOOLS_RECHAZADAS = DATA / "tools" / "rejected"  # tools que no pasaron, como evidencia
WEB_DATA = REPO / "web" / "public" / "data"  # JSON que lee la interfaz

LOCK = RUNS / ".lock"  # existe mientras hay una corrida; guarda su PID. /api/run lo revisa
SPEND = RUNS / "spend.json"  # contrato: {"usd": float}, el gasto real acumulado
REGISTRO = RUNS / "registro.log"  # copia en disco de las líneas de progress.json
PROGRESS = WEB_DATA / "progress.json"  # estado en vivo de la corrida (core/progress.py)

for carpeta in (PROMPTS, PLAYBOOKS, SPECS, META, RUNS, LIVE_RUNS, TOOLS_GENERADAS, TOOLS_RECHAZADAS, WEB_DATA):
    carpeta.mkdir(parents=True, exist_ok=True)


def rel(ruta: str | Path) -> str:
    """Ruta relativa a data/ con separadores "/", que es como se guarda en specs y artefactos."""
    return Path(ruta).resolve().relative_to(DATA).as_posix()
