"use client";

import { useState } from "react";

import { AppShell } from "../app-shell";
import { DataGate, GateBadge, MachineBadge, PanelEmpty } from "../ui/data-display";
import type { Artifact } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const body = artifact.code ?? artifact.content ?? artifact.description;
  return <article className={`card artifact-card ${artifact.accepted ? "" : "artifact-rejected"}`}>
    <header className="artifact-header">
      <div><p className="lbl">{artifact.kind === "tool" ? "Herramienta" : "Playbook"} · Gen {artifact.generation}</p>
        <h2 className={artifact.accepted ? "" : "rejected-name"}>{artifact.name}</h2></div>
      <div className="artifact-badges"><MachineBadge /><GateBadge accepted={artifact.accepted} /></div>
    </header>
    <p className="artifact-description">{artifact.description}</p>
    <div className="artifact-origin"><span>Cluster de origen</span><code>{artifact.origin || "—"}</code><span>{artifact.origin_failures} fallos</span></div>
    {body ? <pre className="code-panel"><code>{body}</code></pre> : <PanelEmpty>Este artefacto no contiene código ni texto exportado.</PanelEmpty>}
    {!artifact.accepted && artifact.rejection && <p className="rejection-reason"><span>Motivo del rechazo</span>{artifact.rejection}</p>}
  </article>;
}
type Filtro = { gate: "todas" | "aprobadas" | "rechazadas"; tipo: "todos" | "tool" | "playbook" };

const OPCIONES_GATE: { valor: Filtro["gate"]; etiqueta: string }[] = [
  { valor: "todas", etiqueta: "Todas" }, { valor: "aprobadas", etiqueta: "Aprobadas" }, { valor: "rechazadas", etiqueta: "Rechazadas" },
];
const OPCIONES_TIPO: { valor: Filtro["tipo"]; etiqueta: string }[] = [
  { valor: "todos", etiqueta: "Todo" }, { valor: "tool", etiqueta: "Herramientas" }, { valor: "playbook", etiqueta: "Playbooks" },
];

function pasaFiltro(artifact: Artifact, filtro: Filtro): boolean {
  if (filtro.gate === "aprobadas" && !artifact.accepted) return false;
  if (filtro.gate === "rechazadas" && artifact.accepted) return false;
  return filtro.tipo === "todos" || artifact.kind === filtro.tipo;
}

function Filtros({ artifacts, filtro, cambiar }: { artifacts: Artifact[]; filtro: Filtro; cambiar: (f: Filtro) => void }) {
  const cuenta = (gate: Filtro["gate"]) => artifacts.filter(a => pasaFiltro(a, { gate, tipo: filtro.tipo })).length;
  return <div className="filtros" role="group" aria-label="Filtrar artefactos">
    <div className="filtro-grupo">{OPCIONES_GATE.map(o => <button key={o.valor} type="button" className="chip-filtro"
      aria-pressed={filtro.gate === o.valor} onClick={() => cambiar({ ...filtro, gate: o.valor })}>{o.etiqueta} <span>{cuenta(o.valor)}</span></button>)}</div>
    <div className="filtro-grupo">{OPCIONES_TIPO.map(o => <button key={o.valor} type="button" className="chip-filtro"
      aria-pressed={filtro.tipo === o.valor} onClick={() => cambiar({ ...filtro, tipo: o.valor })}>{o.etiqueta}</button>)}</div>
  </div>;
}

export function ToolsView({ state }: { state: ViewState<Artifact[]> }) {
  const [filtro, setFiltro] = useState<Filtro>({ gate: "todas", tipo: "todos" });
  return <AppShell active="/herramientas" section="Artefactos" title="Herramientas generadas"
    description="Inspecciona el código que produjo el sistema, su cluster de origen y el resultado de su gate.">
    <DataGate state={state} source="public/data/artifacts.json" title="Todavía no hay artefactos para revisar"
      description="Se mostrarán herramientas y playbooks aceptados y rechazados, con el motivo de cada decisión.">
      {artifacts => {
        if (artifacts.length === 0) return <div className="panel-empty"><p>No hay artefactos en el archivo exportado.</p></div>;
        const visibles = artifacts.filter(a => pasaFiltro(a, filtro));
        return <>
          <Filtros artifacts={artifacts} filtro={filtro} cambiar={setFiltro} />
          {visibles.length === 0 ? <PanelEmpty>Ningún artefacto coincide con el filtro.</PanelEmpty>
            : <div className="artifact-grid">{visibles.map(artifact => <ArtifactCard key={`${artifact.branch}-${artifact.path}`} artifact={artifact} />)}</div>}
        </>;
      }}
    </DataGate>
  </AppShell>;
}
