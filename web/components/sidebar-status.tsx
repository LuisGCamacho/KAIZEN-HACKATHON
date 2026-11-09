"use client";

import { useEffect, useState } from "react";

import { usd } from "../lib/format";
import type { Gasto } from "../lib/types";
import { useJson } from "../lib/use-json";
import { claveGuardada, useRun, type Comando } from "../lib/use-run";
import { ConfirmarAccion } from "./confirmar-accion";

const POLLING_PROGRESO_MS = 3_000;
const POLLING_REPORTES_MS = 10_000;
const POLLING_GASTO_MS = 10_000;
const UMBRAL_AVISO_TOPE = 0.9; // desde el 90 % del tope la barra se marca como casi agotada

/** Botón del sidebar: evalúa la gen 0 si main no tiene datos; si ya los tiene, produce la siguiente. */
export function RunButton() {
  const reportes = useJson("reports.json", { cadaMs: POLLING_REPORTES_MS });
  const progreso = useJson("progress.json", { cadaMs: POLLING_PROGRESO_MS });
  const { lanzar, enviando, aviso, pideClave } = useRun();
  const [pedirClave, setPedirClave] = useState(false);

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
    <button className="new-run-button" type="button" disabled={enviando || corriendo}
      onClick={() => { setPedirClave(pideClave || !claveGuardada()); setConfirmando(true); }} aria-expanded={confirmando}>
      <span aria-hidden="true">+</span> {comando === "gen0" ? "Evaluar gen 0" : "Nueva generación"}
    </button>
    {confirmando && !corriendo && <ConfirmarAccion explicacion={explicacion} accion="Lanzar" pedirClave={pedirClave}
      enviando={enviando} cancelar={() => setConfirmando(false)}
      confirmar={clave => { setConfirmando(false); void lanzar(comando, clave); }} />}
    {aviso && <p className="sidebar-footnote" role="status">{aviso}</p>}
  </>;
}

function millones(tokens: number): string {
  return `${(tokens / 1_000_000).toLocaleString("es-MX", { maximumFractionDigits: 2 })}M`;
}

/** Medidor de gasto (/api/gasto, incluye lo del chat en vivo) y estado de la corrida en curso (progress.json). */
export function SidebarBudget() {
  const progreso = useJson("progress.json", { cadaMs: POLLING_PROGRESO_MS });
  const [gasto, setGasto] = useState<Gasto | null>(null);
  useEffect(() => {
    let vigente = true;
    const leer = () => fetch("/api/gasto", { cache: "no-store" })
      .then(r => (r.ok ? r.json() as Promise<Gasto> : null))
      .then(g => { if (vigente && g) setGasto(g); })
      .catch(() => undefined); // sin conexión se conserva la última lectura
    void leer();
    const intervalo = setInterval(leer, POLLING_GASTO_MS);
    return () => { vigente = false; clearInterval(intervalo); };
  }, []);

  const datos = progreso.status === "ready" ? progreso.data : null;
  let estado = "Sin corridas registradas";
  if (datos?.corriendo) {
    const avance = datos.total ? ` · ${datos.hechas ?? 0}/${datos.total}` : "";
    estado = `${datos.fase ?? "En curso"}${avance}`;
  } else if (datos?.error) {
    estado = datos.fase === "cancelada" ? "Última corrida cancelada" : `Error: ${datos.error}`;
  } else if (datos?.fase === "terminado") {
    estado = "Última corrida terminada";
  }

  // Con Codex no hay USD: lo que se agota son los tokens frente a CODEX_MAX_TOKENS
  const conCodex = gasto?.proveedor === "codex";
  const usado = conCodex ? gasto.tokens : gasto?.usd ?? 0;
  const tope = conCodex ? gasto.tope_tokens : gasto?.presupuesto_usd ?? null;
  const fraccion = tope ? Math.min(1, usado / tope) : null;
  return <div className="sidebar-note" aria-label="Gasto y estado de la corrida">
    <div className="sidebar-note-label">{conCodex ? "Tokens de Codex usados" : "Gasto de API acumulado"}</div>
    <div className="budget-value">
      {gasto === null ? "—" : conCodex ? millones(gasto.tokens) : usd(gasto.usd)}
      {tope !== null && gasto !== null && <span className="budget-tope"> / {conCodex ? millones(tope) : usd(tope)}</span>}
    </div>
    {fraccion !== null && <div className={`budget-barra ${fraccion >= UMBRAL_AVISO_TOPE ? "budget-casi" : ""}`} role="progressbar"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fraccion * 100)} aria-label="Uso del tope">
      <span style={{ width: `${fraccion * 100}%` }} />
    </div>}
    {fraccion !== null && fraccion >= UMBRAL_AVISO_TOPE && <p className="budget-aviso">Casi en el tope: el chat y las corridas se detendrán al llegar.</p>}
    <div className="sidebar-note-value" aria-live="polite">
      <span className={`status-dot ${datos?.corriendo ? "status-active" : ""}`} /> {estado}
    </div>
  </div>;
}
