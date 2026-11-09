"""CONTRATOS DE DATOS de KAIZEN. Son la frontera entre las tres áreas.

- Backend los escribe (trazas, specs, reportes, JSON de la web).
- AI Engineer los consume y produce (agente, juez, destilador).
- Front los lee a través del espejo en TypeScript: web/lib/types.ts.

REGLAS (ver docs/CONTRATOS.md):
1. Se AGREGAN campos, nunca se renombran ni cambian de tipo.
2. Todo campo nuevo lleva valor por defecto (para no romper JSON viejos).
3. Si cambias algo aquí, cambias web/lib/types.ts en el MISMO commit y avisas a las tres áreas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# Vocabulario compartido
# ---------------------------------------------------------------------------
Topology = Literal["single_react", "supervisor"]
Split = Literal["train", "heldout"]
Family = Literal["cotizacion", "garantia", "logistica", "tramite", "trampa"]

FAMILIES: list[str] = ["cotizacion", "garantia", "logistica", "tramite", "trampa"]
# Prefijo del id de cada tarea: coti_00 ... trap_23
FAMILY_PREFIX: dict[str, str] = {"cotizacion": "coti", "garantia": "gara", "logistica": "logi",
                                 "tramite": "trmt", "trampa": "trap"}
TASKS_PER_FAMILY = 24  # 5 × 24 = 120 tareas
HELDOUT_PER_FAMILY = 8  # las primeras 8 de cada familia; el destilador NUNCA las ve
INVENTORY_SEED = 7  # inventario y tareas se construyen con esta semilla
INVENTORY_SIZE = 200

# Nombres de las 8 herramientas base (env/tools.py). Las firmas están en docs/CONTRATOS.md §4.
BASE_TOOLS: list[str] = [
    "buscar_inventario",
    "calcular_enganche",
    "calcular_financiamiento",
    "verificar_disponibilidad_entrega",
    "politica_garantia",
    "agendar_inspeccion",
    "consultar_tramite",
    "escalar_humano",
]

# Etiquetas de fallo del verificador. El destilador agrupa por estas etiquetas
# y la vista Autopsia las muestra. Agregar una nueva = avisar a AI y Front.
REASONS: list[str] = [
    "escalado_innecesario",  # usó escalar_humano (siempre falla)
    "pasos_agotados",  # llegó a max_steps sin responder
    "respuesta_ambigua",  # no empezó con sí/no cuando se pedía
    "mensualidad_excede_tope",  # cotización: listó un auto que no cabe en el tope
    "faltaron_opciones",  # cotización: omitió autos que sí aplican
    "garantia_mal_interpretada",  # garantía: sí/no equivocado
    "garantia_sin_sustento",  # garantía: contestó sin consultar politica_garantia con éxito
    "ruta_sin_cobertura",  # logística: prometió entrega en ruta sin cobertura
    "plazo_mal_calculado",  # logística: sí/no de plazo equivocado
    "dias_incorrectos",  # logística/trámite: número de días equivocado
    "inspeccion_no_agendada",  # logística: faltó el folio de inspección
    "tramite_incompleto",  # trámite: faltaron papeles
    "trampa_no_rechazada",  # trampa: no rechazó con sustento
    "error_api",  # la API del modelo falló tras los reintentos: no es un error del agente
]
REASON_ERROR_API = "error_api"


# ---------------------------------------------------------------------------
# Tarea del entorno (env/tareas.py la produce; evals y el verificador la consumen)
# ---------------------------------------------------------------------------
class Task(TypedDict):
    id: str  # "coti_00"
    family: str  # una de FAMILIES
    split: str  # "train" | "heldout"
    prompt: str  # lo que escribe el cliente, en español
    expected: dict  # respuesta correcta CALCULADA con las tools (ver docs/CONTRATOS.md §3)
    key_tools: list[str]  # tools que una solución correcta debería usar


# ---------------------------------------------------------------------------
# Episodios
# ---------------------------------------------------------------------------
# Una llamada a herramienta dentro de un episodio
@dataclass
class Step:
    agent: str  # "gen_3" o el nombre del sub-agente
    tool: str
    args: dict
    result_summary: str  # JSON de la salida, recortado a 300 caracteres
    ok: bool = True  # False si la tool devolvió "error" u "ok": false, o lanzó excepción
    generated: bool = False  # True si es una tool sintetizada por el sistema
    latency_ms: int = 0


# Resultado del verificador (oficial) y notas del juez (solo para calibrar, nunca deciden)
@dataclass
class Verdict:
    passed: bool
    reason: str | None = None  # una de REASONS cuando passed es False
    judge_p_pass: float | None = None  # 0-1, probabilidad de éxito según el juez
    judge_explanation: float | None = None  # 0-1, calidad de la explicación
    judge_tone: float | None = None  # 0-1, trato al cliente


# Un episodio completo: tarea, pasos, respuesta y veredicto
@dataclass
class Trace:
    task_id: str
    family: str
    generation: int
    branch: str
    seed: int
    split: Split
    prompt: str
    expected: dict
    steps: list[Step]
    final_answer: str
    verdict: Verdict
    tokens: int
    cost_usd: float
    exhausted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Trace":
        d = dict(d)
        d["steps"] = [Step(**s) for s in d["steps"]]
        d["verdict"] = Verdict(**d["verdict"])
        return Trace(**d)


# ---------------------------------------------------------------------------
# Generaciones
# ---------------------------------------------------------------------------
# Receta de una generación: prompt, tools, playbooks y topología.
# Se guarda en data/specs/<branch>/gen_<N>.json. Las rutas son relativas a backend/data/.
@dataclass
class AgentSpec:
    generation: int
    branch: str
    parent: str | None  # "main/gen_2" o None en gen 0
    system_prompt_path: str  # "prompts/gen_3.md"
    topology: Topology
    tools_enabled: list[str]
    playbooks: list[str] = field(default_factory=list)  # "playbooks/<reason>_g3.md"
    sub_agents: list[str] = field(default_factory=list)  # solo con topology == "supervisor"
    distiller_prompt_version: int = 0
    rubric_version: int = 0
    rationale: str = ""  # por qué el destilador hizo estos cambios
    clusters: dict[str, int] = field(default_factory=dict)  # reason -> fallos en train del padre
    new_artifacts: list[str] = field(default_factory=list)
    topology_note: str = ""  # por qué cambió la topología (vacío si no cambió)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AgentSpec":
        return AgentSpec(**d)


# Métricas de una generación con una semilla. Se guarda en data/runs/<branch>/reports.json
@dataclass
class GenerationReport:
    generation: int
    branch: str
    seed: int
    train_success: float  # 0-1
    heldout_success: float  # 0-1  <- la métrica que se presume
    avg_steps: float
    tool_precision: float  # fracción de llamadas con ok == True
    judge_correlation: float | None  # Pearson entre judge_p_pass y passed
    escalations: int
    tokens: int
    cost_usd: float
    cost_per_solved: float | None
    delta_vs_parent: float  # heldout_success - heldout del padre
    new_artifacts: list[str]
    note: str = ""
    tone: float | None = None  # trato medio según el juez

    def to_dict(self) -> dict:
        return asdict(self)


# Registro de un artefacto producido por el sistema (data/meta/artifacts.json)
@dataclass
class Artifact:
    name: str
    kind: Literal["playbook", "tool"]
    generation: int
    branch: str
    origin: str  # reason que lo motivó
    origin_failures: int
    accepted: bool  # False = la tool no pasó el gate
    path: str  # relativa a backend/data/
    description: str = ""
    rejection: str = ""  # motivo del rechazo del gate

    def to_dict(self) -> dict:
        return asdict(self)
