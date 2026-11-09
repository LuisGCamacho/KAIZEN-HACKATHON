"use client";

import { useState } from "react";

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
  const [confirmando, setConfirmando] = useState(false);
  const generacionesMain = reportes.status === "ready"
    ? reportes.data.generations.filter(g => g.branch === "main").map(g => g.generation) : [];
  const ultima = generacionesMain.length ? Math.max(...generacionesMain) : null;
  const comando: Comando = ultima === null ? "gen0" : "next";
  // La acción gasta créditos y tarda minutos: se explica qué va a pasar antes de lanzarla
  const explicacion = ultima === null
    ? "Se evaluará la generación 0 (el agente escrito a mano) en las tareas de la corrida."
    : `Se destilará la generación ${ultima + 1} a partir de los fallos de la ${ultima} y se evaluará en las mismas tareas. Tarda unos 10 minutos y gasta créditos de la cuenta.`;

  return <>
    <button className="new-run-button" type="button" disabled={enviando || corriendo} onClick={() => setConfirmando(true)}
      aria-expanded={confirmando}>
      <span aria-hidden="true">+</span> {comando === "gen0" ? "Evaluar gen 0" : "Nueva generación"}
    </button>
    {confirmando && !corriendo && <div className="run-confirm" role="dialog" aria-label="Confirmar corrida">
      <p>{explicacion}</p>
      <div className="run-confirm-acciones">
        <button className="btn btn-primary" type="button" disabled={enviando}
          onClick={() => { setConfirmando(false); void lanzar(comando); }}>Lanzar</button>
        <button className="btn" type="button" onClick={() => setConfirmando(false)}>Cancelar</button>
      </div>
    </div>}
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
