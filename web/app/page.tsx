import type { ReactNode } from "react";
import { AppShell } from "../components/app-shell";

const metrics = [
  { label: "Éxito held-out", note: "Tareas que el destilador no ve" },
  { label: "Pasos por tarea", note: "Promedio de ejecución" },
  { label: "Correlación del juez", note: "Juez frente al verificador" },
  { label: "Último delta", note: "Cambio frente a la generación anterior" },
];

function MetricCard({ label, note }: { label: string; note: string }) {
  return <article className="card metric-card">
    <p className="lbl">{label}</p><div className="stat">—</div><p className="cmp">{note}</p>
  </article>;
}
function EmptyPanel({ children }: { children: ReactNode }) {
  return <div className="panel-empty"><span className="panel-empty-mark" aria-hidden="true">—</span><p>{children}</p></div>;
}
export default function EvolucionPage() {
  return <AppShell active="/" section="Operaciones automotrices · held-out" title="Evolución"
    description="Sigue el rendimiento de cada generación y revisa la evidencia que explica sus cambios.">
    <div className="overview-actions">
      <button className="btn" type="button" disabled aria-describedby="actions-note">Exportar CSV</button>
      <button className="btn btn-primary" type="button" disabled aria-describedby="actions-note">Nueva generación</button>
      <span className="action-note" id="actions-note">Disponible cuando el backend genere resultados.</span>
    </div>
    <div className="grid g4" aria-label="Métricas de evaluación">
      {metrics.map(metric => <MetricCard key={metric.label} {...metric} />)}
    </div>
    <section className="card overview-chart" aria-labelledby="success-title">
      <div className="ch"><div><p className="lbl">Rendimiento</p><h2 id="success-title">Tasa de éxito por generación</h2></div>
        <div className="legend" aria-label="Series previstas"><span>Held-out</span><span>Train</span><span>Variación entre semillas</span></div></div>
      <EmptyPanel>La gráfica aparecerá cuando haya resultados de evaluación exportados.</EmptyPanel>
    </section>
    <div className="grid g2 overview-lower">
      <section className="card" aria-labelledby="delta-title">
        <div className="ch"><div><p className="lbl">Progreso</p><h2 id="delta-title">Delta por generación</h2></div></div>
        <EmptyPanel>Los cambios entre generaciones aparecerán aquí.</EmptyPanel>
      </section>
      <section className="card" aria-labelledby="artifacts-title">
        <div className="ch"><div><p className="lbl">Evidencia</p><h2 id="artifacts-title">Artefactos generados</h2></div></div>
        <EmptyPanel>Las herramientas y playbooks, incluidos los rechazados, aparecerán aquí.</EmptyPanel>
        <p className="panel-source">Fuente prevista <code>web/public/data/artifacts.json</code></p>
      </section>
    </div>
    <section className="card activity-panel" aria-labelledby="activity-title">
      <header className="activity-heading"><div><p className="lbl">Registro</p><h2 id="activity-title">Actividad reciente</h2></div><span className="activity-status"><span className="status-dot" />Sin actividad</span></header>
      <EmptyPanel>El registro se llenará cuando se conecte una corrida real.</EmptyPanel>
    </section>
    <p className="overview-note">La métrica oficial es el éxito en held-out, medido por el verificador programático. El juez LLM se muestra solo como referencia de calibración.</p>
  </AppShell>;
}
