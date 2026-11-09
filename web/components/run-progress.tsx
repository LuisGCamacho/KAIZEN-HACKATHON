"use client";

import { useJson } from "../lib/use-json";
import type { Progress } from "../lib/types";

const POLLING_MS = 2_000;

/** Pasos de una corrida en el orden en que run.py los ejecuta (fase de progress.json → explicación). */
const PASOS: { fase: string; titulo: string; detalle: string }[] = [
  { fase: "meta-juez", titulo: "Meta-juez",
    detalle: "Compara al juez LLM con el verificador; si discrepan mucho, reescribe la rúbrica del juez." },
  { fase: "meta-destilador", titulo: "Meta-destilador",
    detalle: "Si la mejora se estancó, el sistema reescribe las instrucciones de su propio destilador." },
  { fase: "destilando", titulo: "Destilando",
    detalle: "Agrupa los fallos de práctica, escribe playbooks, intenta crear herramientas nuevas y reescribe el prompt del agente." },
  { fase: "evaluando", titulo: "Evaluando",
    detalle: "La nueva generación resuelve las tareas y el verificador califica cada una, sin IA." },
  { fase: "exportando", titulo: "Publicando",
    detalle: "Actualiza la curva, la autopsia, el linaje y las trazas." },
];

function pasoActual(progreso: Progress): number {
  return PASOS.findIndex(paso => paso.fase === progreso.fase);
}

/** Panel visible en todas las vistas mientras hay una corrida, o cuando la última terminó con error. */
export function RunProgress() {
  const estado = useJson("progress.json", { cadaMs: POLLING_MS });
  if (estado.status !== "ready") return null;
  const progreso = estado.data;
  if (!progreso.corriendo && !progreso.error) return null;

  if (!progreso.corriendo) {
    return <section className="card run-progress run-progress-error" role="alert">
      <p className="lbl">La última corrida se detuvo</p>
      <p className="run-progress-error-texto">{progreso.error}</p>
      <p className="run-progress-nota">Las generaciones anteriores no se perdieron. Al lanzar una corrida nueva este aviso desaparece.</p>
    </section>;
  }

  const actual = pasoActual(progreso);
  const evaluando = progreso.fase === "evaluando" && progreso.total;
  const porcentaje = evaluando ? Math.round(((progreso.hechas ?? 0) / progreso.total!) * 100) : null;
  return <section className="card run-progress" aria-live="polite" aria-label="Corrida en curso">
    <div className="run-progress-cabeza">
      <div>
        <p className="lbl">Corrida en curso{progreso.generacion !== undefined && progreso.fase === "evaluando" ? ` · generación ${progreso.generacion}` : ""}</p>
        <h2>{actual >= 0 ? PASOS[actual].titulo : (progreso.fase ?? "Preparando")}</h2>
        {actual >= 0 && <p className="run-progress-detalle">{PASOS[actual].detalle}</p>}
      </div>
      {evaluando && <div className="run-progress-cifra">
        <span className="stat">{progreso.hechas ?? 0}/{progreso.total}</span>
        <span className="run-progress-nota">{progreso.aciertos ?? 0} correctas hasta ahora</span>
      </div>}
    </div>
    {porcentaje !== null && <div className="run-progress-barra" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={porcentaje}>
      <span style={{ width: `${porcentaje}%` }} />
    </div>}
    <ol className="run-progress-pasos">
      {PASOS.map((paso, indice) => <li key={paso.fase}
        className={indice === actual ? "paso-actual" : actual >= 0 && indice < actual ? "paso-hecho" : ""}>
        <span aria-hidden="true">{actual >= 0 && indice < actual ? "✓" : indice + 1}</span>{paso.titulo}
      </li>)}
    </ol>
    {progreso.lineas.length > 0 && <ol className="run-progress-lineas">
      {progreso.lineas.slice(-3).map((linea, indice) => <li key={`${indice}-${linea}`}><code>{linea}</code></li>)}
    </ol>}
  </section>;
}
