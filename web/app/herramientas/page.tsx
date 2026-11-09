import { AppShell } from "../../components/app-shell";
import { EmptyState } from "../../components/empty-state";

export default function HerramientasPage() {
  return <AppShell active="/herramientas" section="Artefactos" title="Herramientas generadas"
    description="Inspecciona el código producido por el sistema y el resultado de su evaluación.">
    <EmptyState title="Todavía no hay herramientas para revisar"
      description="Las herramientas aceptadas y rechazadas aparecerán con su código, el cluster de origen y el motivo del gate. Los descartes también forman parte de la evidencia."
      source="web/public/data/artifacts.json"
      note="El acento de autoría se reserva para artefactos escritos por la máquina." />
  </AppShell>;
}
