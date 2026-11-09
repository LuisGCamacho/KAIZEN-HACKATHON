import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { LIVE_DIR } from "@/lib/server/python";
import type { LiveConversation, LiveConversationSummary } from "@/lib/types";

const MAX_CONVERSACIONES = 50; // la lista del historial muestra las más recientes

/** Historial de /live: resumen de cada conversación guardada por live.py, la más reciente primero. */
export async function GET() {
  let nombres: string[] = [];
  try {
    nombres = (await readdir(/* turbopackIgnore: true */ LIVE_DIR)).filter(nombre => nombre.endsWith(".json"));
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "ENOENT") console.error("/api/conversaciones:", e);
    return Response.json([], { headers: { "Cache-Control": "no-store" } });
  }
  const resumenes: LiveConversationSummary[] = [];
  for (const nombre of nombres) {
    try {
      const datos = JSON.parse(await readFile(path.join(LIVE_DIR, nombre), "utf-8")) as Partial<LiveConversation>;
      // Los archivos sin id son de peticiones sueltas (formato anterior): no forman una conversación
      if (!datos.id || !Array.isArray(datos.turns)) continue;
      resumenes.push({ id: datos.id, title: datos.title ?? "", branch: datos.branch ?? "", generation: datos.generation ?? null,
                       created: datos.created ?? "", updated: datos.updated ?? "", turns: datos.turns.length });
    } catch {
      // Un archivo a medio escribir o dañado no debe tumbar el historial completo; se omite
    }
  }
  resumenes.sort((a, b) => b.updated.localeCompare(a.updated));
  return Response.json(resumenes.slice(0, MAX_CONVERSACIONES), { headers: { "Cache-Control": "no-store" } });
}
