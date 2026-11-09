import type { ReactNode } from "react";
import { EmptyState } from "../empty-state";
import type { ViewState } from "../../lib/view-state";

export function DataGate<T>({ state, source, title, description, children }: {
  state: ViewState<T>;
  source: string;
  title: string;
  description: string;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <section className="data-state" aria-busy="true" aria-label="Cargando">
    <div className="skeleton skeleton-title" /><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row short" />
  </section>;
  if (state.status === "error") return <section className="data-error" role="alert">
    <p className="lbl">No se pudieron cargar los datos</p><p>{state.message}</p>
    <p>Vuelve a consultar esta fuente cuando termine la exportación.</p><code>{source}</code>
  </section>;
  if (state.status === "empty") return <EmptyState title={title} description={description} source={source}
    command="python run.py smoke" note="Ejecuta el comando desde la carpeta backend. La corrida usa el proveedor de modelos configurado." />;
  return <>{children(state.data)}</>;
}
export function PanelEmpty({ children }: { children: ReactNode }) {
  return <div className="panel-empty"><span className="panel-empty-mark" aria-hidden="true">—</span><p>{children}</p></div>;
}
export function MetricCard({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="card metric-card"><p className="lbl">{label}</p><div className="stat">{value}</div><p className="cmp">{note}</p></article>;
}
export function GateBadge({ accepted }: { accepted: boolean }) {
  return <span className={`badge gate-badge ${accepted ? "gate-accepted" : "gate-rejected"}`}>
    <span aria-hidden="true">{accepted ? "✓" : "×"}</span>{accepted ? "Aprobada" : "Rechazada"}
  </span>;
}
export function StateBadge({ children, state }: { children: ReactNode; state?: "open" | "closed" }) {
  return <span className={`badge state-badge ${state ? `state-${state}` : ""}`}>{children}</span>;
}
export function MachineBadge() {
  return <span className="badge machine-badge"><span aria-hidden="true" />Autoría de la máquina</span>;
}
export function SectionHeading({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return <div className="section-heading"><div>{eyebrow && <p className="lbl">{eyebrow}</p>}<h2>{title}</h2></div>{children}</div>;
}
