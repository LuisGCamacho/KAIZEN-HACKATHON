"use client";

import { useRef, useState } from "react";

import { leerNdjson } from "../lib/ndjson";
import type { LiveEvent } from "../lib/types";
import { useJson } from "../lib/use-json";
import type { ViewState } from "../lib/view-state";
import { LiveView, type MensajeChat } from "./views/live-view";

type Mensaje = { role: "user" | "assistant"; content: string };

/**
 * Chat de la demo: manda la conversación completa a POST /api/live y muestra cada evento NDJSON en cuanto
 * llega. Detener aborta el fetch; la ruta mata el proceso de Python al detectar el abort.
 */
export function LiveConectada() {
  const reportes = useJson("reports.json");
  // Misma regla que el resto de la web: main si tiene datos; si no, smoke
  const rama = reportes.status === "ready" && !reportes.data.generations.some(g => g.branch === "main")
    && reportes.data.generations.some(g => g.branch === "smoke") ? "smoke" : "main";

  const [texto, setTexto] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [eventos, setEventos] = useState<LiveEvent[] | null>(null);
  const [chat, setChat] = useState<MensajeChat[]>([]); // lo que ve el público: turnos de cliente y agente
  const [enCurso, setEnCurso] = useState(false);
  const abortar = useRef<AbortController | null>(null);

  async function enviar() {
    const pregunta = texto.trim();
    if (!pregunta || enCurso) return;
    const conversacion: Mensaje[] = [...mensajes, { role: "user", content: pregunta }];
    setMensajes(conversacion);
    setChat(previo => [...previo, { de: "cliente", texto: pregunta }]);
    setTexto("");
    setEventos(previos => previos ?? []);
    setEnCurso(true);
    const control = new AbortController();
    abortar.current = control;
    let herramientasDelTurno = 0;
    const agregar = (evento: LiveEvent) => {
      setEventos(previos => [...(previos ?? []), evento]);
      if (evento.type === "tool_call") herramientasDelTurno += 1;
      if (evento.type === "final") setChat(previo => [...previo, { de: "agente", texto: evento.text, herramientas: herramientasDelTurno }]);
      if (evento.type === "error") setChat(previo => [...previo, { de: "aviso", texto: `No se pudo responder: ${evento.message}` }]);
    };
    try {
      const respuesta = await fetch("/api/live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conversacion, generation: "best", branch: rama }),
        signal: control.signal,
      });
      if (!respuesta.ok || !respuesta.body) {
        const cuerpo = (await respuesta.json().catch(() => ({}))) as { error?: string };
        agregar({ t: Date.now(), type: "error", message: cuerpo.error ?? `El servidor respondió ${respuesta.status}` });
        return;
      }
      for await (const evento of leerNdjson<LiveEvent>(respuesta.body)) {
        agregar(evento);
        // La respuesta final entra al historial para que el siguiente turno tenga contexto
        if (evento.type === "final") setMensajes(previos => [...previos, { role: "assistant", content: evento.text }]);
      }
    } catch (e) {
      if (control.signal.aborted) agregar({ t: Date.now(), type: "error", message: "Detenido por el usuario" });
      else agregar({ t: Date.now(), type: "error", message: "Se perdió la conexión con el servidor" });
      if (!control.signal.aborted) console.error("/live:", e);
    } finally {
      setEnCurso(false);
      abortar.current = null;
    }
  }

  const state: ViewState<LiveEvent[]> = eventos === null ? { status: "empty" } : { status: "ready", data: eventos };
  return <LiveView state={state} chat={chat} composer={{
    texto, cambiarTexto: setTexto, enviar, detener: () => abortar.current?.abort(), enCurso,
    destino: `${rama} · mejor generación`,
  }} />;
}
