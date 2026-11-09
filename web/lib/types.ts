// CONTRATOS · Espejo de backend/core/contracts.py y de lo que escribe backend/evaluation/export.py.
// Regla: se agregan campos, nunca se renombran ni cambian de tipo. Si cambias algo aquí,
// cambia backend/core/contracts.py en el MISMO commit.
// Ver docs/CONTRATOS.md.

// ---------- Vocabulario ----------
export type Topology = "single_react" | "supervisor";
export type Split = "train" | "heldout";
export type Family = "cotizacion" | "garantia" | "logistica" | "tramite" | "trampa";

export const REASONS = [
  "escalado_innecesario",
  "pasos_agotados",
  "respuesta_ambigua",
  "mensualidad_excede_tope",
  "faltaron_opciones",
  "garantia_mal_interpretada",
  "garantia_sin_sustento",
  "ruta_sin_cobertura",
  "plazo_mal_calculado",
  "dias_incorrectos",
  "inspeccion_no_agendada",
  "tramite_incompleto",
  "trampa_no_rechazada",
] as const;
export type Reason = (typeof REASONS)[number];

// ---------- Episodios (core/contracts.py) ----------
export type Step = {
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  result_summary: string;
  ok: boolean;
  generated: boolean;
  latency_ms: number;
};

export type Verdict = {
  passed: boolean;
  reason: string | null;
  judge_p_pass: number | null;
  judge_explanation: number | null;
  judge_tone: number | null;
};

export type Trace = {
  task_id: string;
  family: string;
  generation: number;
  branch: string;
  seed: number;
  split: Split;
  prompt: string;
  expected: Record<string, unknown>;
  steps: Step[];
  final_answer: string;
  verdict: Verdict;
  tokens: number;
  cost_usd: number;
  exhausted: boolean;
};

export type AgentSpec = {
  generation: number;
  branch: string;
  parent: string | null;
  system_prompt_path: string;
  topology: Topology;
  tools_enabled: string[];
  playbooks: string[];
  sub_agents: string[];
  distiller_prompt_version: number;
  rubric_version: number;
  rationale: string;
  clusters: Record<string, number>;
  new_artifacts: string[];
  topology_note: string;
};

export type GenerationReport = {
  generation: number;
  branch: string;
  seed: number;
  train_success: number;
  heldout_success: number;
  avg_steps: number;
  tool_precision: number;
  judge_correlation: number | null;
  escalations: number;
  tokens: number;
  cost_usd: number;
  cost_per_solved: number | null;
  delta_vs_parent: number;
  new_artifacts: string[];
  note: string;
  tone: number | null;
};

// ---------- Archivos de web/public/data (evaluation/export.py) ----------

/** Una fila por generación: media y desviación entre semillas. */
export type Generation = {
  branch: string;
  generation: number;
  seeds: number;
  heldout_mean: number;
  heldout_std: number;
  train_mean: number;
  train_std: number;
  avg_steps: number;
  tool_precision: number;
  judge_correlation: number | null;
  escalations: number;
  cost_usd: number;
  cost_per_solved: number | null;
  tone: number | null;
  delta: number;
  topology: Topology;
  topology_changed: boolean;
  distiller_prompt_version: number;
  rubric_version: number;
  meta_rewrite: boolean;
  new_artifacts: string[];
  note: string;
};

/** reports.json */
export type ReportsFile = {
  branches: string[];
  generations: Generation[];
  seeds: GenerationReport[];
  spend_usd: number;
};

/** clusters.json es Cluster[] */
export type Cluster = {
  branch: string;
  reason: string;
  per_generation: number[];
  generations: number[];
  closed_by: string | null;
  open: boolean;
};

/** artifacts.json es Artifact[] */
export type Artifact = {
  name: string;
  kind: "playbook" | "tool";
  generation: number;
  branch: string;
  origin: string;
  origin_failures: number;
  accepted: boolean;
  path: string;
  description: string;
  rejection: string;
  content?: string; // texto del playbook
  code?: string; // código de la tool
  tests?: string; // tests de la tool
};

export type LineageGeneration = AgentSpec & {
  parent_topology: Topology | null;
  agents: { name: string; role: string; tools: string[] }[];
  failures_total: number;
  prompt: string;
  parent_prompt: string;
  playbook_texts: Record<string, string>;
};

export type MetaVersion = {
  version: number;
  text: string;
  parent_text: string;
  generation?: number;
  branch?: string;
  deltas?: number[];
  diagnosis?: string;
  change?: string;
  correlation_before?: number | null;
};

/** lineage.json */
export type LineageFile = {
  branches: Record<string, LineageGeneration[]>;
  distiller_prompt: MetaVersion[];
  rubric: MetaVersion[];
};

export type Comparison = {
  task_id: string;
  family: string;
  split: Split;
  prompt: string;
  expected: Record<string, unknown>;
  before: Trace;
  after: Trace;
};

/** traces.json */
export type TracesFile = { branch: string; before: number; after: number | null; items: Comparison[] };

/** progress.json (core/progress.py, se lee cada 2 s) */
export type Progress = {
  corriendo: boolean;
  fase?: string;
  generacion?: number;
  branch?: string;
  semilla?: number;
  hechas?: number;
  total?: number;
  aciertos?: number;
  exito_parcial?: number;
  error?: string | null;
  lineas: string[];
};

/** Nombre de cada archivo y su tipo, para useJson(). */
export type DataFiles = {
  "reports.json": ReportsFile;
  "clusters.json": Cluster[];
  "artifacts.json": Artifact[];
  "lineage.json": LineageFile;
  "traces.json": TracesFile;
  "progress.json": Progress;
};

// ---------- Demo en vivo: eventos NDJSON de POST /api/live (backend/live.py) ----------
type LiveBase = { t: number; agent?: string };
export type LiveEvent = LiveBase &
  (
    | { type: "start"; generation: number; branch: string; topology: Topology; sub_agents?: string[]; tools: string[]; playbooks: number }
    | { type: "delegate"; to: string; query: string }
    | { type: "tool_call"; tool: string; args: Record<string, unknown>; generated: boolean }
    | { type: "tool_result"; tool: string; summary: string; ok: boolean; ms: number }
    | { type: "message"; text: string }
    | { type: "final"; text: string; tokens: number; cost_usd: number; steps: number; exhausted: boolean }
    | { type: "error"; message: string }
  );

/** Cuerpo de POST /api/live */
export type LiveRequest = {
  messages: { role: "user" | "assistant"; content: string }[];
  generation: number | "best" | "latest";
  branch: string;
};
