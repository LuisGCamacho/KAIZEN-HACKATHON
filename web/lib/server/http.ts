import "server-only";

type Lectura = { ok: true; valor: unknown } | { ok: false; respuesta: Response };

/**
 * Lee un cuerpo JSON cortando en cuanto supera maxBytes. request.text() cargaría en memoria un cuerpo
 * enorme completo antes de poder rechazarlo, y estas rutas son públicas.
 */
export async function leerJsonLimitado(request: Request, maxBytes: number): Promise<Lectura> {
  const demasiadoGrande = {
    ok: false as const,
    respuesta: Response.json({ error: "petición demasiado grande" }, { status: 413 }),
  };
  const declarado = Number(request.headers.get("content-length") ?? 0);
  if (declarado > maxBytes) return demasiadoGrande;
  if (!request.body) return { ok: true, valor: {} };

  const lector = request.body.getReader();
  const trozos: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await lector.cancel();
      return demasiadoGrande;
    }
    trozos.push(value);
  }
  const texto = Buffer.concat(trozos).toString("utf-8");
  try {
    return { ok: true, valor: texto.trim() ? JSON.parse(texto) : {} };
  } catch {
    return { ok: false, respuesta: Response.json({ error: "JSON inválido" }, { status: 400 }) };
  }
}

/** Registra el detalle en el log del servidor y devuelve al cliente un mensaje sin rutas ni trazas. */
export function errorInterno(contexto: string, e: unknown): Response {
  console.error(`${contexto}:`, e);
  return Response.json({ error: "error interno del servidor" }, { status: 500 });
}
