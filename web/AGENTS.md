<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# AGENTS.md · interfaz web de KAIZEN

Contexto para agentes de código que trabajan en `web/`. Léelo antes de cambiar algo.

## Qué es KAIZEN y qué hace esta interfaz

KAIZEN es una **fábrica de agentes que se mejora sola en tres niveles**:

1. Un agente de operaciones de una agencia de autos se evalúa sobre 120 tareas, y un destilador escribe la siguiente generación a partir de sus fallos.
2. Un meta-juez recalibra al juez LLM contra un verificador programático.
3. Un meta-destilador reescribe el prompt del destilador cuando la mejora se estanca.

El motor vive en `../backend` (Python). **Esta interfaz es solo un visor:**

- Lee archivos JSON estáticos de `public/data/`, que escribe `backend/evaluation/export.py`.
- Lanza Python únicamente desde dos rutas: `POST /api/run` (corridas en segundo plano) y `POST /api/live` (la demo con un cliente, en streaming NDJSON).
- **No hay base de datos, backend propio ni datos de ejemplo.** Sin corridas, cada vista muestra su estado vacío con el comando que hay que correr.

La métrica que se presume es el **éxito en held-out**: 40 tareas (8 por familia) que el destilador nunca ve.

## Stack

- **Next.js 16.4.5** (App Router) y **React 19.3**. Lee el bloque de arriba: consulta `node_modules/next/dist/docs/` antes de usar una API de Next.
- `next.config.ts` activa `cacheComponents` y `partialPrefetching`, y carga Tailwind con `@tailwindcss/turbopack`.
- **Tailwind CSS 4** con tokens en `app/globals.css` (`@theme`). No hay `tailwind.config`.
- **TypeScript strict**, con el alias `@/*` apuntando a la raíz de `web/`.
- Fuentes: Inter (UI) y JetBrains Mono (IDs, código y números), vía `next/font/google` en `app/layout.tsx`.
- Sin librerías de UI ni de gráficas: los componentes y las gráficas SVG están hechos a mano en `components/`.

## Comandos

```bash
npm install
npm run dev      # http://localhost:3000
npm run lint     # eslint (config de next: core-web-vitals + typescript)
npm run build    # verificación de tipos y build de producción
```

Para ver datos reales, el backend tiene que haber corrido algo. La opción más barata es `cd ../backend && .venv/Scripts/python run.py smoke`, pero **no la corras sin permiso** porque gasta presupuesto de API. Para regenerar los JSON a partir de corridas ya hechas, sin costo: `python run.py export`.

## Mapa

```
web/
├── app/
│   ├── layout.tsx            Sidebar + <main>; fuentes; lang="es"
│   ├── globals.css           Tokens del sistema de diseño (@theme)
│   ├── page.tsx              /             → EvolutionView
│   ├── live/page.tsx         /live         → LiveView
│   ├── autopsia/page.tsx     /autopsia     → AutopsyView
│   ├── herramientas/page.tsx /herramientas → ToolsView
│   ├── linaje/page.tsx       /linaje       → LineageView
│   ├── trazas/page.tsx       /trazas       → TracesView
│   └── api/
│       ├── run/route.ts      Lanza run.py en segundo plano (202 / 400 / 409)
│       └── live/route.ts     Lanza live.py y reenvía su stdout NDJSON
├── components/
│   ├── layout/   sidebar, nav-item, page-header, logo, budget-meter
│   ├── ui/       primitivas: card, button, badge, chip, tabs, collapsible, code-block,
│   │             stat-card, label, skeleton, empty-state, data-gate
│   ├── charts/   SVG a mano: fitness-chart, error-bars, delta-bars, generation-bars, sparkline…
│   ├── evolution/ autopsy/ tools/ lineage/ traces/ live/   una carpeta por vista
├── hooks/
│   ├── use-json.ts           Lee /data/<archivo> con polling opcional
│   ├── use-live-session.ts   Conversación + línea de tiempo por generación (modo comparar = 2)
│   └── use-stick-to-bottom.ts
├── lib/
│   ├── types.ts              CONTRATO: espejo de backend/core/contracts.py y de export.py
│   ├── live.ts               Tipos LiveEvent, streamLive(), toTimeline(), activityOf()
│   ├── ndjson.ts             Lector de streams NDJSON
│   ├── generations.ts        primaryBranch(), bestOf() (misma regla que backend/history.py), byBranch()
│   ├── format.ts             pct, signedPct, num, usd, int… (devuelven "—" si no hay número)
│   ├── chart.ts, diff.ts, object.ts, cn.ts
│   └── server/python.ts      server-only: runPython(), BACKEND, LOCK
└── public/data/              JSON que escribe el backend. NO se editan a mano
```

