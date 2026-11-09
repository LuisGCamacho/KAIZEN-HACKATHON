import { AppShell } from "../../components/app-shell";
import { EmptyState } from "../../components/empty-state";

export default function AutopsiaPage() {
  return <AppShell active="/autopsia" section="Evidencia" title="Autopsia de fallos"
    description="Rastrea las causas de error por generación y encuentra el artefacto que ayudó a resolverlas.">
    <EmptyState title="Aún no hay fallos agrupados"
      description="Cada causa ocupará una fila con su frecuencia a través de las generaciones. Los clusters abiertos seguirán visibles para mostrar qué problemas continúan sin resolver."
      source="web/public/data/clusters.json"
      note="Las frecuencias y los estados de cierre se leerán de resultados reales; no se muestran datos de ejemplo." />
  </AppShell>;
}
