"use client";

import { useState } from "react";

export type Comando = "next" | "gen0";

/** Lanza una corrida con POST /api/run. El progreso no llega aquí: lo trae progress.json por polling. */
export function useRun() {
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  async function lanzar(comando: Comando) {
    setEnviando(true);
    setAviso(null);
    try {
      const respuesta = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: comando }),
      });
      const cuerpo = (await respuesta.json().catch(() => ({}))) as { error?: string };
      if (respuesta.status === 202) setAviso(comando === "gen0" ? "Evaluando la generación 0…" : "Destilando la siguiente generación…");
      else if (respuesta.status === 409) setAviso("Ya hay una corrida en curso.");
      else setAviso(cuerpo.error ?? `No se pudo lanzar (código ${respuesta.status}).`);
    } catch {
      setAviso("Sin conexión con el servidor.");
    } finally {
      setEnviando(false);
    }
  }

  return { lanzar, enviando, aviso };
}
