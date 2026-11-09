"use client";

import { useEffect, useRef } from "react";

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

/** Un turno visible del chat. "aviso" = el sistema no pudo responder (error o Detener), no lo dijo el agente. */
export type MensajeChat = { de: "cliente" | "agente" | "aviso"; texto: string; herramientas?: number };

export type LiveComposer = {
  texto: string;
  cambiarTexto: (texto: string) => void;
  enviar: () => void;
  detener: () => void;
  enCurso: boolean;
  destino: string; // p. ej. "main · mejor generación", para que el público sepa con quién habla
};

/** Preguntas que tocan las reglas ocultas del entorno; un clic las pone en el cuadro de texto. */
const EJEMPLOS = [
  "Compré el A061 hace 13 meses y el motor hace un ruido raro, ¿me lo cubre la garantía?",
  "Quiero que me lleven un auto de Mérida a Guadalajara, ¿en cuántos días llega?",
  "Tengo 50,000 de enganche y pago máximo 7,000 al mes a 48 meses en Monterrey, ¿qué autos me alcanzan?",
  "Agenden una inspección del A010 para el domingo.",
];

/** Qué está haciendo el agente ahora, a partir del último evento del turno en curso. */
function estadoActual(eventos: LiveEvent[]): string {
  const ultimo = eventos.at(-1);
  if (ultimo?.type === "tool_call") return `Consultando ${ultimo.tool}…`;
  if (ultimo?.type === "delegate") return `Delegando a ${ultimo.to}…`;
  return "Pensando la respuesta…";
}

function Conversacion({ chat, eventos, composer }: { chat: MensajeChat[]; eventos: LiveEvent[]; composer?: LiveComposer }) {
  const final = useRef<HTMLLIElement>(null);
  // Se pega al último mensaje cada vez que llega algo nuevo
  useEffect(() => { final.current?.scrollIntoView({ block: "nearest" }); }, [chat.length, eventos.length]);

  if (chat.length === 0) {
    return <div className="chat-vacio">
      <p>Escribe como si fueras un cliente de la agencia. El agente responde usando sus herramientas: inventario, financiamiento, garantías, entregas y trámites.</p>
      {composer && <div className="chat-ejemplos" aria-label="Preguntas de ejemplo">
        {EJEMPLOS.map(ejemplo => <button key={ejemplo} type="button" className="chip-ejemplo"
          onClick={() => {
            composer.cambiarTexto(ejemplo);
            document.getElementById("live-prompt")?.focus(); // así Enter envía la pregunta elegida
          }} disabled={composer.enCurso}>{ejemplo}</button>)}
      </div>}
    </div>;
  }
  return <ol className="chat-lista" aria-live="polite">
    {chat.map((mensaje, indice) => <li key={indice} className={`chat-msg chat-${mensaje.de}`}>
      <span className="chat-autor">{mensaje.de === "cliente" ? "Cliente" : mensaje.de === "agente" ? "Agente" : "Aviso"}</span>
      <p>{mensaje.texto}</p>
      {mensaje.de === "agente" && mensaje.herramientas !== undefined &&
        <span className="chat-meta">{mensaje.herramientas === 0 ? "Sin herramientas" : `Usó ${mensaje.herramientas} ${mensaje.herramientas === 1 ? "herramienta" : "herramientas"}`}</span>}
    </li>)}
    {composer?.enCurso && <li className="chat-msg chat-agente chat-pensando">
      <span className="chat-autor">Agente</span><p>{estadoActual(eventos)}</p>
    </li>}
    <li ref={final} className="chat-ancla" aria-hidden="true" />
  </ol>;
}

export function LiveView({ state, composer, chat = [] }: {
  state: ViewState<LiveEvent[]>;
  composer?: LiveComposer;
  chat?: MensajeChat[];
}) {
  const eventos = state.status === "ready" ? state.data : [];
  return <AppShell active="/live" section="Observación" title="En vivo"
    description="Conversa con el agente como lo haría un cliente y observa qué herramientas usa para responder.">
    <div className="live-layout">
      <section className="card live-chat" aria-label="Conversación con el agente">
        <SectionHeading eyebrow="Atención al cliente" title="Conversación">
          {composer && <span className="chat-caption">{composer.destino}</span>}
        </SectionHeading>
        <div className="chat-scroll"><Conversacion chat={chat} eventos={eventos} composer={composer} /></div>
        <form className="composer-row" onSubmit={evento => { evento.preventDefault(); composer?.enviar(); }}>
          <label className="sr-only" htmlFor="live-prompt">Mensaje para el agente</label>
          <textarea id="live-prompt" rows={2} disabled={!composer || composer.enCurso}
            value={composer?.texto ?? ""} onChange={evento => composer?.cambiarTexto(evento.target.value)}
            onKeyDown={evento => { if (evento.key === "Enter" && !evento.shiftKey) { evento.preventDefault(); composer?.enviar(); } }}
            placeholder={composer ? "Escribe tu mensaje como cliente…" : "El envío se habilitará al conectar la sesión en vivo."} />
          {composer?.enCurso
            ? <button className="btn" type="button" onClick={composer.detener}>Detener</button>
            : <button className="btn btn-primary" type="submit" disabled={!composer || !composer.texto.trim()}>Enviar</button>}
        </form>
        <p className="page-footnote">Enter envía · Mayús + Enter agrega una línea. Cada respuesta tarda entre 10 y 20 segundos.</p>
      </section>

      <section className="card live-timeline" aria-label="Actividad del agente">
        <SectionHeading eyebrow="Evidencia" title="Lo que hizo el agente" />
        {state.status === "empty"
          ? <PanelEmpty>Cada herramienta que el agente consulte y su resultado aparecerán aquí, en el orden en que ocurren.</PanelEmpty>
          : <DataGate state={state} source="POST /api/live" title="Aún no hay actividad"
          description="Cada herramienta que el agente consulta y su resultado aparecerán aquí, en el orden en que ocurren.">
          {events => events.length === 0 ? <PanelEmpty>La sesión no emitió eventos.</PanelEmpty> :
            <ol className="event-list">{events.map((event, index) => <li key={`${event.t}-${index}`}>
              <time dateTime={new Date(event.t).toISOString()}>{new Date(event.t).toLocaleTimeString("es-MX")}</time>
              <span className="event-type">{event.type.replaceAll("_", " ")}</span>
              {event.type === "tool_call" && event.generated && <MachineBadge />}
              <p>{eventText(event)}</p>
              {event.type === "tool_result" && <span className="event-result">{event.ok ? "Completada" : "Falló"} · {event.ms} ms</span>}
            </li>)}</ol>}
        </DataGate>}
      </section>
    </div>
  </AppShell>;
}
