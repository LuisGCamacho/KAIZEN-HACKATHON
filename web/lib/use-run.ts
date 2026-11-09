"use client";

import { useState } from "react";

export type Comando = "next" | "gen0" | "cancel";

const CLAVE_ALMACEN = "kaizen.admin"; // la clave de administrador se recuerda en este navegador
const CABECERA_ADMIN = "x-kaizen-admin"; // misma que lib/server/admin.ts

/** Clave guardada en este navegador, o "" si no hay (o el navegador bloquea el almacenamiento). */
export function claveGuardada(): string {
  try {
    return localStorage.getItem(CLAVE_ALMACEN) ?? "";
  } catch {
    return "";
  }
}

function guardarClave(clave: string): void {
  try {
    if (clave) localStorage.setItem(CLAVE_ALMACEN, clave);
    else localStorage.removeItem(CLAVE_ALMACEN);
  } catch {
    // Sin almacenamiento la clave se pide en cada acción; no bloquea nada
  }
}

const AVISOS: Record<Comando, string> = {
  gen0: "Evaluando la generación 0…",
  next: "Destilando la siguiente generación…",
  cancel: "Cancelando la corrida…",
};

/**
 * Acciones de /api/run (lanzar y cancelar). El progreso no llega aquí: lo trae progress.json por polling.
 * Si el servidor exige clave (KAIZEN_ADMIN_KEY) y la guardada no sirve, se olvida y `pideClave` se activa.
 */
export function useRun() {
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [pideClave, setPideClave] = useState(false);

  async function lanzar(comando: Comando, clave?: string): Promise<boolean> {
    if (clave !== undefined) guardarClave(clave.trim());
    setEnviando(true);
    setAviso(null);
    try {
      const respuesta = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", [CABECERA_ADMIN]: claveGuardada() },
        body: JSON.stringify({ command: comando }),
      });
      const cuerpo = (await respuesta.json().catch(() => ({}))) as { error?: string };
      if (respuesta.status === 401) {
        guardarClave("");
        setPideClave(true);
        setAviso("Clave de administrador incorrecta.");
        return false;
      }
      setPideClave(false);
      if (respuesta.status === 202) {
        setAviso(AVISOS[comando]);
        return true;
      }
      setAviso(respuesta.status === 409 && comando !== "cancel" ? "Ya hay una corrida en curso."
        : cuerpo.error ?? `No se pudo completar (código ${respuesta.status}).`);
      return false;
    } catch {
      setAviso("Sin conexión con el servidor.");
      return false;
    } finally {
      setEnviando(false);
    }
  }

  return { lanzar, enviando, aviso, pideClave };
}
