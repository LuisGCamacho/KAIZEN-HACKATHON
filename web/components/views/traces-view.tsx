import { AppShell } from "../app-shell";
import { DataGate, GateBadge, MachineBadge, PanelEmpty } from "../ui/data-display";
import { num, usd } from "../../lib/format";
import type { TracesFile, Trace } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function Episode({ trace, label }: { trace: Trace; label: string }) {
  return <section className="episode-panel">
    <header className="episode-heading"><div><p className="lbl">{label}</p><h3>Gen {trace.generation} · <code>{trace.branch}</code></h3></div>
      <GateBadge accepted={trace.verdict.passed} /></header>
    <ol className="step-list">{trace.steps.length ? trace.steps.map((step, index) => <li key={`${step.agent}-${step.tool}-${index}`}>
      <div className="step-meta"><span>Paso {index + 1}</span><code>{step.agent} · {step.tool}</code>{step.generated && <MachineBadge />}</div>
      <p>{step.result_summary}</p>
    </li>) : <li className="muted-value">Sin pasos exportados.</li>}</ol>
    <div className="episode-final"><p className="lbl">Respuesta final</p><p>{trace.final_answer || "—"}</p></div>
    <div className="episode-stats"><span>{trace.steps.length} pasos</span><span>{trace.tokens.toLocaleString("es-MX")} tokens</span><span>{usd(trace.cost_usd)}</span></div>
  </section>;
}
export function TracesView({ state }: { state: ViewState<TracesFile> }) {
  return <AppShell active="/trazas" section="Comparación" title="Trazas de episodio"
    description="Compara dos generaciones sobre la misma tarea y revisa por ti mismo qué esperaba el verificador.">
    <DataGate state={state} source="public/data/traces.json" title="Aún no hay episodios comparables"
      description="Cada comparación mostrará la tarea, el resultado esperado y los pasos de ambas generaciones.">
      {file => file.items.length === 0 ? <PanelEmpty>No hay comparaciones en el archivo exportado.</PanelEmpty> :
        <div className="trace-list">{file.items.map(item => <article className="card trace-card" key={item.task_id}>
          <header className="trace-task"><div><p className="lbl">{item.family} · {item.split}</p><h2>{item.task_id}</h2></div>
            <div className="trace-prompt"><p className="lbl">Tarea</p><p>{item.prompt}</p></div>
          </header>
          <section className="expected-result"><p className="lbl">Qué esperaba el verificador</p><pre className="code-panel"><code>{JSON.stringify(item.expected, null, 2)}</code></pre></section>
          <div className="trace-columns"><Episode trace={item.before} label="Antes" /><Episode trace={item.after} label="Después" /></div>
          <div className="trace-summary"><span>Pasos: {item.before.steps.length} → {item.after.steps.length}</span>
            <span>Tokens: {num(item.before.tokens, 0)} → {num(item.after.tokens, 0)}</span>
            <span>Escalados: {item.before.steps.filter(step => step.tool === "escalar_humano").length} → {item.after.steps.filter(step => step.tool === "escalar_humano").length}</span></div>
        </article>)}</div>}
    </DataGate>
  </AppShell>;
}
