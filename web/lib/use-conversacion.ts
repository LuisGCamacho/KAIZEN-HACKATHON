"use client";

import { useRef, useState } from "react";

import type { MensajeChat } from "../components/views/live-view";
import { leerNdjson } from "./ndjson";
import type { LiveConversation, LiveEvent } from "./types";

type Mensaje = { role: "user" | "assistant"; content: string };

export const MEJOR = "best"; // generación pedida: live.py resuelve la mejor de la rama

/** Reconstruye lo que ve el público a partir de una conversación guardada por live.py. */
function chatDe(conversacion: LiveConversation): MensajeChat[] {
  return conversacion.turns.flatMap<MensajeChat>(turno => [
    { de: "cliente", texto: turno.question },
    turno.answer !== null
      ? { de: "agente", texto: turno.answer, herramientas: turno.tools }
      : { de: "aviso", texto: `No se pudo responder: ${turno.error ?? "sin detalle"}` },
  ]);
}

/**
 * Una conversación de /live con una generación: manda el historial a POST /api/live, muestra cada evento
 * NDJSON en cuanto llega y conserva su id (live.py la guarda en el servidor para el historial).
 * El modo comparar usa dos a la vez con la misma pregunta.
 */
export function useConversacion(rama: string, generacionInicial: string) {
  const [generacion, setGeneracion] = useState(generacionInicial);
  const [actual, setActual] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [chat, setChat] = useState<MensajeChat[]>([]);
  const [eventos, setEventos] = useState<LiveEvent[] | null>(null);
  const [enCurso, setEnCurso] = useState(false);
  const abortar = useRef<AbortController | null>(null);

  function nueva(otraGeneracion?: string) {
    setActual(null);
    setMensajes([]);
    setChat([]);
    setEventos(null);
    if (otraGeneracion !== undefined) setGeneracion(otraGeneracion);
  }

  function cargar(conversacion: LiveConversation) {
    setActual(conversacion.id);
    setMensajes(conversacion.messages);
    setChat(chatDe(conversacion));
    setEventos(conversacion.turns.flatMap(turno => turno.events));
    setGeneracion(conversacion.generation !== null ? String(conversacion.generation) : MEJOR);
  }

  async function enviar(pregunta: string) {
    const id = actual ?? crypto.randomUUID();
    const historial: Mensaje[] = [...mensajes, { role: "user", content: pregunta }];
    setActual(id);
    setMensajes(historial);
    setChat(previo => [...previo, { de: "cliente", texto: pregunta }]);
    setEventos(previos => previos ?? []);
    setEnCurso(true);
    const control = new AbortController();
    abortar.current = control;
    let herramientasDelTurno = 0;
    const agregar = (evento: LiveEvent) => {
      setEventos(previos => [...(previos ?? []), evento]);
      // "best" se fija a la generación que respondió, así los siguientes turnos hablan con el mismo agente
      if (evento.type === "start") setGeneracion(String(evento.generation));
      if (evento.type === "tool_call") herramientasDelTurno += 1;
      if (evento.type === "final") {
        setChat(previo => [...previo, { de: "agente", texto: evento.text, herramientas: herramientasDelTurno }]);
        setMensajes(previos => [...previos, { role: "assistant", content: evento.text }]);
      }
      if (evento.type === "error") setChat(previo => [...previo, { de: "aviso", texto: `No se pudo responder: ${evento.message}` }]);
    };
    try {
      const respuesta = await fetch("/api/live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: historial, generation: generacion === MEJOR ? MEJOR : Number(generacion),
                               branch: rama, conversation_id: id }),
        signal: control.signal,
      });
      if (!respuesta.ok || !respuesta.body) {
        const cuerpo = (await respuesta.json().catch(() => ({}))) as { error?: string };
        agregar({ t: Date.now(), type: "error", message: cuerpo.error ?? `El servidor respondió ${respuesta.status}` });
        return;
      }
      for await (const evento of leerNdjson<LiveEvent>(respuesta.body)) agregar(evento);
    } catch (e) {
      if (control.signal.aborted) agregar({ t: Date.now(), type: "error", message: "Detenido por el usuario" });
      else {
        agregar({ t: Date.now(), type: "error", message: "Se perdió la conexión con el servidor" });
        console.error("/live:", e);
      }
    } finally {
      setEnCurso(false);
      abortar.current = null;
    }
  }

  return { generacion, setGeneracion, actual, chat, eventos, enCurso, nueva, cargar, enviar,
           detener: () => abortar.current?.abort() };
}