## De dónde sale cada vista

| Ruta | Vista | Archivo(s) | Polling |
|---|---|---|---|
| `/` Evolución | `evolution/evolution-view.tsx` | `reports.json`, `artifacts.json`, `progress.json` | 5 s / 2 s |
| `/live` En vivo | `live/live-view.tsx` | `POST /api/live` + `reports.json` | stream |
| `/autopsia` | `autopsy/autopsy-view.tsx` | `clusters.json` | 5 s |
| `/herramientas` | `tools/tools-view.tsx` | `artifacts.json` | 5 s |
| `/linaje` | `lineage/lineage-view.tsx` | `lineage.json` (+ `progress.json` en el botón de reset) | 5 s |
| `/trazas` | `traces/traces-view.tsx` | `traces.json` | no |
| Sidebar | `run-button`, `budget-meter` | `progress.json`, `reports.json` | 3 s / 10 s |

## Patrones obligatorios

### Datos

- Lee los datos **solo** con `useJson<T>("archivo.json", everyMs?)`, tipado con `lib/types.ts`. Ya evita la caché con `?t=` y `no-store`, y trata el 404 como "sin datos".
- Envuelve cada vista con `<DataGate state isEmpty empty={{ title, body, command }}>`. Resuelve los estados cargando, vacío y con datos en un solo lugar.
- **Nunca inventes datos**: nada de mocks, fixtures ni números de relleno. El estado vacío dice qué falta y qué comando correrlo (`EmptyState`).
- Los valores opcionales del contrato (`null` o ausentes) se muestran con los formateadores de `lib/format.ts`, que devuelven "—".
- **Rama:** usa `primaryBranch()` (main si tiene datos; si no, smoke). La rama `control` es la ablación (fork de main en gen 2, sin meta-destilador) y se dibuja como comparación.
- **"Mejor generación":** usa `bestOf()`. Tiene que seguir la misma regla que `backend/evaluation/history.py` (mayor `heldout_mean`; en empate, la más nueva).

### Rutas API (seguridad)

- `/api/run` solo acepta comandos de una **allowlist** (`next`, `gen0`, `control`, `reset`) que se traducen a argumentos fijos. **El texto del cliente nunca se pasa como argumento a Python.** Las ramas también pasan por allowlist (`main` y `smoke`).
- Si existe `backend/data/runs/.lock`, `/api/run` responde 409: solo puede haber una corrida a la vez.
- `/api/live` valida la rama con `^[a-z0-9_-]{1,32}$`, pasa la conversación **por stdin**, reenvía stdout sin tocarlo y mata el proceso cuando la petición se aborta (botón Detener). Si Python termina con un código distinto de 0, emite un evento `error`.
- Todo lo que lanza procesos vive en `lib/server/` e importa `"server-only"`. Busca el Python del venv del backend (Windows o Unix); `KAIZEN_PYTHON` lo sobrescribe.

### Componentes

- Los componentes de las vistas son `"use client"`, porque usan hooks y polling. Los `page.tsx` son de servidor y solo arman `PageHeader` + la vista.
- Reutiliza las primitivas de `components/ui/` antes de crear otras. Une clases con `cn()`.
- Gráficas en SVG a mano, siguiendo el patrón de `components/charts/` y las utilidades de `lib/chart.ts`.

## Sistema de diseño

- **Ningún componente escribe un color literal.** Usa solo los tokens de `globals.css`:
  - Tinta: `ink`, `ink-2`, `ink-3`, `ink-4`.
  - Superficies: `bg`, `panel`, `soft`, `chip`.
  - Líneas: `line`, `line-strong`, `grid`.
  - Diff: `diff-add`, `diff-del`.
  - Navegación: `nav-active`.
