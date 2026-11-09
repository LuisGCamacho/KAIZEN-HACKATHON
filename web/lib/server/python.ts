import "server-only";

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

/** Carpeta del backend: la web y el backend viven en el mismo repo (web/ y backend/). */
export const BACKEND = path.resolve(process.cwd(), "..", "backend");
export const LOCK = path.join(BACKEND, "data", "runs", ".lock");
/** Conversaciones de /live (las escribe backend/live.py): el historial del chat. */
export const LIVE_DIR = path.join(BACKEND, "data", "runs", "live");

/** Python del venv del backend (Windows o Unix). KAIZEN_PYTHON lo sobrescribe, p. ej. en el servidor. */
export function pythonPath(): string {
  if (process.env.KAIZEN_PYTHON) return process.env.KAIZEN_PYTHON;
  const venv =
    process.platform === "win32"
      ? path.join(BACKEND, ".venv", "Scripts", "python.exe")
      : path.join(BACKEND, ".venv", "bin", "python");
  if (!existsSync(venv)) {
    throw new Error(`No existe ${venv}. Crea el venv del backend o define KAIZEN_PYTHON.`);
  }
  return venv;
}

/**
 * Lanza un script de backend/ con argumentos fijos. Nunca recibe texto del cliente: eso va por stdin.
 * detached: el proceso sigue vivo aunque termine la petición (corridas de /api/run).
 */
export function runPython(script: string, args: string[] = [], detached = false): ChildProcess {
  // turbopackIgnore: el ejecutable se resuelve en tiempo de ejecución; sin el comentario el build traza todo el repo
  return spawn(/* turbopackIgnore: true */ pythonPath(), ["-u", script, ...args], {
    cwd: BACKEND,
    detached,
    stdio: detached ? "ignore" : "pipe",
    // -u y PYTHONUNBUFFERED: cada evento sale en cuanto se emite; UTF-8 para los acentos en Windows
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  });
}
