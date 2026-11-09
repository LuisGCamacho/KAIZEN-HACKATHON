import { errorInterno, leerJsonLimitado } from "@/lib/server/http";
import { runPython } from "@/lib/server/python";

/** Límites de la demo pública: el servidor es compartido y cada conversación gasta presupuesto. */
const MAX_BODY_BYTES = 64 * 1024;
const MAX_PROCESOS_SIMULTANEOS = 4;
const TIMEOUT_MS = 180_000; // una conversación con supervisor y varias tools tarda menos de 1 minuto
const MAX_STDERR = 2_000; // solo el final del error de Python, para el log del servidor
const PATRON_RAMA = /^[a-z0-9_-]{1,32}$/;

let procesosActivos = 0;

const encoder = new TextEncoder();
const lineaError = (message: string) =>
  encoder.encode(JSON.stringify({ t: Date.now(), type: "error", message }) + "\n");

type Generacion = number | "best" | "latest";

function generacionValida(valor: unknown): valor is Generacion {
  return valor === "best" || valor === "latest" || (Number.isInteger(valor) && (valor as number) >= 0);
}

export async function POST(request: Request) {
  const lectura = await leerJsonLimitado(request, MAX_BODY_BYTES);
  if (!lectura.ok) return lectura.respuesta;
  const body = (lectura.valor ?? {}) as { messages?: unknown; generation?: unknown; branch?: unknown };
  if (!Array.isArray(body.messages)) {
    return Response.json({ error: "messages debe ser una lista" }, { status: 400 });
  }
  const branch = typeof body.branch === "string" && PATRON_RAMA.test(body.branch) ? body.branch : "main";
  const generation = generacionValida(body.generation) ? body.generation : "best";

  if (procesosActivos >= MAX_PROCESOS_SIMULTANEOS) {
    return Response.json({ error: "demasiadas conversaciones a la vez; intenta en unos segundos" }, { status: 429 });
  }

  let child;
  try {
    child = runPython("live.py");
  } catch (e) {
    return errorInterno("/api/live no pudo lanzar Python", e);
  }
  procesosActivos++;
  let liberado = false;
  // 'close' puede no llegar tras un 'error' de spawn: el cupo se libera una sola vez desde cualquiera
  const liberar = () => {
    if (!liberado) {
      liberado = true;
      procesosActivos--;
    }
  };
  // Si Python muere antes de leer stdin, el EPIPE lo reporta el manejador de 'close' con el código de salida
  child.stdin!.on("error", () => undefined);
  // El texto del cliente va por stdin como JSON, nunca como argumento de línea de comandos
  child.stdin!.end(JSON.stringify({ messages: body.messages, generation, branch }));

  let stderr = "";
  child.stderr!.on("data", (c: Buffer) => {
    stderr = (stderr + c.toString("utf-8")).slice(-MAX_STDERR);
  });

  // closed evita escribir en un stream ya cerrado: sin él, Detener provoca «Controller is already closed»
  let closed = false;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const cerrar = () => {
        if (!closed) {
          closed = true;
          controller.close();
        }
      };
      const limite = setTimeout(() => {
        if (!closed) controller.enqueue(lineaError(`la conversación superó ${TIMEOUT_MS / 1000} s`));
        child.kill();
      }, TIMEOUT_MS);

      child.stdout!.on("data", (c: Buffer) => {
        if (!closed) controller.enqueue(new Uint8Array(c));
      });
      child.on("error", (e) => {
        clearTimeout(limite);
        liberar();
        console.error("/api/live: error del proceso de Python:", e);
        if (!closed) controller.enqueue(lineaError("no se pudo ejecutar el agente"));
        cerrar();
      });
      child.on("close", (code) => {
        clearTimeout(limite);
        liberar();
        // live.py emite sus propios errores y sale con 0; otro código es un fallo que no alcanzó a reportar
        if (code !== 0 && code !== null && !closed) {
          // El traceback trae rutas del servidor: va al log, no al público de la demo
          console.error(`/api/live: live.py terminó con código ${code}:\n${stderr.trim() || "sin detalle"}`);
          controller.enqueue(lineaError(`el agente terminó con un error interno (código ${code})`));
        }
        cerrar();
      });
    },
    cancel() {
      closed = true;
      child.kill();
    },
  });

  request.signal.addEventListener("abort", () => child.kill()); // botón Detener

  return new Response(stream, {
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no", // que un proxy (nginx/Caddy) no acumule el stream
    },
  });
}
