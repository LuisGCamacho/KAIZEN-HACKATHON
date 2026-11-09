"use client";

import { useEffect, useState } from "react";

import type { DataFiles } from "./types";
import type { ViewState } from "./view-state";

/**
 * Lee un JSON de /api/data con polling opcional y lo entrega como ViewState.
 * 404 = el backend todavía no exportó nada: estado "empty", no error.
 * esVacio decide cuándo un archivo existente no tiene datos que mostrar (p. ej. una lista vacía).
 */
export function useJson<K extends keyof DataFiles>(
  archivo: K,
  { cadaMs, esVacio }: { cadaMs?: number; esVacio?: (datos: DataFiles[K]) => boolean } = {},
): ViewState<DataFiles[K]> {
  const [estado, setEstado] = useState<ViewState<DataFiles[K]>>({ status: "loading" });

  useEffect(() => {
    let vigente = true;
    const cargar = async () => {
      try {
        const respuesta = await fetch(`/api/data/${archivo}`, { cache: "no-store" });
        if (!vigente) return;
        if (respuesta.status === 404) return setEstado({ status: "empty" });
        if (!respuesta.ok) return setEstado({ status: "error", message: `El servidor respondió ${respuesta.status}` });
        const datos = (await respuesta.json()) as DataFiles[K];
        if (!vigente) return;
        setEstado(esVacio?.(datos) ? { status: "empty" } : { status: "ready", data: datos });
      } catch {
        // Un fallo de red durante el polling no borra lo que ya se mostraba
        if (vigente) setEstado(previo => (previo.status === "ready" ? previo : { status: "error", message: "Sin conexión con el servidor" }));
      }
    };
    void cargar();
    const intervalo = cadaMs ? setInterval(cargar, cadaMs) : undefined;
    return () => {
      vigente = false;
      clearInterval(intervalo);
    };
    // esVacio es una función de criterio fijo por vista; no debe reiniciar el polling en cada render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archivo, cadaMs]);

  return estado;
}

export const listaVacia = (datos: unknown[]) => datos.length === 0;
