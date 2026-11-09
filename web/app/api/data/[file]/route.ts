import { readFile } from "node:fs/promises";
import path from "node:path";

import type { DataFiles } from "@/lib/types";

/**
 * Sirve los JSON que escribe backend/evaluation/export.py leyéndolos del disco en cada petición.
 * public/ solo garantiza los archivos que existían al hacer el build; estos cambian durante la corrida
 * (y en Docker viven en un volumen montado después del build).
 */
const ARCHIVOS: readonly (keyof DataFiles)[] = [
  "reports.json", "clusters.json", "artifacts.json", "lineage.json", "traces.json", "progress.json",
];
const WEB_DATA = path.join(/* turbopackIgnore: true */ process.cwd(), "public", "data");

export async function GET(_request: Request, { params }: { params: Promise<{ file: string }> }) {
  const { file } = await params;
  // Allowlist: el nombre nunca se usa para construir una ruta si no es uno de los 6 archivos del contrato
  if (!ARCHIVOS.includes(file as keyof DataFiles)) {
    return Response.json({ error: "archivo desconocido" }, { status: 404 });
  }
  try {
    const contenido = await readFile(path.join(WEB_DATA, file), "utf-8");
    return new Response(contenido, {
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") {
      return Response.json({ error: "sin datos todavía" }, { status: 404 });
    }
    console.error(`/api/data/${file}:`, e);
    return Response.json({ error: "error interno del servidor" }, { status: 500 });
  }
}
