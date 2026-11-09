"use client";

/**
 * Conecta las vistas (components/views, presentacionales) con los JSON del backend vía useJson.
 * Cada vista recibe un ViewState: cargando, vacío (el backend aún no exportó), error o datos.
 */
import { listaVacia, useJson } from "../lib/use-json";
import { useRun } from "../lib/use-run";
import { AutopsyView } from "./views/autopsy-view";
import { EvolutionView } from "./views/evolution-view";
import { LineageView } from "./views/lineage-view";
import { ToolsView } from "./views/tools-view";
import { TracesView } from "./views/traces-view";

const POLLING_MS = 5_000; // vistas que cambian al terminar cada generación
const POLLING_PROGRESO_MS = 2_000; // el registro en vivo de la corrida

export function EvolucionConectada() {
  const reports = useJson("reports.json", { cadaMs: POLLING_MS, esVacio: r => r.generations.length === 0 });
  const artifacts = useJson("artifacts.json", { cadaMs: POLLING_MS, esVacio: listaVacia });
  const progress = useJson("progress.json", { cadaMs: POLLING_PROGRESO_MS });
  const { lanzar, enviando, aviso } = useRun();
  const corriendo = progress.status === "ready" && progress.data.corriendo;
  // Igual que el sidebar: sin gen 0 en main no hay nada que destilar, así que primero se evalúa la línea base
  const generacionesMain = reports.status === "ready"
    ? reports.data.generations.filter(g => g.branch === "main").map(g => g.generation) : [];
  const ultima = generacionesMain.length ? Math.max(...generacionesMain) : null;
  // Misma confirmación que el botón del sidebar: la acción tarda minutos y gasta créditos
  const confirmarYLanzar = () => {
    const explicacion = ultima === null
      ? "Se evaluará la generación 0 (el agente escrito a mano)."
      : `Se destilará la generación ${ultima + 1} a partir de los fallos de la ${ultima} y se evaluará en las mismas tareas. Tarda unos 10 minutos y gasta créditos de la cuenta.`;
    if (window.confirm(`${explicacion}\n\n¿Lanzar la corrida?`)) void lanzar(ultima === null ? "gen0" : "next");
  };
  return <EvolutionView reports={reports} artifacts={artifacts} progress={progress}
    generar={{ lanzar: confirmarYLanzar, deshabilitado: enviando || corriendo, aviso }} />;
}

export function AutopsiaConectada() {
  return <AutopsyView state={useJson("clusters.json", { cadaMs: POLLING_MS, esVacio: listaVacia })} />;
}

export function HerramientasConectada() {
  return <ToolsView state={useJson("artifacts.json", { cadaMs: POLLING_MS, esVacio: listaVacia })} />;
}

export function LinajeConectado() {
  const state = useJson("lineage.json", {
    cadaMs: POLLING_MS,
    esVacio: l => Object.values(l.branches).every(generaciones => generaciones.length === 0),
  });
  return <LineageView state={state} />;
}

export function TrazasConectadas() {
  // Sin polling: la comparación solo cambia al terminar una generación y se lee completa al entrar
  return <TracesView state={useJson("traces.json", { esVacio: t => t.items.length === 0 })} />;
}
