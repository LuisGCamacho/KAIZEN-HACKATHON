import type { Generation } from "../../lib/types";
import { signedPct } from "../../lib/format";

export function DeltaBars({ rows }: { rows: Generation[] }) {
  const deltas = [...rows].sort((a, b) => a.generation - b.generation).filter(row => row.generation > 0);
  if (deltas.length === 0) return <div className="panel-empty"><p>Los deltas aparecerán al comparar generaciones.</p></div>;
  const max = Math.max(...deltas.map(row => Math.abs(row.delta)), 0.0001);
  return <div className="delta-list" aria-label="Cambio en éxito held-out por generación">
    {deltas.map(row => <div className="delta-row" key={row.generation}>
      <span className="delta-label">Gen {row.generation - 1} → {row.generation}</span>
      <span className="delta-track"><span className={`delta-fill ${row.delta < 0 ? "negative" : ""}`} style={{ width: `${Math.max(2, Math.abs(row.delta) / max * 50)}%` }} /></span>
      <span className="delta-value">{signedPct(row.delta)}</span>
      {row.meta_rewrite && <span className="delta-machine">Reescritura del destilador</span>}
    </div>)}
  </div>;
}
