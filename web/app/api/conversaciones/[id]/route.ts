import { readFile, unlink } from "node:fs/promises";
import path from "node:path";

import { LIVE_DIR } from "@/lib/server/python";

// Mismo patrón que backend/live.py: solo hex y guiones, así el id nunca forma una ruta fuera de live/
const PATRON_ID = /^[a-f0-9-]{8,64}$/;

function ruta(id: string): string | null {
  return PATRON_ID.test(id) ? path.join(/* turbopackIgnore: true */ LIVE_DIR, `${id}.json`) : null;
}

/** Una conversación completa del historial de /live. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const archivo = ruta((await params).id);
  if (!archivo) return Response.json({ error: "id inválido" }, { status: 400 });
  try {
    return new Response(await readFile(archivo, "utf-8"), {
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ error: "no existe esa conversación" }, { status: 404 });
  }
}

/** Borra una conversación del historial. */
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const archivo = ruta((await params).id);
  if (!archivo) return Response.json({ error: "id inválido" }, { status: 400 });
  try {
    await unlink(archivo);
    return new Response(null, { status: 204 });
  } catch {
    return Response.json({ error: "no existe esa conversación" }, { status: 404 });
  }
}
