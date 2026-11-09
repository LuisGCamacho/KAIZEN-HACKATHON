"use client";

import { useState } from "react";

import { AppShell } from "../app-shell";
import { DataGate, MachineBadge, PanelEmpty, StateBadge } from "../ui/data-display";
import { diffLineas } from "../../lib/diff";
import type { LineageFile, MetaVersion } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function branchName(data: LineageFile): string | null {
  if (data.branches.main?.length) return "main";
  return Object.keys(data.branches)[0] ?? null;
}

/** Prompt anterior contra actual, línea por línea: + agregada, − quitada (no solo color). */
function DiffPrompt({ anterior, actual }: { anterior: string; actual: string }) {
  if (!anterior) return <pre className="code-panel"><code>{actual || "Sin prompt exportado."}</code></pre>;
  const lineas = diffLineas(anterior, actual);
  const agregadas = lineas.filter(l => l.tipo === "agregada").length;
  const quitadas = lineas.filter(l => l.tipo === "quitada").length;
  return <>
    <p className="diff-resumen"><span>+{agregadas} {agregadas === 1 ? "línea agregada" : "líneas agregadas"}</span>
      <span>−{quitadas} {quitadas === 1 ? "línea quitada" : "líneas quitadas"}</span></p>
    <pre className="code-panel diff-panel" aria-label="Diferencias del prompt"><code>
      {lineas.map((linea, indice) => <span key={indice} className={`diff-linea diff-${linea.tipo}`}>
        <span className="diff-signo" aria-hidden="true">{linea.tipo === "agregada" ? "+" : linea.tipo === "quitada" ? "−" : " "}</span>
        <span className="sr-only">{linea.tipo === "agregada" ? "Agregada: " : linea.tipo === "quitada" ? "Quitada: " : ""}</span>
        <span className="diff-texto">{linea.texto || " "}</span>{"\n"}
      </span>)}
    </code></pre>
  </>;
}

function HistorialMeta({ titulo, eyebrow, versiones }: { titulo: string; eyebrow: string; versiones: MetaVersion[] }) {
  if (versiones.length <= 1) return null; // solo la v0 escrita a mano: no hubo reescrituras
  return <section className="card prompt-history">
    <div className="section-heading"><div><p className="lbl">{eyebrow}</p><h2>{titulo}</h2></div></div>
    <ul className="version-list">{versiones.map(version => <li key={version.version}>
      <code>v{version.version}</code>
      <span>{version.version === 0 ? "Escrita a mano" : version.change || version.diagnosis || "Reescrita por el meta-loop"}</span>
      {version.generation != null && <span>Gen {version.generation}{version.branch ? ` · ${version.branch}` : ""}</span>}
      {version.version > 0 && <MachineBadge />}
    </li>)}</ul>
  </section>;
}

export function LineageView({ state }: { state: ViewState<LineageFile> }) {
  const [elegida, setElegida] = useState<number | null>(null); // null = la última generación
  return <AppShell active="/linaje" section="Evidencia" title="Linaje"
    description="¿Qué causa medida llevó a cada cambio? Revisa la cadena de generaciones y la evolución de sus prompts.">
    <DataGate state={state} source="public/data/lineage.json" title="El historial de generaciones aparecerá aquí"
      description="Cada nodo mostrará su relación con la generación anterior, la topología y el motivo del cambio.">
      {data => {
        const branch = branchName(data);
        const generations = branch ? data.branches[branch] ?? [] : [];
        if (generations.length === 0) return <PanelEmpty>No hay generaciones para esta rama.</PanelEmpty>;
        const seleccionada = generations.find(g => g.generation === elegida) ?? generations.at(-1)!;
        return <>
          <div className="lineage-branch"><span className="lbl">Rama</span><code>{branch}</code>
            <span className="lineage-ayuda">Elige una generación para ver qué cambió en su prompt.</span></div>
          <ol className="lineage-list">{generations.map((generation, index) => {
            const previous = generations[index - 1];
            const hasMetaRewrite = previous != null && (
              generation.distiller_prompt_version !== previous.distiller_prompt_version ||
              generation.rubric_version !== previous.rubric_version
            );
            const activa = generation.generation === seleccionada.generation;
            return <li className={activa ? "lineage-current" : ""} key={`${generation.branch}-${generation.generation}`}>
              <button type="button" className="card lineage-card lineage-boton" aria-pressed={activa}
                onClick={() => setElegida(generation.generation)}>
                <div className="lineage-node">Gen {generation.generation}</div>
                <div className="lineage-head">
                  <div><p className="lbl">{generation.topology.replaceAll("_", " ")}</p><h2>Generación {generation.generation}</h2></div>
                  <div className="artifact-badges">{hasMetaRewrite && <MachineBadge />}<StateBadge>{generation.tools_enabled.length} herramientas</StateBadge></div>
                </div>
                <p className="lineage-rationale">{generation.rationale || generation.topology_note || "Sin rationale exportado."}</p>
                <div className="lineage-meta"><span>{generation.failures_total} fallos analizados</span><span>Padre: {generation.parent ?? "ninguno"}</span>
                  {generation.new_artifacts.length > 0 && <span>{generation.new_artifacts.length} artefactos nuevos</span>}</div>
              </button>
            </li>;
          })}</ol>
          <section className="card prompt-comparison">
            <div className="section-heading"><div><p className="lbl">Prompt del agente · generación {seleccionada.generation}</p>
              <h2>{seleccionada.parent_prompt ? `Cambios frente a ${seleccionada.parent ?? "su padre"}` : "Prompt escrito a mano"}</h2></div></div>
            <DiffPrompt anterior={seleccionada.parent_prompt} actual={seleccionada.prompt} />
          </section>
          <HistorialMeta eyebrow="Meta-destilador" titulo="Versiones del prompt del destilador" versiones={data.distiller_prompt} />
          <HistorialMeta eyebrow="Meta-juez" titulo="Versiones de la rúbrica del juez" versiones={data.rubric} />
        </>;
      }}
    </DataGate>
  </AppShell>;
}
