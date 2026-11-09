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
export function ToolsView({ state }: { state: ViewState<Artifact[]> }) {
  return <AppShell active="/herramientas" section="Artefactos" title="Herramientas generadas"
    description="Inspecciona el código que produjo el sistema, su cluster de origen y el resultado de su gate.">
    <DataGate state={state} source="public/data/artifacts.json" title="Todavía no hay artefactos para revisar"
      description="Se mostrarán herramientas y playbooks aceptados y rechazados, con el motivo de cada decisión.">
      {artifacts => artifacts.length === 0 ? <div className="panel-empty"><p>No hay artefactos en el archivo exportado.</p></div> :
        <div className="artifact-grid">{artifacts.map(artifact => <ArtifactCard key={artifact.path} artifact={artifact} />)}</div>}
    </DataGate>
  </AppShell>;
}
