import { AppShell } from "../../components/app-shell";
import { EmptyState } from "../../components/empty-state";

export default function LinajePage() {
  return <AppShell active="/linaje" section="Evidencia" title="Linaje"
    description="Compara generaciones, sus causas de cambio y las revisiones de prompts que dieron forma al agente.">
    <EmptyState title="El historial de generaciones aparecerá aquí"
      description="Cada generación mostrará su relación con la anterior, el motivo medido del cambio y la diferencia entre prompts. La reescritura automática del destilador se señalará como autoría de la máquina."
      source="web/public/data/lineage.json"
      note="Los diffs usan una escala de grises para que el acento conserve su significado." />
  </AppShell>;
}
