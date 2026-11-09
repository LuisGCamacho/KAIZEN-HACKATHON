# AGENTS.md · KAIZEN

Instrucciones para cualquier agente de código (Codex, Cursor, Copilot, Gemini, Claude, etc.) y para las personas del equipo. Léelo antes de cambiar algo.

## Qué es KAIZEN

Una **fábrica de agentes que se mejora sola en tres niveles**:

1. **El agente.** Un agente de operaciones de una agencia de autos seminuevos se evalúa sobre 120 tareas, y un **destilador** escribe la siguiente generación a partir de sus fallos: prompt, playbooks, tools y topología.
2. **El juez.** Un **meta-juez** recalibra al juez LLM contra un verificador programático.
3. **El destilador.** Un **meta-destilador** reescribe el prompt del destilador cuando la mejora se estanca.

La métrica oficial es el **éxito en held-out**: 40 tareas que el destilador nunca ve, calificadas por un verificador sin LLM.

## Estructura

```
KAIZEN/
├── AGENTS.md          ← este archivo (reglas generales)
├── backend/           Motor en Python: entorno, agente, evaluación, auto-mejora, export
│   └── AGENTS.md      ← contexto y reglas del backend
├── web/               Interfaz en Next.js: solo lee JSON y lanza dos scripts de Python
│   └── AGENTS.md      ← contexto y reglas de la web
├── docs/CONTRATOS.md  Contratos de datos entre áreas
└── skills/            Guías de calidad del equipo (ver abajo)
```

**Si trabajas en `backend/` o `web/`, lee también el `AGENTS.md` de esa carpeta.** Ahí está el mapa del código, los comandos y las reglas que no se pueden romper.

## Guías del equipo (`skills/`)

Son obligatorias para todo el código. Lee la que aplique **antes** de escribir:

| Guía | Cuándo |
|---|---|
| [`skills/codigo-limpio.md`](skills/codigo-limpio.md) | Siempre que escribas o revises código |
| [`skills/sin-hardcode.md`](skills/sin-hardcode.md) | Hay números, rutas, URLs, claves, modelos o colores literales |
| [`skills/comentarios-objetivos.md`](skills/comentarios-objetivos.md) | Agregas o revisas comentarios y docstrings |
| [`skills/diseno-frontend.md`](skills/diseno-frontend.md) | Creas o cambias vistas, componentes o gráficas en `web/` |

### Resumen de las guías

- **Claridad antes que eficiencia.** Escribe código que se entienda en una lectura. Solo optimiza si hay un problema medido.
- **Simple.** Haz lo que se pidió y nada más. No abstraigas antes de tiempo ni agregues opciones "por si acaso".
- **Sin hardcode:**
  - Los secretos van en `.env`.
  - Las rutas, en `backend/core/paths.py`.
  - Los números con significado, en constantes con nombre.
  - Los colores, en los tokens de `web/app/globals.css`.
  - El vocabulario compartido, en los contratos.
- **Comentarios objetivos:** explican el porqué, las restricciones y las reglas del negocio, sin opiniones ni repetir el código.
- **Diseño:** monocromático con tokens, el rojo `seal` solo para lo que escribió la máquina, y estados cargando, vacío y error en cada vista. Accesible y en español.

## Reglas generales del proyecto

1. **Nunca inventes datos.** Nada de mocks, números de relleno ni notas inventadas. Si falta un valor, queda `None` o `null` y la interfaz muestra "—" o su estado vacío.
2. **Contratos:** `backend/core/contracts.py` ↔ `web/lib/types.ts`. Se agregan campos, nunca se renombran ni cambian de tipo. Un cambio toca los dos archivos en el mismo commit y se avisa al otro equipo.
3. **El destilador nunca ve held-out, y el verificador es la única verdad.** No rompas estas dos reglas: invalidan la métrica sin dar error.
4. **No gastes presupuesto sin permiso.** No corras `run.py gen0`, `next`, `loop` ni `smoke` salvo que te lo pidan, porque llaman a la API de pago. `pytest` y `run.py export` son gratis.
5. **Secretos:** nunca subas `backend/.env` ni pongas claves en el código. Si se filtró una clave, hay que rotarla.
6. **Idioma:** código, comentarios, logs y textos de la interfaz en español. Los nombres de campos de contrato se respetan tal cual (`task_id`, `heldout_success`).
7. **Sigue el estilo existente** del archivo que tocas. No reformatees ni renombres código ajeno en el mismo cambio.

## Flujo de trabajo

- Haz cambios pequeños, con un propósito por commit y un mensaje que explique el *porqué*.
- Antes de dar algo por terminado:
  - **Backend:** `cd backend && .venv/Scripts/python -m pytest` (en macOS/Linux, `.venv/bin/python`).
  - **Web:** `cd web && npm run lint && npm run build`.
- Si algo falla o no pudiste verificarlo, dilo explícitamente. No lo des por hecho.
