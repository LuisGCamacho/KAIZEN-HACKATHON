import { runPython } from "@/lib/server/python";

/** Límites de la demo pública: el servidor es compartido y cada conversación gasta presupuesto. */
const MAX_BODY_BYTES = 64 * 1024;
const MAX_PROCESOS_SIMULTANEOS = 4;
const TIMEOUT_MS = 180_000; // una conversación con supervisor y varias tools tarda menos de 1 minuto
const MAX_STDERR = 2_000; // solo el final del error de Python
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
  const texto = await request.text();
  if (texto.length > MAX_BODY_BYTES) {
    return Response.json({ error: "petición demasiado grande" }, { status: 413 });
  }
  let body: { messages?: unknown; generation?: unknown; branch?: unknown };
  try {
    body = JSON.parse(texto);
  } catch {
    return Response.json({ error: "JSON inválido" }, { status: 400 });
  }
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
    return Response.json({ error: e instanceof Error ? e.message : "no se pudo lanzar Python" }, { status: 500 });
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
        if (!closed) controller.enqueue(lineaError(`no se pudo ejecutar Python: ${e.message}`));
        cerrar();
      });
      child.on("close", (code) => {
        clearTimeout(limite);
        liberar();
        // live.py emite sus propios errores y sale con 0; otro código es un fallo que no alcanzó a reportar
        if (code !== 0 && code !== null && !closed) {
          controller.enqueue(lineaError(`live.py terminó con código ${code}: ${stderr.trim() || "sin detalle"}`));
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
