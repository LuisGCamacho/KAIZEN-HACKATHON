import type { Generation } from "../../lib/types";
import { pct } from "../../lib/format";

const WIDTH = 760;
const HEIGHT = 280;
const LEFT = 56;
const RIGHT = 20;
const TOP = 28;
const BOTTOM = 42;
const SEPARACION_ETIQUETA = 12; // px entre el punto y su porcentaje
const DIFERENCIA_VISIBLE = 0.005; // por debajo de medio punto, train y held-out se dibujan encimadas
const MARGEN_ETIQUETA = 90; // px desde el borde derecho en que las etiquetas se alinean hacia adentro

/** Ancla de texto que no se sale del gráfico: las etiquetas cerca del borde derecho crecen hacia la izquierda. */
function ancla(x: number): "middle" | "end" {
  return x > WIDTH - RIGHT - MARGEN_ETIQUETA / 2 ? "end" : "middle";
}

function yAt(value: number): number {
  const bounded = Math.max(0, Math.min(1, value));
  return HEIGHT - BOTTOM - bounded * (HEIGHT - TOP - BOTTOM);
}

/** Generaciones propias de control: las anteriores al fork las hereda de main con los mismos valores. */
function propiasDeControl(control: Generation[], main: Generation[]): Generation[] {
  const deMain = new Map(main.map(row => [row.generation, row]));
  return control.filter(row => {
    const igual = deMain.get(row.generation);
    return !igual || igual.heldout_mean !== row.heldout_mean || igual.train_mean !== row.train_mean;
  }).sort((a, b) => a.generation - b.generation);
}

/**
 * Éxito por generación de la rama principal. Con `control` (ablación sin meta-destilador) se dibuja su línea
 * gris desde el fork, como comparación; las generaciones donde el meta-loop reescribió algo llevan una marca.
 */
export function FitnessChart({ rows, control = [], label = "Tasa de éxito por generación" }: {
  rows: Generation[];
  control?: Generation[];
  label?: string;
}) {
  if (rows.length === 0) return <div className="panel-empty"><span className="panel-empty-mark" aria-hidden="true">—</span><p>La gráfica aparecerá cuando haya resultados de evaluación.</p></div>;
  const sorted = [...rows].sort((a, b) => a.generation - b.generation);
  const controlPropio = propiasDeControl(control, sorted);
  // Eje X por número de generación, compartido entre main y control
  const generaciones = [...new Set([...sorted, ...controlPropio].map(row => row.generation))].sort((a, b) => a - b);
  const xAt = (generacion: number) => generaciones.length < 2
    ? (LEFT + WIDTH - RIGHT) / 2
    : LEFT + generaciones.indexOf(generacion) * (WIDTH - LEFT - RIGHT) / (generaciones.length - 1);
  const puntos = (filas: Generation[], key: "heldout_mean" | "train_mean") =>
    filas.map(row => `${xAt(row.generation)},${yAt(row[key])}`).join(" ");
  // La línea de control sale del punto de main donde se separó (la generación anterior a su primera propia)
  const origen = controlPropio.length ? sorted.filter(row => row.generation < controlPropio[0].generation).at(-1) : undefined;
  const lineaControl = origen ? [origen, ...controlPropio] : controlPropio;
  const reescrituras = sorted.filter(row => row.meta_rewrite);

  // Explica lo que no se ve, para que la gráfica no parezca rota
  const notas = [
    ...(sorted.every(row => Math.abs(row.train_mean - row.heldout_mean) < DIFERENCIA_VISIBLE)
      ? ["La línea de train queda debajo de la de held-out porque valen lo mismo en todas las generaciones."] : []),
    ...(sorted.every(row => row.seeds <= 1) ? ["Con una sola semilla no hay barras de desviación."] : []),
  ];
  const summary = sorted.map(row => `generación ${row.generation}: ${pct(row.heldout_mean)} held-out`).join(", ");
  return <div className="chart-wrap">
    <svg className="fitness-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${label}. ${summary}`}>
      <title>{`${label}. ${summary}`}</title>
      {[0, 0.5, 1].map(value => <g key={value} className="chart-grid">
        <line x1={LEFT} x2={WIDTH - RIGHT} y1={yAt(value)} y2={yAt(value)} />
        <text x={LEFT - 10} y={yAt(value) + 4} textAnchor="end">{pct(value)}</text>
      </g>)}
      {reescrituras.map(row => <g key={`meta-${row.generation}`} className="chart-meta">
        <line x1={xAt(row.generation)} x2={xAt(row.generation)} y1={TOP - 12} y2={HEIGHT - BOTTOM} />
        <text x={xAt(row.generation) + (ancla(xAt(row.generation)) === "end" ? -4 : 4)} y={TOP - 14}
          textAnchor={ancla(xAt(row.generation)) === "end" ? "end" : "start"}>meta-loop</text>
      </g>)}
      {sorted.map(row => {
        const x = xAt(row.generation);
        const low = yAt(row.heldout_mean - row.heldout_std);
        const high = yAt(row.heldout_mean + row.heldout_std);
        return <g className="chart-error" key={row.generation}>
          <line x1={x} x2={x} y1={low} y2={high} />
          <line x1={x - 4} x2={x + 4} y1={low} y2={low} />
          <line x1={x - 4} x2={x + 4} y1={high} y2={high} />
        </g>;
      })}
      {lineaControl.length > 1 && <polyline className="chart-control" points={puntos(lineaControl, "heldout_mean")} />}
      {controlPropio.map(row => <g key={`control-${row.generation}`}>
        <circle className="chart-control-point" cx={xAt(row.generation)} cy={yAt(row.heldout_mean)} r="3" />
        <text className="chart-value chart-value-train" x={xAt(row.generation)} y={yAt(row.heldout_mean) + SEPARACION_ETIQUETA + 8} textAnchor={ancla(xAt(row.generation))}>{`control ${pct(row.heldout_mean)}`}</text>
      </g>)}
      <polyline className="chart-train" points={puntos(sorted, "train_mean")} />
      <polyline className="chart-heldout" points={puntos(sorted, "heldout_mean")} />
      {sorted.map(row => <g key={row.generation}>
        <circle className="chart-point" cx={xAt(row.generation)} cy={yAt(row.heldout_mean)} r="4" />
        <text className="chart-value" x={xAt(row.generation)} y={yAt(row.heldout_mean) - SEPARACION_ETIQUETA} textAnchor={ancla(xAt(row.generation))}>{pct(row.heldout_mean)}</text>
        {Math.abs(row.train_mean - row.heldout_mean) >= DIFERENCIA_VISIBLE && controlPropio.length === 0 &&
          <text className="chart-value chart-value-train" x={xAt(row.generation)} y={yAt(row.train_mean) + SEPARACION_ETIQUETA + 8} textAnchor={ancla(xAt(row.generation))}>{`train ${pct(row.train_mean)}`}</text>}
      </g>)}
      {generaciones.map(generacion => <text key={`x-${generacion}`} className="chart-x-label" x={xAt(generacion)} y={HEIGHT - 12} textAnchor="middle">Gen {generacion}</text>)}
    </svg>
    <div className="chart-legend">
      <span className="legend-heldout">Held-out</span><span className="legend-train">Train</span>
      {lineaControl.length > 1 && <span className="legend-control">Control (sin meta-destilador)</span>}
      {reescrituras.length > 0 && <span className="legend-meta">Reescritura del meta-loop</span>}
      <span className="legend-error">Desviación entre semillas</span>
    </div>
    {notas.length > 0 && <p className="chart-note">{notas.join(" ")}</p>}
  </div>;
}
