import { existsSync, readFileSync } from "node:fs";

import { exigirAdmin } from "@/lib/server/admin";
import { errorInterno, leerJsonLimitado } from "@/lib/server/http";
import { LOCK, runPython } from "@/lib/server/python";

/**
 * Allowlist: cada comando se traduce a argumentos fijos de run.py. El texto del cliente nunca llega a Python.
 * control: ablación que nace de main/gen_2 sin meta-destilador (docs/CONTRATOS.md §7).
 */
const COMMANDS: Record<string, string[]> = {
  next: ["next"],
  gen0: ["gen0"],
  control: ["next", "--branch", "control", "--fork-from", "2", "--no-meta-distiller"],
  reset: ["reset"],
};
const BRANCHES = ["main", "smoke"]; // ramas que acepta "next"; control tiene su propio comando
const CONFIRMACION_RESET = "RESET";
// run.py tarda en crear el lock tras arrancar; en esa ventana un segundo clic también debe recibir 409
const VENTANA_ARRANQUE_MS = 5_000;

const MAX_BODY_BYTES = 1024; // el cuerpo es un comando corto

let ultimoLanzamiento = 0;

/** PID de la corrida activa según el lock, o null si no hay una viva. */
function pidDeLaCorrida(): number | null {
  if (!existsSync(LOCK)) return null;
  const pid = Number(readFileSync(LOCK, "utf-8").trim());
  if (!Number.isInteger(pid) || pid <= 0) return null;
  try {
    process.kill(pid, 0);
    return pid;
  } catch {
    return null;
  }
}

/**
 * Cancela la corrida: SIGTERM a su grupo de procesos (run.py se lanza desacoplado y es líder de su grupo),
 * así mueren también los `codex exec` que lanzó. run.py atrapa la señal, marca la corrida como cancelada en
 * progress.json y libera el lock.
 */
function cancelar(): Response {
  const pid = pidDeLaCorrida();
  if (pid === null) return Response.json({ error: "no hay una corrida en curso" }, { status: 409 });
  try {
    process.kill(-pid, "SIGTERM");
  } catch {
    process.kill(pid, "SIGTERM"); // lanzada a mano (docker exec): no es líder de grupo
  }
  return Response.json({ cancelled: pid }, { status: 202 });
}

/** El lock cuenta solo si su PID sigue vivo; uno huérfano (reinicio o crash) lo reemplaza run.py. */
function corridaEnCurso(): boolean {
  if (Date.now() - ultimoLanzamiento < VENTANA_ARRANQUE_MS) return true;
  if (!existsSync(LOCK)) return false;
  const pid = Number(readFileSync(LOCK, "utf-8").trim());
  if (!Number.isInteger(pid) || pid <= 0) return true; // lock ilegible: mejor no lanzar otra corrida
  try {
    process.kill(pid, 0); // señal 0: solo comprueba que el proceso existe
    return true;
  } catch (e) {
    // EPERM: existe pero es de otro usuario
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

export async function POST(request: Request) {
  const lectura = await leerJsonLimitado(request, MAX_BODY_BYTES);
  if (!lectura.ok) return lectura.respuesta;
  const body = (lectura.valor ?? {}) as { command?: unknown; branch?: unknown; confirm?: unknown };
  const sinPermiso = exigirAdmin(request);
  if (sinPermiso) return sinPermiso;
  const command = typeof body.command === "string" ? body.command : "next";
  if (command === "cancel") return cancelar();
  if (!Object.hasOwn(COMMANDS, command)) {
    return Response.json({ error: "comando desconocido" }, { status: 400 });
  }
  if (command === "reset" && body.confirm !== CONFIRMACION_RESET) {
    return Response.json({ error: `reset exige {"confirm": "${CONFIRMACION_RESET}"}` }, { status: 400 });
  }
  if (body.branch !== undefined && (typeof body.branch !== "string" || !BRANCHES.includes(body.branch))) {
    return Response.json({ error: `rama no permitida (usa ${BRANCHES.join(" o ")})` }, { status: 400 });
  }
  if (corridaEnCurso()) {
    return Response.json({ error: "ya hay una corrida en curso" }, { status: 409 });
  }

  const args = command === "next" && body.branch ? ["next", "--branch", body.branch as string] : COMMANDS[command];
  let child;
  try {
    child = runPython("run.py", args, true); // desacoplado: sigue aunque termine la petición
  } catch (e) {
    return errorInterno("/api/run no pudo lanzar Python", e);
  }
  ultimoLanzamiento = Date.now();
  // Sin este manejador, un fallo asíncrono de spawn (p. ej. KAIZEN_PYTHON mal escrito) tumbaría el servidor
  child.on("error", (e) => console.error(`run.py no arrancó: ${e.message}`));
  child.unref();
  // El progreso no va en la respuesta: run.py actualiza progress.json y la web lo consulta cada 2-3 s
  return Response.json({ started: command, pid: child.pid }, { status: 202 });
}
