import { AppShell } from "../app-shell";
import { DataGate, MachineBadge, PanelEmpty, StateBadge } from "../ui/data-display";
import type { LineageFile } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function branchName(data: LineageFile): string | null {
  if (data.branches.main?.length) return "main";
  return Object.keys(data.branches)[0] ?? null;
}
export function LineageView({ state }: { state: ViewState<LineageFile> }) {
  return <AppShell active="/linaje" section="Evidencia" title="Linaje"
    description="¿Qué causa medida llevó a cada cambio? Revisa la cadena de generaciones y la evolución de sus prompts.">
    <DataGate state={state} source="public/data/lineage.json" title="El historial de generaciones aparecerá aquí"
      description="Cada nodo mostrará su relación con la generación anterior, la topología y el motivo del cambio.">
      {data => {
        const branch = branchName(data);
        const generations = branch ? data.branches[branch] ?? [] : [];
        if (generations.length === 0) return <PanelEmpty>No hay generaciones para esta rama.</PanelEmpty>;
        return <>
          <div className="lineage-branch"><span className="lbl">Rama</span><code>{branch}</code></div>
          <ol className="lineage-list">{generations.map((generation, index) => {
            const previous = generations[index - 1];
            const hasMetaRewrite = previous != null && (
              generation.distiller_prompt_version !== previous.distiller_prompt_version ||
              generation.rubric_version !== previous.rubric_version
            );
            return <li className={index === generations.length - 1 ? "lineage-current" : ""} key={`${generation.branch}-${generation.generation}`}>
              <article className="card lineage-card">
                <div className="lineage-node">Gen {generation.generation}</div>
                <div className="lineage-head">
                  <div><p className="lbl">{generation.topology.replaceAll("_", " ")}</p><h2>Generación {generation.generation}</h2></div>
                  <div className="artifact-badges">{hasMetaRewrite && <MachineBadge />}<StateBadge>{generation.tools_enabled.length} herramientas</StateBadge></div>
                </div>
                <p className="lineage-rationale">{generation.rationale || generation.topology_note || "Sin rationale exportado."}</p>
                <div className="lineage-meta"><span>{generation.failures_total} fallos analizados</span><span>Padre: {generation.parent ?? "ninguno"}</span></div>
              </article>
            </li>;
          })}</ol>
          <section className="card prompt-comparison">
            <div className="section-heading"><div><p className="lbl">Prompt del agente</p><h2>Versión anterior y actual</h2></div></div>
            <div className="prompt-columns">
              <div><h3>Anterior</h3><pre className="code-panel"><code>{generations.at(-1)?.parent_prompt || "Sin prompt anterior."}</code></pre></div>
              <div><h3>Actual</h3><pre className="code-panel"><code>{generations.at(-1)?.prompt || "Sin prompt exportado."}</code></pre></div>
            </div>
          </section>
          {data.distiller_prompt.length > 0 && <section className="card prompt-history">
            <div className="section-heading"><div><p className="lbl">Meta-destilador</p><h2>Versiones del prompt</h2></div></div>
            <ul className="version-list">{data.distiller_prompt.map(version => <li key={version.version}>
              <code>v{version.version}</code><span>{version.change || version.diagnosis || "Revisión del prompt"}</span>{version.generation != null && <span>Gen {version.generation}</span>}
            </li>)}</ul>
          </section>}
        </>;
      }}
    </DataGate>
  </AppShell>;
}
