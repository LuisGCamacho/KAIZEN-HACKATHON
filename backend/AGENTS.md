# AGENTS.md · backend de KAIZEN

Contexto para agentes de código que trabajan en `backend/`. Léelo completo antes de cambiar algo: varias reglas de aquí son las que hacen que la métrica sea honesta, y romperlas no da error, solo invalida los resultados.

## Qué es KAIZEN

Una **fábrica de agentes que se mejora sola en tres niveles**:

1. **Nivel 1 · el agente.** Un agente de operaciones de una agencia de autos seminuevos (cotizaciones, garantías, logística, trámites) se evalúa sobre 120 tareas. El **destilador** lee sus fallos y escribe la siguiente generación: prompt nuevo, playbooks, tools sintetizadas y, si conviene, otra topología.
2. **Nivel 2A · el juez.** Un juez LLM estima si cada respuesta pasa. El **meta-juez** compara al juez con el verificador programático y reescribe la rúbrica del juez.
3. **Nivel 2B · el destilador.** Si la mejora por generación se estanca o cae, el **meta-destilador** reescribe el prompt del propio destilador.

El backend es el motor: corre el agente, califica, destila y exporta JSON. La interfaz (`web/`) solo lee esos JSON y lanza dos scripts de Python. No hay base de datos ni otro servidor.

