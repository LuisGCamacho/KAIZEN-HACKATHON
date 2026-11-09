import { AppShell } from "../../components/app-shell";
import { EmptyState } from "../../components/empty-state";

export default function TrazasPage() {
  return <AppShell active="/trazas" section="Comparación" title="Trazas de episodio"
    description="Lee lado a lado cómo dos generaciones resolvieron la misma tarea y qué esperaba el verificador.">
    <EmptyState title="Aún no hay episodios comparables"
      description="Cuando existan trazas, aquí podrás revisar la tarea, el resultado esperado, los pasos de cada generación y el uso de herramientas generadas."
      source="web/public/data/traces.json"
      note="La comparación mostrará pasos, tokens y escalados únicamente si esos valores están presentes en los datos." />
  </AppShell>;
}
