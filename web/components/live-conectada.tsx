"use client";

import { useEffect, useRef, useState } from "react";

import { pct } from "../lib/format";
import { leerNdjson } from "../lib/ndjson";
import type { Generation, LiveConversation, LiveConversationSummary, LiveEvent } from "../lib/types";
import { useJson } from "../lib/use-json";
import type { ViewState } from "../lib/view-state";
import { LiveView, type MensajeChat } from "./views/live-view";

type Mensaje = { role: "user" | "assistant"; content: string };

const MEJOR = "best"; // valor del selector: live.py resuelve la mejor generación de la rama
const POLLING_REPORTES_MS = 10_000;

/** Mayor held-out y, en empate, la más nueva: la misma regla que backend/evaluation/export.py. */
function mejorDe(filas: Generation[]): Generation | null {
  return filas.reduce<Generation | null>((mejor, fila) =>
    !mejor || fila.heldout_mean > mejor.heldout_mean ||
    (fila.heldout_mean === mejor.heldout_mean && fila.generation > mejor.generation) ? fila : mejor, null);
}

/** Reconstruye lo que ve el público a partir de una conversación guardada por live.py. */
function chatDe(conversacion: LiveConversation): MensajeChat[] {
  return conversacion.turns.flatMap<MensajeChat>(turno => [
    { de: "cliente", texto: turno.question },
    turno.answer !== null
      ? { de: "agente", texto: turno.answer, herramientas: turno.tools }
      : { de: "aviso", texto: `No se pudo responder: ${turno.error ?? "sin detalle"}` },
  ]);
}

/** Resumen de las conversaciones guardadas; lista vacía si el servidor no responde (el chat sigue funcionando). */
async function leerHistorial(): Promise<LiveConversationSummary[]> {
  try {
    const respuesta = await fetch("/api/conversaciones", { cache: "no-store" });
    return respuesta.ok ? await respuesta.json() as LiveConversationSummary[] : [];
  } catch {
    return [];
  }
}

/**
 * Chat de la demo: manda la conversación completa a POST /api/live y muestra cada evento NDJSON en cuanto
 * llega. Cada conversación tiene un id; live.py la guarda en el servidor y aparece en el historial.
 */
export function LiveConectada() {
  const reportes = useJson("reports.json", { cadaMs: POLLING_REPORTES_MS });
  const generaciones = reportes.status === "ready" ? reportes.data.generations : [];
  // Misma regla que el resto de la web: main si tiene datos; si no, smoke
  const rama = !generaciones.some(g => g.branch === "main") && generaciones.some(g => g.branch === "smoke") ? "smoke" : "main";
  const filas = generaciones.filter(g => g.branch === rama).sort((a, b) => a.generation - b.generation);
  const mejor = mejorDe(filas);

  const [generacion, setGeneracion] = useState<string>(MEJOR);
  const [conversaciones, setConversaciones] = useState<LiveConversationSummary[]>([]);
  const [actual, setActual] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [chat, setChat] = useState<MensajeChat[]>([]);
  const [eventos, setEventos] = useState<LiveEvent[] | null>(null);
  const [texto, setTexto] = useState("");
  const [enCurso, setEnCurso] = useState(false);
  const abortar = useRef<AbortController | null>(null);

  async function cargarHistorial() {
    setConversaciones(await leerHistorial());
  }
  useEffect(() => {
    let vigente = true; // si la vista se desmonta antes de que responda, no se actualiza el estado
    void leerHistorial().then(lista => { if (vigente) setConversaciones(lista); });
    return () => { vigente = false; };
  }, []);

  function nueva(otraGeneracion?: string) {
    setActual(null);
    setMensajes([]);
    setChat([]);
    setEventos(null);
    setTexto("");
    if (otraGeneracion !== undefined) setGeneracion(otraGeneracion);
  }

  async function seleccionar(id: string) {
    const respuesta = await fetch(`/api/conversaciones/${id}`, { cache: "no-store" });
    if (!respuesta.ok) return void cargarHistorial(); // la borraron desde otro navegador
    const conversacion = await respuesta.json() as LiveConversation;
    setActual(conversacion.id);
    setMensajes(conversacion.messages);
    setChat(chatDe(conversacion));
    setEventos(conversacion.turns.flatMap(turno => turno.events));
    setGeneracion(conversacion.generation !== null ? String(conversacion.generation) : MEJOR);
    setTexto("");
  }

  async function borrar(id: string) {
    if (!window.confirm("¿Borrar esta conversación del historial?")) return;
    await fetch(`/api/conversaciones/${id}`, { method: "DELETE" });
    if (id === actual) nueva();
    void cargarHistorial();
  }

  // Una conversación habla siempre con la misma generación: cambiarla abre una conversación nueva
  function cambiarGeneracion(valor: string) {
    if (chat.length > 0) nueva(valor);
    else setGeneracion(valor);
  }

  async function enviar() {
    const pregunta = texto.trim();
    if (!pregunta || enCurso) return;
    const id = actual ?? crypto.randomUUID();
    const conversacion: Mensaje[] = [...mensajes, { role: "user", content: pregunta }];
    setActual(id);
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
        body: JSON.stringify({ messages: conversacion, generation: generacion === MEJOR ? MEJOR : Number(generacion),
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
      void cargarHistorial();
    }
  }

  const opciones = [
    { valor: MEJOR, etiqueta: mejor ? `Mejor · gen ${mejor.generation} (${pct(mejor.heldout_mean)})` : "Mejor generación" },
    ...filas.map(f => ({ valor: String(f.generation), etiqueta: `Gen ${f.generation} · ${pct(f.heldout_mean)} held-out` })),
  ];
  // Una conversación vieja puede ser de una generación que ya no aparece en la rama actual
  if (!opciones.some(o => o.valor === generacion)) opciones.push({ valor: generacion, etiqueta: `Gen ${generacion}` });

  const state: ViewState<LiveEvent[]> = eventos === null ? { status: "empty" } : { status: "ready", data: eventos };
  return <LiveView state={state} chat={chat}
    composer={{ texto, cambiarTexto: setTexto, enviar, detener: () => abortar.current?.abort(), enCurso }}
    historial={{ conversaciones, actual, seleccionar: id => void seleccionar(id), nueva: () => nueva(), borrar: id => void borrar(id) }}
    generacion={{ opciones, valor: generacion, cambiar: cambiarGeneracion }} />;
}