## Arranque

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cp .env.example .env                              # pon OPENAI_API_KEY
```

Usa siempre el Python del venv (`.venv/Scripts/python` en Windows). Dependencias: `openai`, `python-dotenv`, `pytest` y `pytest-timeout`. No agregues dependencias sin avisar al equipo.

## Comandos

| Comando | Qué hace | Costo |
|---|---|---|
| `python -m pytest` | Tests del entorno, el verificador, el gate y el reset. **No llama al LLM.** | 0 |
| `python run.py smoke` | Pipeline real completo sobre 10 tareas (2 por familia), rama `smoke` | centavos |
| `python run.py gen0` | Evalúa la línea base: 120 tareas × semillas de `KAIZEN_SEEDS` | ~dólares |
| `python run.py next [--branch B] [--fork-from N] [--no-meta-distiller]` | Destila y evalúa una generación más | ~dólares |
| `python run.py loop --until N` | Hace gen0 si falta y luego `next` hasta la generación N | alto |
| `python run.py export` | Regenera `web/public/data/*.json` desde `data/runs/` | 0 |
| `python run.py reset [--dry]` | Borra todo lo de las generaciones ≥ 1 y deja gen 0. `--dry` solo lista lo que borraría | 0 |
| `python run.py rescore [--trato]` | Vuelve a pasar el verificador sobre las trazas guardadas | 0 (o LLM con `--trato`) |

`--commit` hace un commit de git por generación. **No corras `gen0`, `next` ni `loop` sin que te lo pidan:** gastan presupuesto real. Para validar un cambio, primero `pytest` y luego, si hace falta, `smoke`.

## Mapa del código

```
backend/
├── run.py              CLI: orquesta evaluar → destilar → evaluar. Crea data/runs/.lock
├── live.py             Demo en vivo: lee JSON por stdin y emite eventos NDJSON por stdout
├── core/
│   ├── contracts.py    CONTRATOS de datos (Step, Verdict, Trace, AgentSpec, GenerationReport). Espejo: web/lib/types.ts
│   ├── llm.py          ÚNICO cliente OpenAI: chat(), chat_json(), costo, reintentos, BudgetExceeded
│   ├── paths.py        Todas las rutas (ROOT, DATA, RUNS, SPECS, WEB_DATA…) y rel()
│   ├── progress.py     progress.json en vivo (escritura atómica) + registro.log
│   ├── artifacts.py    Registro data/meta/artifacts.json (sin duplicados por gen/rama/nombre)
│   ├── versions.py     Versionado de rubrica_vN.md y distiller_prompt_vN.md con su historial
│   └── reset.py        Plan y aplicación del reset a gen 0
├── env/                EL ENTORNO. Determinista, sin LLM
│   ├── inventario.py   200 autos con semilla 7. Congelado
│   ├── tools.py        Las 8 tools base (FUNCIONES + ESQUEMAS)
│   ├── tareas.py       Las 120 tareas; `expected` se CALCULA con las tools
│   └── verificador.py  Métrica oficial: binaria, sin LLM, devuelve Verdict(passed, reason)
├── agents/
│   ├── agent.py        Bucle ReAct + topología supervisor (sub-agentes como tools delegar_<x>)
│   └── builder.py      spec gen_N.json → agente listo (carga tools generadas en caliente)
├── evaluation/
│   ├── evals.py        Harness: corre episodios en paralelo, verifica, juzga, arma el GenerationReport
│   ├── judge.py        Juez LLM (p_pasa, explicación). Nunca decide la métrica
│   ├── trato.py        Nota de trato al cliente (criterio fijo)
│   ├── history.py      reports.json por rama, agregados entre semillas, best/latest generation
│   ├── rescore.py      Recalifica trazas guardadas con el verificador actual
│   └── export.py       Escribe web/public/data/*.json para la interfaz
├── improve/
│   ├── distiller.py    Nivel 1: clusters de fallos → playbooks + tool + prompt + topología
│   ├── tool_synth.py   El LLM escribe una tool + sus tests; el gate (AST + pytest) decide
│   ├── meta_judge.py   Nivel 2A: reescribe la rúbrica si el juez discrepa del verificador
│   └── meta_distiller.py  Nivel 2B: reescribe el prompt del destilador si el delta cae
├── tests/              test_env.py (entorno) y test_rsi.py (auto-mejora, gate, reset)
└── data/               TODO lo que el sistema escribe. Aquí no vive código escrito a mano
    ├── prompts/        gen_0.md y estilo.md a mano; el resto lo escribe el destilador
    ├── playbooks/      <reason>_g<N>[_<rama>].md
    ├── specs/<rama>/   gen_N.json (AgentSpec)
    ├── tools/generated/  tools aceptadas (.py + test_*.py + .json con su esquema)
    ├── tools/rejected/   tools rechazadas, como evidencia
    ├── meta/           rubrica_vN.md, distiller_prompt_vN.md, *_history.json, artifacts.json
    └── runs/<rama>/gen_N/seed_S.jsonl, runs/<rama>/reports.json, spend.json, .lock, live/
```

## El ciclo de una generación (`run.py siguiente`)

1. Carga la spec del padre y sus trazas.
2. **Meta-juez:** con 3 o más discrepancias de más de 0.5 entre juez y verificador, reescribe la rúbrica.
3. **Meta-destilador:** si el último delta en held-out fue menor que el anterior, o ≤ 0, reescribe el prompt del destilador.
4. **Destilador:** toma solo los fallos de **train**, agrupa por `reason` y, para las 3 causas más frecuentes, escribe un playbook e intenta sintetizar una tool. Reescribe el prompt de sistema. La topología y los sub-agentes se heredan del padre. **Pendiente:** pasar a `supervisor` cuando más del 40 % de los fallos sean de `logistica` o `tramite`; hoy `builder.build()` solo acepta `single_react` y rechaza `supervisor`.
5. Guarda `specs/<rama>/gen_N.json` y exporta.
6. Evalúa con cada semilla, guarda trazas y reportes, y exporta.

El prompt final del agente es `prompt de la generación` + `## Procedimiento aprendido` (cada playbook). Lo arma `builder.instrucciones()`. **Pendiente:** el bloque `## Trato al cliente` con `estilo.md`; ni `estilo.md` ni `evaluation/trato.py` existen todavía, y `run.py rescore --trato` avisa que falta.

## Ramas

- `main`: la línea principal.
- `smoke`: prueba barata sobre 10 tareas. No hereda de main.
- `control`: ablación. Nace de main en `--fork-from 2` (default) y corre con `--no-meta-distiller`. Hereda de main las specs, las trazas y los reportes hasta el fork.

`export.py` y `history.py` asumen fork en 2 para `control`. Si cambias el fork, revisa los dos.

## Invariantes: NO romper

1. **El destilador nunca ve held-out.** `distiller.fallos_de_train()` filtra `split == "train"`. Las primeras 8 tareas de cada familia (40 en total) son held-out, y la métrica que se presume es `heldout_success`. Hay un test que lo vigila (`test_el_destilador_nunca_ve_heldout`).
2. **El verificador es la única verdad.** Es binario y sin LLM. El juez y el trato solo calibran y se muestran; nunca deciden `passed`.
3. **`expected` se calcula con las tools**, nunca se escribe a mano. Si cambias una tool, cambian las respuestas correctas. Corre `pytest` y, si hay trazas viejas, `run.py rescore`.
4. **El entorno es determinista, salvo la fecha.** El inventario usa semilla 7 y tiene 200 autos. `env/tools.HOY` es la fecha real del día (`date.today()`); las fechas de inspección de las tareas se calculan a partir de ella, así que sus folios esperados cambian de un día a otro. Una corrida que cruza la medianoche mezcla dos días, y `rescore` debe calificar contra el `expected` guardado en cada `Trace`, no contra el de `env/tareas.py`. Las tools son funciones puras y **nunca lanzan excepción**: devuelven `{"error": ...}` o `{"ok": false, "motivo": ...}`.
5. **Todo el LLM pasa por `core/llm.py`** (`chat()` o `chat_json()`). Nadie más importa `openai` para llamar al modelo; solo se importa para capturar sus excepciones. Ahí viven el contador de gasto y la guardia `BudgetExceeded`.
6. **`estilo.md` (trato) es fijo.** El destilador no escribe reglas de tono; las agrega el sistema.
7. **Sin datos inventados.** Si el juez o el trato fallan, la nota queda en `None`. Nunca se rellena.
8. **Escritura atómica a `web/public/data/`:** se escribe `archivo.tmp` y luego `replace`. La interfaz hace polling y no debe leer un JSON a medias.
9. **Rutas:** usa `core/paths.py`. Las rutas guardadas en specs y artefactos son relativas a `data/` y usan `/` (`paths.rel()`).
10. **Las conversaciones de `live.py` no entran al aprendizaje.** Se guardan en `data/runs/live/`.
11. **Una sola corrida a la vez:** `run.py` mantiene tomado durante toda la corrida un candado del sistema operativo (`data/runs/.corrida.candado`) y escribe `data/runs/.lock` con su PID para que lo vea `/api/run`. Si run.py muere (crash o reinicio), el sistema libera el candado y el `.lock` huérfano se reemplaza solo: no hay que borrar nada a mano.
12. **El gate de tools es un filtro, no un sandbox.** Usa una allowlist de imports (`env.tools`, `env.inventario`, `math`, `datetime`, `typing`), prohíbe builtins peligrosos y dunders, y corre pytest con timeout. Solo es apto para uso local.
13. **El gasto se suma sobre `spend.json`, no en memoria:** `run.py` y cada `live.py` son procesos distintos que gastan a la vez. `llm.CONTADOR_GASTO` relee el archivo bajo un candado entre procesos (`spend.json.lock`); `total_usd` es de solo lectura.

## Contratos (`core/contracts.py` ↔ `web/lib/types.ts`)

- **Se agregan campos; nunca se renombran ni cambian de tipo.** Todo campo nuevo lleva valor por defecto, para no romper los JSON viejos (`Trace.from_dict` y `AgentSpec(**d)` fallarían).
- Un cambio de contrato toca `contracts.py` **y** `web/lib/types.ts` en el mismo commit, y se avisa a front.
- Lo que la web consume no son los dataclasses tal cual, sino lo que arma `evaluation/export.py`:

| Archivo en `web/public/data/` | Lo escribe | Tipo en `types.ts` |
|---|---|---|
| `reports.json` | `export.export_all()` | `ReportsFile` |
| `clusters.json` | `export.clusters()` | `Cluster[]` |
| `artifacts.json` | `core/artifacts.py` vía export | `Artifact[]` |
| `lineage.json` | `export.lineage()` + `meta_versions()` | `LineageFile` |
| `traces.json` | `export.comparisons()` (gen 0 vs. la última, semilla 1, máximo 30) | `TracesFile` |
| `progress.json` | `core/progress.py` (la web lo lee cada 2 a 3 s) | `Progress` |

Si cambias la forma de alguno, actualiza `web/lib/types.ts` y avisa.

### Demo en vivo (`live.py`)

- **Entrada (stdin):** `{"messages": [{role, content}], "generation": N | "best" | "latest", "branch": "main"}`
- **Salida (stdout, una línea JSON por evento con `t` en ms):**
  - `start`: `{generation, branch, topology, sub_agents, tools, playbooks}`
  - `delegate`: `{agent, to, query}`
  - `tool_call`: `{agent, tool, args, generated}`
  - `tool_result`: `{agent, tool, summary, ok, ms}`
  - `message`: `{agent, text}`
  - `final`: `{agent, text, tokens, cost_usd, steps, exhausted}`
  - `error`: `{message}`
- Siempre termina en `final` o en `error`, y hace `flush` en cada línea. Usa el mismo `builder.build()` que la evaluación, con `temperature=0`.

## El dominio (para no adivinar)

- **Ciudades y estados:** CDMX → CDMX, GDL → Jalisco, MTY → Nuevo Leon, MID → Yucatan, PUE → Puebla. Las tools aceptan alias ("Guadalajara", "Mérida"…).
- **Familias:**

| Familia | Prefijo | Etiquetas de fallo |
|---|---|---|
| `cotizacion` | `coti` | `mensualidad_excede_tope`, `faltaron_opciones` |
| `garantia` | `gara` | `respuesta_ambigua`, `garantia_mal_interpretada`, `garantia_sin_sustento` |
| `logistica` | `logi` | `plazo_mal_calculado`, `ruta_sin_cobertura`, `dias_incorrectos`, `inspeccion_no_agendada` |
| `tramite` | `trmt` | `tramite_incompleto`, `dias_incorrectos` |
| `trampa` | `trap` | `trampa_no_rechazada` |

  Son 24 tareas por familia.
- **Reglas globales del verificador, antes de revisar la familia:** usar `escalar_humano` da `escalado_innecesario`, y agotar los pasos da `pasos_agotados`.
- **El verificador lee el texto:** la primera palabra decide sí/no, los IDs tienen el formato `A\d{3}`, los días son enteros de 1 a 3 dígitos y los folios empiezan con `INS-`.
- **Reglas ocultas que el agente debe descubrir:**
  - Motor o transmisión con más de 100 000 km: 12 meses de garantía.
  - Falla eléctrica en un modelo 2018 o anterior: 6 meses.
  - Domingo: sucursal cerrada.
  - Días 1 y 15: agenda llena.
  - MID↔GDL y MID↔MTY: sin cobertura.
- "Hoy" en las tareas es la fecha real del día en que corre el proceso (`env/tools.HOY`).
- La lista oficial de etiquetas está en `env/verificador.py` (`REASONS`). Agregar una implica avisar a front, porque la vista Autopsia agrupa por ellas.

## Variables de entorno (`backend/.env`, nunca a git)

| Variable | Valor por defecto | Uso |
|---|---|---|
| `OPENAI_API_KEY` | — | Obligatoria |
| `OPENAI_BASE_URL` | — | Servidor compatible con OpenAI. Con `localhost`, el costo es 0 y el timeout sube a 600 s |
| `MODEL_AGENT` | `gpt-4.1-mini` | Agente evaluado, juez y trato |
| `MODEL_SMART` | `gpt-4.1` | Destilador, síntesis de tools y meta-loop |
| `BUDGET_USD` | `20` | Corte duro del gasto acumulado en `data/runs/spend.json` |
| `PRICE_<MODELO>` | — | `entrada,salida[,cache]` en USD por millón de tokens, para modelos que no estén en la tabla de `llm.py`. Sin precio se asume el de gpt-4.1; sin `cache`, la entrada en caché se cobra como entrada normal |
| `KAIZEN_SEEDS` | `1,2,3` | Semillas por generación |
| `KAIZEN_WORKERS` | `8` | Episodios en paralelo (1 con un modelo local) |
| `KAIZEN_PYTHON` | `backend/.venv/…/python` | **Lo lee la web**, no el backend (`web/.env.local` o el entorno del servicio): intérprete con el que `/api/run` y `/api/live` lanzan Python |

## Convenciones

- Python 3 con `from __future__ import annotations`, type hints y dataclasses. Los scripts de entrada (`run.py`, `live.py`) insertan `backend/` en `sys.path`; los imports son absolutos desde ahí (`from core import llm`).
- **Nombres, comentarios, logs y prompts en español.** Los identificadores de contrato están en inglés (`task_id`, `heldout_success`): respétalos.
- Siempre `encoding="utf-8"` al leer o escribir, y `ensure_ascii=False` en `json.dumps`. Corre en Windows.
- Para los logs de corrida usa `progress.linea()` o el `log()` que se recibe como parámetro, no `print` suelto; así aparecen en la interfaz.
- Los errores que ve el usuario de la demo se emiten como evento `error`; no se dejan caer en silencio.
- Funciones cortas y comentarios que explican el *porqué*. Sigue el estilo de los archivos existentes.

## Antes de terminar un cambio

1. `.venv/Scripts/python -m pytest`. Debe pasar completo.
2. Si tocaste el entorno o el verificador: `run.py rescore`, si ya hay trazas.
3. Si tocaste el export o los contratos: `run.py export` y revisa que `web/lib/types.ts` siga coincidiendo.
4. Si tocaste el agente, el destilador o el meta-loop: `run.py smoke`, solo si te lo autorizan.
5. No subas `.env`, `.venv/`, `data/runs/spend.json`, `.lock`, `registro.log` ni `progress.json` (ya están en `.gitignore`).

## Guías del equipo (`skills/` en la raíz)

Aplícalas siempre. Lee la guía correspondiente antes de escribir código:

| Guía | Cuándo |
|---|---|
| [`codigo-limpio`](../skills/codigo-limpio.md) | Siempre que escribas o revises código: simple, legible y la claridad antes que la eficiencia |
| [`sin-hardcode`](../skills/sin-hardcode.md) | Hay números, rutas, URLs, claves, modelos o colores literales |
| [`comentarios-objetivos`](../skills/comentarios-objetivos.md) | Agregas o revisas comentarios y docstrings |
| [`diseno-frontend`](../skills/diseno-frontend.md) | Creas o cambias vistas, componentes o gráficas en `web/` |
