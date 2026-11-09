import { errorInterno } from "@/lib/server/http";
import { runPython } from "@/lib/server/python";

/**
 * GET /api/excel?branch=main → el .xlsx de Evolución (tabla con formato, resumen y gráficas).
 * Lo arma backend/exportar_excel.py con los mismos datos de reports.json que ve la vista.
 */
const BRANCHES = ["main", "smoke", "control"]; // allowlist: la rama llega a Python como argumento fijo
const TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const LIMITE_MS = 30_000; // generar el archivo tarda menos de un segundo; más es un proceso colgado

type Salida = { codigo: number | null; datos: Buffer; error: string };

function ejecutar(branch: string): Promise<Salida> {
  return new Promise((resolve, reject) => {
    const child = runPython("exportar_excel.py", ["--branch", branch]);
    const datos: Buffer[] = [];
    const errores: Buffer[] = [];
    const reloj = setTimeout(() => child.kill(), LIMITE_MS);
    child.stdout!.on("data", (trozo: Buffer) => datos.push(trozo));
    child.stderr!.on("data", (trozo: Buffer) => errores.push(trozo));
    // Sin este manejador, un fallo de spawn (p. ej. KAIZEN_PYTHON mal escrito) tumbaría el servidor
    child.on("error", (e) => { clearTimeout(reloj); reject(e); });
    child.on("close", (codigo) => {
      clearTimeout(reloj);
      resolve({ codigo, datos: Buffer.concat(datos), error: Buffer.concat(errores).toString("utf-8").trim() });
    });
  });
}

export async function GET(request: Request) {
  const branch = new URL(request.url).searchParams.get("branch") ?? "main";
  if (!BRANCHES.includes(branch)) {
    return Response.json({ error: `rama no permitida (usa ${BRANCHES.join(", ")})` }, { status: 400 });
  }
  let salida: Salida;
  try {
    salida = await ejecutar(branch);
  } catch (e) {
    return errorInterno("/api/excel no pudo lanzar Python", e);
  }
  if (salida.codigo !== 0 || salida.datos.length === 0) {
    return errorInterno("/api/excel: exportar_excel.py falló", new Error(salida.error || `código ${salida.codigo}`));
  }
  return new Response(new Uint8Array(salida.datos), {
    headers: {
      "Content-Type": TIPO_XLSX,
      "Content-Disposition": `attachment; filename="kaizen-${branch}-generaciones.xlsx"`,
      "Cache-Control": "no-store",
    },
  });
}
