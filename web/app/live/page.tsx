import { AppShell } from "../../components/app-shell";
import { EmptyState } from "../../components/empty-state";

export default function EnVivoPage() {
  return <AppShell active="/live" section="Observación" title="En vivo"
    description="Observa una sesión de agente paso a paso, con llamadas a herramientas y respuestas en contexto.">
    <EmptyState title="La sesión en vivo todavía no está conectada"
      description="Aquí se presentará el intercambio con el agente, su actividad y el resultado final. La ruta de streaming necesita un backend activo para iniciar una sesión."
      source="POST /api/live"
      note="No se inicia ninguna ejecución desde esta pantalla mientras el endpoint no esté disponible." />
  </AppShell>;
}
