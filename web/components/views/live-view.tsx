"use client";

import { useEffect, useRef } from "react";

import { AppShell } from "../app-shell";
import { DataGate, MachineBadge, PanelEmpty, SectionHeading } from "../ui/data-display";
import type { LiveConversationSummary, LiveEvent } from "../../lib/types";
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
};

export type SelectorGeneracion = {
  opciones: { valor: string; etiqueta: string }[];
  valor: string;
  cambiar: (valor: string) => void;
};

export type Historial = {
  conversaciones: LiveConversationSummary[];
  actual: string | null;
  seleccionar: (id: string) => void;
  nueva: () => void;
  borrar: (id: string) => void;
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

function fechaCorta(iso: string): string {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "" : fecha.toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });
}

function ListaHistorial({ historial, bloqueado }: { historial: Historial; bloqueado: boolean }) {
  return <section className="card live-historial" aria-label="Historial de conversaciones">
    <SectionHeading eyebrow="Historial" title="Conversaciones" />
    <button className="btn btn-primary historial-nueva" type="button" onClick={historial.nueva} disabled={bloqueado}>
      Nueva conversación
    </button>
    {historial.conversaciones.length === 0
      ? <PanelEmpty>Aún no hay conversaciones guardadas.</PanelEmpty>
      : <ul className="historial-lista">
        {historial.conversaciones.map(c => <li key={c.id} className={c.id === historial.actual ? "historial-activa" : ""}>
          <button type="button" className="historial-item" onClick={() => historial.seleccionar(c.id)} disabled={bloqueado}
            aria-current={c.id === historial.actual ? "true" : undefined}>
            <span className="historial-titulo">{c.title || "Sin título"}</span>
            <span className="historial-meta">{c.generation !== null ? `gen ${c.generation}` : "—"} · {c.turns} {c.turns === 1 ? "turno" : "turnos"} · {fechaCorta(c.updated)}</span>
          </button>
          <button type="button" className="historial-borrar" onClick={() => historial.borrar(c.id)} disabled={bloqueado}
            aria-label={`Borrar la conversación «${c.title}»`} title="Borrar">×</button>
        </li>)}
      </ul>}
  </section>;
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

export function LiveView({ state, composer, chat = [], historial, generacion }: {
  state: ViewState<LiveEvent[]>;
  composer?: LiveComposer;
  chat?: MensajeChat[];
  historial?: Historial;
  generacion?: SelectorGeneracion;
}) {
  const ocupado = Boolean(composer?.enCurso);
  const eventos = state.status === "ready" ? state.data : [];
  return <AppShell active="/live" section="Observación" title="En vivo"
    description="Conversa con el agente como lo haría un cliente y observa qué herramientas usa para responder.">
    <div className={`live-layout ${historial ? "con-historial" : ""}`}>
      {historial && <ListaHistorial historial={historial} bloqueado={ocupado} />}

      <section className="card live-chat" aria-label="Conversación con el agente">
        <SectionHeading eyebrow="Atención al cliente" title="Conversación">
          {generacion && <label className="selector-generacion">
            <span>Generación</span>
            <select value={generacion.valor} onChange={evento => generacion.cambiar(evento.target.value)} disabled={ocupado}
              title="Cambiar de generación inicia una conversación nueva">
              {generacion.opciones.map(o => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
            </select>
          </label>}
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
