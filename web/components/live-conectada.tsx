"use client";

import { useEffect, useState } from "react";

import { pct } from "../lib/format";
import type { Generation, LiveConversation, LiveConversationSummary, LiveEvent } from "../lib/types";
import { MEJOR, useConversacion } from "../lib/use-conversacion";
import { useJson } from "../lib/use-json";
import type { ViewState } from "../lib/view-state";
import { LiveView, type PanelChat, type SelectorGeneracion } from "./views/live-view";

const POLLING_REPORTES_MS = 10_000;
const GENERACION_BASE = "0"; // en modo comparar, la segunda columna arranca con el agente escrito a mano

/** Mayor held-out y, en empate, la más nueva: la misma regla que backend/evaluation/export.py. */
function mejorDe(filas: Generation[]): Generation | null {
  return filas.reduce<Generation | null>((mejor, fila) =>
    !mejor || fila.heldout_mean > mejor.heldout_mean ||
    (fila.heldout_mean === mejor.heldout_mean && fila.generation > mejor.generation) ? fila : mejor, null);
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

/** Chat de la demo con historial del servidor, selector de generación y modo comparar (dos generaciones). */
export function LiveConectada() {
  const reportes = useJson("reports.json", { cadaMs: POLLING_REPORTES_MS });
  const generaciones = reportes.status === "ready" ? reportes.data.generations : [];
  // Misma regla que el resto de la web: main si tiene datos; si no, smoke
  const rama = !generaciones.some(g => g.branch === "main") && generaciones.some(g => g.branch === "smoke") ? "smoke" : "main";
  const filas = generaciones.filter(g => g.branch === rama).sort((a, b) => a.generation - b.generation);
  const mejor = mejorDe(filas);

  const principal = useConversacion(rama, MEJOR);
  const comparada = useConversacion(rama, GENERACION_BASE);
  const [comparar, setComparar] = useState(false);
  const [texto, setTexto] = useState("");
  const [conversaciones, setConversaciones] = useState<LiveConversationSummary[]>([]);
  const enCurso = principal.enCurso || comparada.enCurso;

  async function cargarHistorial() {
    setConversaciones(await leerHistorial());
  }
  useEffect(() => {
    let vigente = true; // si la vista se desmonta antes de que responda, no se actualiza el estado
    void leerHistorial().then(lista => { if (vigente) setConversaciones(lista); });
    return () => { vigente = false; };
  }, []);

  function nueva() {
    principal.nueva();
    comparada.nueva();
    setTexto("");
  }

  async function seleccionar(id: string) {
    const respuesta = await fetch(`/api/conversaciones/${id}`, { cache: "no-store" });
    if (!respuesta.ok) return void cargarHistorial(); // la borraron desde otro navegador
    principal.cargar(await respuesta.json() as LiveConversation);
    comparada.nueva();
    setComparar(false);
    setTexto("");
  }

  async function borrar(id: string) {
    if (!window.confirm("¿Borrar esta conversación del historial?")) return;
    await fetch(`/api/conversaciones/${id}`, { method: "DELETE" });
    if (id === principal.actual) principal.nueva();
    void cargarHistorial();
  }

  // Comparar exige que las dos columnas respondan exactamente las mismas preguntas: se empieza de cero
  function alternarComparar() {
    nueva();
    setComparar(activo => !activo);
  }

  async function enviar() {
    const pregunta = texto.trim();
    if (!pregunta || enCurso) return;
    setTexto("");
    await Promise.all([principal.enviar(pregunta), ...(comparar ? [comparada.enviar(pregunta)] : [])]);
    void cargarHistorial();
  }

  const opcionesBase = [
    { valor: MEJOR, etiqueta: mejor ? `Mejor · gen ${mejor.generation} (${pct(mejor.heldout_mean)})` : "Mejor generación" },
    ...filas.map(f => ({ valor: String(f.generation), etiqueta: `Gen ${f.generation} · ${pct(f.heldout_mean)} held-out` })),
  ];
  // Una conversación vieja puede ser de una generación que ya no aparece en la rama actual
  const opciones = (valor: string) => opcionesBase.some(o => o.valor === valor)
    ? opcionesBase : [...opcionesBase, { valor, etiqueta: `Gen ${valor}` }];

  // Una conversación habla siempre con la misma generación: cambiarla empieza de cero (en comparar, las dos)
  function selector(conversacion: typeof principal): SelectorGeneracion {
    return {
      opciones: opciones(conversacion.generacion),
      valor: conversacion.generacion,
      cambiar: valor => {
        if (comparar) {
          principal.nueva();
          comparada.nueva();
        } else if (conversacion.chat.length > 0) {
          conversacion.nueva();
        }
        conversacion.setGeneracion(valor);
      },
    };
  }

  const panel = (clave: string, conversacion: typeof principal): PanelChat => ({
    clave, chat: conversacion.chat, eventos: conversacion.eventos ?? [], enCurso: conversacion.enCurso,
    generacion: selector(conversacion),
  });
  // En comparar, a la izquierda el agente base y a la derecha el que eligió (la mejor por defecto)
  const paneles = comparar ? [panel("base", comparada), panel("principal", principal)] : [panel("principal", principal)];
  const evidencia: ViewState<LiveEvent[]> = principal.eventos === null
    ? { status: "empty" } : { status: "ready", data: principal.eventos };

  return <LiveView paneles={paneles} evidencia={evidencia}
    composer={{ texto, cambiarTexto: setTexto, enviar, detener: () => { principal.detener(); comparada.detener(); }, enCurso }}
    historial={{ conversaciones, actual: principal.actual, seleccionar: id => void seleccionar(id), nueva, borrar: id => void borrar(id) }}
    comparar={{ activo: comparar, alternar: alternarComparar }} />;
}
