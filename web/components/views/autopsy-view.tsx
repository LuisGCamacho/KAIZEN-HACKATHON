import { AppShell } from "../app-shell";
import { Sparkline } from "../charts/sparkline";
import { DataGate, StateBadge } from "../ui/data-display";
import type { Cluster } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function reasonLabel(reason: string): string {
  return reason.replaceAll("_", " ");
}
export function AutopsyView({ state }: { state: ViewState<Cluster[]> }) {
  return <AppShell active="/autopsia" section="Evidencia" title="Autopsia de fallos"
    description="¿Qué fallos tuvo el agente y cuáles se cerraron? Cada fila sigue una causa a través de las generaciones.">
    <DataGate state={state} source="public/data/clusters.json" title="Aún no hay fallos agrupados"
      description="Los clusters abiertos también se mostrarán; así se ve qué problemas siguen sin resolver.">
      {clusters => clusters.length === 0 ? <div className="panel-empty"><p>El exportador no reportó clusters para esta rama.</p></div> :
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th scope="col">Causa</th><th scope="col">Frecuencia por generación</th><th scope="col">Estado</th><th scope="col">Artefacto que cerró</th></tr></thead>
          <tbody>{clusters.map(cluster => <tr key={`${cluster.branch}-${cluster.reason}`}>
            <th scope="row"><code>{reasonLabel(cluster.reason)}</code></th>
            <td><Sparkline values={cluster.per_generation} label={`Frecuencia del fallo ${reasonLabel(cluster.reason)} por generación`} />
              <span className="table-count">{cluster.per_generation.join(" · ")}</span></td>
            <td><StateBadge state={cluster.open ? "open" : "closed"}>{cluster.open ? "Abierto" : "Cerrado"}</StateBadge></td>
            <td>{cluster.closed_by ? <code>{cluster.closed_by}</code> : <span className="muted-value">Sin artefacto</span>}</td>
          </tr>)}</tbody>
        </table></div>}
    </DataGate>
  </AppShell>;
}
