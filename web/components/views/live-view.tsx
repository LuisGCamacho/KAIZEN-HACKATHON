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
export type LiveComposer = {
  texto: string;
  cambiarTexto: (texto: string) => void;
  enviar: () => void;
  detener: () => void;
  enCurso: boolean;
  destino: string; // p. ej. "main · mejor generación", para que el público sepa con quién habla
};

export function LiveView({ state, composer }: { state: ViewState<LiveEvent[]>; composer?: LiveComposer }) {
  return <AppShell active="/live" section="Observación" title="En vivo"
    description="Sigue la conversación con el agente, sus delegaciones y las herramientas que usa.">
    <section className="card live-composer">
      <label className="lbl" htmlFor="live-prompt">Mensaje para el agente</label>
      <form className="composer-row" onSubmit={evento => { evento.preventDefault(); composer?.enviar(); }}>
        <textarea id="live-prompt" rows={3} disabled={!composer || composer.enCurso}
          value={composer?.texto ?? ""} onChange={evento => composer?.cambiarTexto(evento.target.value)}
          onKeyDown={evento => { if (evento.key === "Enter" && !evento.shiftKey) { evento.preventDefault(); composer?.enviar(); } }}
          placeholder={composer ? "Escribe como cliente, p. ej. «¿Qué garantía tiene el A010 por falla de motor?»" : "El envío se habilitará al conectar la sesión en vivo."} />
        {composer?.enCurso
          ? <button className="btn" type="button" onClick={composer.detener}>Detener</button>
          : <button className="btn btn-primary" type="submit" disabled={!composer || !composer.texto.trim()}>Enviar</button>}
      </form>
      <p className="page-footnote">{composer ? <>Conversando con <code>{composer.destino}</code> por <code>POST /api/live</code>.</> : <>La conversación se conecta a <code>POST /api/live</code>.</>}</p>
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
