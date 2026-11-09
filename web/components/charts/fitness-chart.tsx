import type { Generation } from "../../lib/types";
import { pct } from "../../lib/format";

const WIDTH = 760;
const HEIGHT = 280;
const LEFT = 56;
const RIGHT = 20;
const TOP = 20;
const BOTTOM = 42;

function xAt(index: number, count: number): number {
  return count < 2 ? (LEFT + WIDTH - RIGHT) / 2 : LEFT + index * (WIDTH - LEFT - RIGHT) / (count - 1);
}
function yAt(value: number): number {
  const bounded = Math.max(0, Math.min(1, value));
  return HEIGHT - BOTTOM - bounded * (HEIGHT - TOP - BOTTOM);
}
function linePoints(rows: Generation[], key: "heldout_mean" | "train_mean"): string {
  return rows.map((row, index) => `${xAt(index, rows.length)},${yAt(row[key])}`).join(" ");
}
export function FitnessChart({ rows, label = "Tasa de éxito por generación" }: { rows: Generation[]; label?: string }) {
  if (rows.length === 0) return <div className="panel-empty"><span className="panel-empty-mark" aria-hidden="true">—</span><p>La gráfica aparecerá cuando haya resultados de evaluación.</p></div>;
  const sorted = [...rows].sort((a, b) => a.generation - b.generation);
  const summary = sorted.map(row => `generación ${row.generation}: ${pct(row.heldout_mean)} held-out`).join(", ");
  return <div className="chart-wrap">
    <svg className="fitness-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${label}. ${summary}`}>
      <title>{`${label}. ${summary}`}</title>
      {[0, 0.5, 1].map(value => <g key={value} className="chart-grid">
        <line x1={LEFT} x2={WIDTH - RIGHT} y1={yAt(value)} y2={yAt(value)} />
        <text x={LEFT - 10} y={yAt(value) + 4} textAnchor="end">{pct(value)}</text>
      </g>)}
      {sorted.map((row, index) => {
        const x = xAt(index, sorted.length);
        const low = yAt(row.heldout_mean - row.heldout_std);
        const high = yAt(row.heldout_mean + row.heldout_std);
        return <g className="chart-error" key={row.generation}>
          <line x1={x} x2={x} y1={low} y2={high} />
          <line x1={x - 4} x2={x + 4} y1={low} y2={low} />
          <line x1={x - 4} x2={x + 4} y1={high} y2={high} />
        </g>;
      })}
      <polyline className="chart-train" points={linePoints(sorted, "train_mean")} />
      <polyline className="chart-heldout" points={linePoints(sorted, "heldout_mean")} />
      {sorted.map((row, index) => <g key={row.generation}>
        <circle className="chart-point" cx={xAt(index, sorted.length)} cy={yAt(row.heldout_mean)} r="4" />
        <text className="chart-x-label" x={xAt(index, sorted.length)} y={HEIGHT - 12} textAnchor="middle">Gen {row.generation}</text>
      </g>)}
    </svg>
    <div className="chart-legend"><span className="legend-heldout">Held-out</span><span className="legend-train">Train</span><span className="legend-error">Desviación entre semillas</span></div>
  </div>;
}
