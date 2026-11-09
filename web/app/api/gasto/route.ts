import { readFile } from "node:fs/promises";
import path from "node:path";

import { BACKEND } from "@/lib/server/python";
import type { Gasto } from "@/lib/types";

const SPEND = path.join(/* turbopackIgnore: true */ BACKEND, "data", "runs", "spend.json");

/**
 * Gasto real acumulado y su tope, para el medidor del sidebar. Se lee de spend.json en cada petición (no de
 * reports.json): así incluye lo que gasta el chat en vivo, que no exporta. Los topes vienen del mismo .env
 * que usa el backend (env_file del contenedor).
 */
export async function GET() {
  let datos: { usd?: number; codex_tokens?: number } = {};
  try {
    datos = JSON.parse(await readFile(SPEND, "utf-8"));
  } catch {
    // Sin spend.json todavía no se ha gastado nada
  }
  const tope = Number(process.env.CODEX_MAX_TOKENS ?? 0);
  const gasto: Gasto = {
    proveedor: process.env.KAIZEN_PROVIDER?.trim().toLowerCase() === "codex" ? "codex" : "openai",
    usd: Number(datos.usd ?? 0),
    presupuesto_usd: Number(process.env.BUDGET_USD ?? 20),
    tokens: Number(datos.codex_tokens ?? 0),
    tope_tokens: tope > 0 ? tope : null,
  };
  return Response.json(gasto, { headers: { "Cache-Control": "no-store" } });
}
