import "server-only";

import { timingSafeEqual } from "node:crypto";

/** Cabecera con la que la web manda la clave de administrador (la pide una vez y la recuerda el navegador). */
export const CABECERA_ADMIN = "x-kaizen-admin";

/**
 * Las acciones que gastan créditos o borran datos (correr, cancelar, reset) exigen KAIZEN_ADMIN_KEY.
 * Sin la variable (desarrollo local) se permiten; en el servidor público debe estar definida.
 * Devuelve la respuesta 401 a enviar, o null si la petición está autorizada.
 */
export function exigirAdmin(request: Request): Response | null {
  const esperada = process.env.KAIZEN_ADMIN_KEY;
  if (!esperada) return null;
  const recibida = request.headers.get(CABECERA_ADMIN) ?? "";
  const a = Buffer.from(recibida);
  const b = Buffer.from(esperada);
  // Comparación en tiempo constante: no revela por cuánto se acerca una clave equivocada
  if (a.length === b.length && timingSafeEqual(a, b)) return null;
  return Response.json({ error: "clave de administrador incorrecta" }, { status: 401 });
}
