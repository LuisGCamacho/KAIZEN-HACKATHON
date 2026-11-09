"use client";

import { usd } from "../lib/format";
import { useJson } from "../lib/use-json";
import { useRun, type Comando } from "../lib/use-run";

const POLLING_PROGRESO_MS = 3_000;
const POLLING_REPORTES_MS = 10_000;

/** Botón del sidebar: evalúa la gen 0 si main no tiene datos; si ya los tiene, produce la siguiente. */
export function RunButton() {
  const reportes = useJson("reports.json", { cadaMs: POLLING_REPORTES_MS });
  const progreso = useJson("progress.json", { cadaMs: POLLING_PROGRESO_MS });
  const { lanzar, enviando, aviso } = useRun();

  const corriendo = progreso.status === "ready" && progreso.data.corriendo;
  const tieneMain = reportes.status === "ready" && reportes.data.generations.some(g => g.branch === "main");
  const comando: Comando = tieneMain ? "next" : "gen0";

  return <>
    <button className="new-run-button" type="button" disabled={enviando || corriendo} onClick={() => lanzar(comando)}
      title={comando === "gen0" ? "Evalúa la generación 0 en main" : "Destila y evalúa la siguiente generación de main"}>
      <span aria-hidden="true">+</span> {comando === "gen0" ? "Evaluar gen 0" : "Nueva generación"}
    </button>
    {aviso && <p className="sidebar-footnote" role="status">{aviso}</p>}
  </>;
}

/** Gasto acumulado (spend_usd de reports.json) y estado de la corrida en curso (progress.json). */
export function SidebarBudget() {
  const reportes = useJson("reports.json", { cadaMs: POLLING_REPORTES_MS });
  const progreso = useJson("progress.json", { cadaMs: POLLING_PROGRESO_MS });

  const datos = progreso.status === "ready" ? progreso.data : null;
  const gasto = reportes.status === "ready" ? reportes.data.spend_usd : null;
  let estado = "Sin corridas registradas";
  if (datos?.corriendo) {
    const avance = datos.total ? ` · ${datos.hechas ?? 0}/${datos.total}` : "";
    estado = `${datos.fase ?? "En curso"}${avance}`;
  } else if (datos?.error) {
    estado = `Error: ${datos.error}`;
  } else if (datos?.fase === "terminado") {
    estado = "Última corrida terminada";
  }

  return <div className="sidebar-note" aria-label="Estado de los datos">
    <div className="sidebar-note-label">Gasto de API acumulado</div>
    <div className="budget-value">{usd(gasto)}</div>
    <div className="sidebar-note-value" aria-live="polite">
      <span className={`status-dot ${datos?.corriendo ? "status-active" : ""}`} /> {estado}
    </div>
  </div>;
}
