import { AppShell } from "../app-shell";
import { DataGate, MachineBadge, PanelEmpty, SectionHeading } from "../ui/data-display";
import type { LiveEvent } from "../../lib/types";
import type { ViewState } from "../../lib/view-state";

function eventText(event: LiveEvent): string {
  switch (event.type) {
    case "start": return `Generación ${event.generation} · ${event.branch} · ${event.topology}`;
    case "delegate": return `Delegó a ${event.to}: ${event.query}`;
    case "tool_call": return `Llamó a ${event.tool}`;
    case "tool_result": return `${event.tool}: ${event.summary}`;
    case "message": return event.text;
    case "final": return event.text;
    case "error": return event.message;
  }
}
export function LiveView({ state }: { state: ViewState<LiveEvent[]> }) {
  return <AppShell active="/live" section="Observación" title="En vivo"
    description="Sigue la conversación con el agente, sus delegaciones y las herramientas que usa.">
    <section className="card live-composer">
      <label className="lbl" htmlFor="live-prompt">Mensaje para el agente</label>
      <div className="composer-row"><textarea id="live-prompt" rows={3} disabled placeholder="El envío se habilitará al conectar la sesión en vivo." />
        <button className="btn btn-primary" type="button" disabled>Enviar</button></div>
      <p className="page-footnote">La conversación se conecta a <code>POST /api/live</code>.</p>
    </section>
    <section className="card live-timeline" aria-live="polite">
      <SectionHeading eyebrow="Sesión" title="Actividad del agente" />
      <DataGate state={state} source="POST /api/live" title="La sesión en vivo todavía no inicia"
        description="Los mensajes, delegaciones, llamadas a herramientas y resultado final aparecerán aquí.">
        {events => events.length === 0 ? <PanelEmpty>La sesión no emitió eventos.</PanelEmpty> :
          <ol className="event-list">{events.map((event, index) => <li key={`${event.t}-${index}`}>
            <time dateTime={new Date(event.t).toISOString()}>{new Date(event.t).toLocaleTimeString("es-MX")}</time>
            <span className="event-type">{event.type.replaceAll("_", " ")}</span>
            {event.type === "tool_call" && event.generated && <MachineBadge />}
            <p>{eventText(event)}</p>
            {event.type === "tool_result" && <span className="event-result">{event.ok ? "Completada" : "Falló"} · {event.ms} ms</span>}
          </li>)}</ol>}
      </DataGate>
    </section>
  </AppShell>;
}
