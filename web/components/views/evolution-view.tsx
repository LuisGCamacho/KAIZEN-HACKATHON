import type { ReactNode } from "react";
import { AppShell } from "../app-shell";
import { DeltaBars } from "../charts/delta-bars";
import { FitnessChart } from "../charts/fitness-chart";
import { DataGate, MetricCard, PanelEmpty, SectionHeading } from "../ui/data-display";
import { num, pct, signedPct, usd } from "../../lib/format";
import type { Artifact, Generation, Progress, ReportsFile } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function branchToShow(report: ReportsFile): string | null {
  if (report.generations.some(row => row.branch === "main")) return "main";
  if (report.generations.some(row => row.branch === "smoke")) return "smoke";
  return report.generations[0]?.branch ?? null;
}
function bestGeneration(rows: Generation[]): Generation | null {
  return rows.reduce<Generation | null>((best, row) => {
    if (!best || row.heldout_mean > best.heldout_mean ||
      (row.heldout_mean === best.heldout_mean && row.generation > best.generation)) return row;
    return best;
  }, null);
}
function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  if (artifacts.length === 0) return <PanelEmpty>No hay artefactos en esta corrida.</PanelEmpty>;
  return <ul className="artifact-list">{artifacts.slice(0, 5).map(item => <li key={item.path}>
    <span className={item.accepted ? "artifact-name" : "artifact-name rejected-name"}>{item.path}</span>
    <span className="artifact-meta">Gen {item.generation} · {item.origin_failures} fallos</span>
    <span className={`badge gate-badge ${item.accepted ? "gate-accepted" : "gate-rejected"}`}>{item.accepted ? "Aprobada" : "Rechazada"}</span>
  </li>)}</ul>;
}
function Activity({ progress }: { progress: Progress | null }) {
  if (!progress?.lineas.length) return <PanelEmpty>No hay actividad reciente.</PanelEmpty>;
  return <ol className="activity-lines" aria-live="polite">{progress.lineas.slice(-6).map((line, index) => <li key={`${index}-${line}`}><code>{line}</code></li>)}</ol>;
}
export function EvolutionView({ reports, artifacts, progress, generar }: {
  reports: ViewState<ReportsFile>;
  artifacts: ViewState<Artifact[]>;
  progress: ViewState<Progress>;
  /** Acción del botón «Generar siguiente» (POST /api/run). Sin ella el botón queda deshabilitado. */
  generar?: { lanzar: () => void; deshabilitado: boolean; aviso: string | null; confirmacion?: ReactNode };
}) {
  return <AppShell active="/" section="Operaciones automotrices · held-out" title="Evolución"
    description="Sigue el rendimiento de cada generación y revisa la evidencia que explica sus cambios.">
    <DataGate state={reports} source="public/data/reports.json" title="La curva de aprendizaje aparecerá aquí"
      description="Esta vista compara el éxito en held-out, el conjunto que el destilador nunca ve.">
      {report => {
        const branch = branchToShow(report);
        const rows = report.generations.filter(row => row.branch === branch).sort((a, b) => a.generation - b.generation);
        const best = bestGeneration(rows);
        const gen0 = rows.find(row => row.generation === 0) ?? null;
        const mejora = best && gen0 ? best.heldout_mean - gen0.heldout_mean : null;
        const gasto = rows.reduce((total, row) => total + row.cost_usd, 0);
        // La rama control se dibuja como comparación solo junto a main, que es de donde nace
        const control = branch === "main" ? report.generations.filter(row => row.branch === "control") : [];
        const artifactRows = artifacts.status === "ready" ? artifacts.data.filter(item => item.branch === branch) : [];
        const progressData = progress.status === "ready" ? progress.data : null;
        return <>
          <div className="overview-actions">
            {/* El Excel lo arma el backend (con gráficas): un enlace basta para que el navegador lo descargue */}
            {rows.length > 0 && branch
              ? <a className="btn" href={`/api/excel?branch=${encodeURIComponent(branch)}`} download>Exportar Excel</a>
              : <button className="btn" type="button" disabled>Exportar Excel</button>}
            <button className="btn btn-primary" type="button" disabled={!generar || generar.deshabilitado}
              onClick={generar?.lanzar} aria-describedby="actions-note">Generar siguiente</button>
            <span className="action-note" id="actions-note" role="status">
              {generar?.aviso ?? (generar ? "Destila los fallos de train y evalúa la nueva generación." : "Las acciones se habilitarán al conectar la API.")}
            </span>
          </div>
          {generar?.confirmacion}
          <div className="grid g4">
            <MetricCard label="Éxito held-out" value={pct(best?.heldout_mean)} note={best ? `Mejor: generación ${best.generation}` : "Sin generaciones"} />
            <MetricCard label="Mejora desde gen 0" value={signedPct(mejora)}
              note={best && gen0 ? `${pct(gen0.heldout_mean)} → ${pct(best.heldout_mean)} en held-out` : "Sin generación 0"} />
            <MetricCard label="Correlación del juez" value={num(best?.judge_correlation, 2)} note="No define la métrica oficial" />
            <MetricCard label="Gasto de la rama" value={usd(gasto)} note={`${rows.length} ${rows.length === 1 ? "generación" : "generaciones"} evaluadas`} />
          </div>
          <section className="card overview-chart">
            <SectionHeading eyebrow="Rendimiento" title="Tasa de éxito por generación">
              <span className="chart-caption">Media y desviación entre semillas</span>
            </SectionHeading>
            <FitnessChart rows={rows} control={control} />
          </section>
          <div className="grid g2 overview-lower">
            <section className="card"><SectionHeading eyebrow="Progreso" title="Delta por generación" />
              <DeltaBars rows={rows} />
            </section>
            <section className="card"><SectionHeading eyebrow="Evidencia" title="Artefactos generados" />
              {artifacts.status === "error" ? <p className="inline-error">{artifacts.message}</p> : <ArtifactList artifacts={artifactRows} />}
              {artifacts.status === "loading" && <div className="skeleton skeleton-row" />}
              {artifacts.status === "empty" && <PanelEmpty>Los artefactos se mostrarán al cargar artifacts.json.</PanelEmpty>}
            </section>
          </div>
          <section className="card activity-panel"><SectionHeading eyebrow="Registro" title="Actividad reciente">
            <span className="activity-status"><span className={`status-dot ${progressData?.corriendo ? "status-active" : ""}`} />{progressData?.corriendo ? "En curso" : "Sin actividad"}</span>
          </SectionHeading>
            {progress.status === "error" ? <p className="inline-error">{progress.message}</p> : <Activity progress={progressData} />}
            {progress.status === "loading" && <div className="skeleton skeleton-row" />}
          </section>
          <p className="overview-note">La métrica oficial es el éxito en held-out, medida por el verificador programático. El juez LLM se muestra solo como referencia de calibración.</p>
        </>;
      }}
    </DataGate>
  </AppShell>;
}