- **Acento único `seal` (#c8322d): SOLO para marcar autoría de la máquina** (artefactos, tools o prompts que escribió el sistema). No lo uses para errores, alertas ni decoración.
- Radios: `rounded-control` (8), `rounded-button` (10), `rounded-card` (12).
- Tamaños de texto: `text-view`, `text-figure`, `text-label`, `text-id`, `text-code`.
- Fuentes: `font-ui` y `font-mono`. IDs (`A012`, `coti_03`), números y código van en mono.
- Estética monocromática y sobria. Tiene foco visible (`:focus-visible`) y un layout que se apila en pantallas angostas (sidebar + main con flex-wrap).
- **Todo el texto de la interfaz va en español** (México: `toLocaleString("es-MX")`).

## Contrato con el backend

- `lib/types.ts` es el **espejo** de `backend/core/contracts.py` y de lo que arma `backend/evaluation/export.py`.
- **Se agregan campos; nunca se renombran ni cambian de tipo.** Un cambio aquí implica un cambio en el backend en el mismo commit, y viceversa. Avisa al otro equipo.
- Los campos nuevos del backend llegan como opcionales: márcalos con `?` o `| null` y manéjalos con "—".
- **Desfases conocidos, corrígelos cuando toques esas zonas:**
  - `Verdict` en `types.ts` no tiene `judge_tone` (el backend sí lo escribe).
  - `GenerationReport` no tiene tipo propio (`ReportsFile.seeds`).
  - `LiveEvent` está definido en `lib/live.ts`, no en `types.ts`, y su `start` no tipa `branch`.

### Eventos de `/api/live` (NDJSON, una línea por evento, campo `t` en ms)

| Evento | Campos |
|---|---|
| `start` | `generation`, `branch`, `topology`, `sub_agents`, `tools`, `playbooks` |
| `delegate` | `agent`, `to`, `query` (topología supervisor) |
| `tool_call` | `agent`, `tool`, `args`, `generated` (`generated: true` significa que la tool la escribió la máquina, y va con `seal`) |
| `tool_result` | `agent`, `tool`, `summary`, `ok`, `ms` |
| `message` | `agent`, `text` |
| `final` | `agent`, `text`, `tokens`, `cost_usd`, `steps`, `exhausted` |
| `error` | `message` |

- La petición es `{ messages: {role, content}[], generation: number | "best" | "latest", branch }`.
- El stream siempre termina en `final` o en `error`. `toTimeline()` empareja cada `tool_call` con su `tool_result`.

## Vocabulario del dominio (para los textos)

- **Familias:** cotización, garantía, logística, trámite y trampa. Son 24 tareas por familia.
- **Split:** `train` es lo que ve el destilador; `heldout` es lo que nunca ve.
- **Topología:** `single_react` o `supervisor` (sub-agentes cotizador, logística y garantía).
- **Artefacto:** un playbook o una tool que produjo el sistema. Las tools pueden quedar aceptadas o rechazadas por el gate, y las rechazadas también se muestran, como evidencia.
- **Etiquetas de fallo (`reason`):** la lista está en `backend/env/verificador.py`. La Autopsia agrupa por ellas.
- **Juez y trato:** se muestran como calibración. **Nunca cuentan en la métrica oficial**, que es la del verificador. Dilo así en la interfaz.

## Antes de terminar un cambio

1. `npm run lint` y `npm run build` sin errores.
2. Revisa la vista **sin datos**: mueve `public/data/` temporalmente o usa una rama vacía, y confirma que el estado vacío se vea bien.
3. Revisa la vista con datos reales, si los hay.
4. No edites `public/data/*.json` a mano ni los subas con datos inventados. `progress.json` está en `.gitignore`.

## Guías del equipo (`skills/` en la raíz)

Aplícalas siempre. Lee la guía correspondiente antes de escribir código:

| Guía | Cuándo |
|---|---|
| [`codigo-limpio`](../skills/codigo-limpio.md) | Siempre que escribas o revises código: simple, legible y la claridad antes que la eficiencia |
| [`sin-hardcode`](../skills/sin-hardcode.md) | Hay números, rutas, URLs, claves, modelos o colores literales |
| [`comentarios-objetivos`](../skills/comentarios-objetivos.md) | Agregas o revisas comentarios y docstrings |
| [`diseno-frontend`](../skills/diseno-frontend.md) | Creas o cambias vistas, componentes o gráficas en `web/` |
