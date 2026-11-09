import type { Generation } from "./types";

/** Columnas del CSV de Evolución: las métricas que se comparan entre generaciones. */
const COLUMNAS: (keyof Generation)[] = [
  "branch", "generation", "seeds", "heldout_mean", "heldout_std", "train_mean", "train_std", "delta",
  "avg_steps", "tool_precision", "judge_correlation", "escalations", "cost_usd", "cost_per_solved", "topology",
];

function celda(valor: unknown): string {
  if (valor === null || valor === undefined) return "";
  const texto = String(valor);
  // RFC 4180: comillas si hay separador, comillas o saltos de línea
  return /[",\n]/.test(texto) ? `"${texto.replaceAll('"', '""')}"` : texto;
}

export function generacionesACsv(filas: Generation[]): string {
  const lineas = [COLUMNAS.join(","), ...filas.map(fila => COLUMNAS.map(c => celda(fila[c])).join(","))];
  return lineas.join("\n") + "\n";
}

/** Descarga un texto como archivo desde el navegador. */
export function descargar(nombre: string, contenido: string, tipo = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([contenido], { type: tipo }));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  enlace.click();
  URL.revokeObjectURL(url);
}
