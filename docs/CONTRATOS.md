# Contratos entre áreas

Estos contratos son la frontera entre **BACKEND**, **FRONT** y **AI ENGINEER**. Si se respetan, los tres equipos pueden trabajar en paralelo sin esperarse.

- Python escribe JSON y Next los lee como archivos estáticos. No hay base de datos ni un segundo servidor.
- Next solo lanza Python, desde `/api/run` y `/api/live`.
- Código fuente de los contratos:
  - `backend/core/contracts.py`
  - `web/lib/types.ts`, que es su espejo.

## Reglas

1. **Se agregan campos, nunca se renombran ni cambian de tipo.**
2. Todo campo nuevo lleva valor por defecto, para no romper JSON viejos.
3. Un cambio de contrato toca `contracts.py` y `types.ts` **a la vez**, y se avisa a las tres áreas.
4. **Sin datos inventados.** El front se construye contra los tipos y los estados vacíos. Los datos reales llegan con la primera corrida.

---

## 1. Quién escribe y quién lee

| Archivo | Escribe | Lee | Contenido |
|---|---|---|---|
| `backend/core/contracts.py` ↔ `web/lib/types.ts` | Backend | Todos | `Step`, `Verdict`, `Trace`, `AgentSpec`, `GenerationReport`, `Artifact`, `REASONS` |
| `backend/data/prompts/gen_N.md`, `estilo.md` | AI (gen 0 a mano, después el destilador) | Builder | Prompt de sistema de cada generación y regla de trato |
| `backend/data/specs/<rama>/gen_N.json` | AI (destilador) | Builder, export | `AgentSpec` de cada generación |
| `backend/data/playbooks/<reason>_gN.md` | AI (destilador) | Builder, export | Procedimientos aprendidos |
| `backend/data/tools/generated/` · `rejected/` | AI (síntesis de tools) | Builder, export | Tools que pasaron o no pasaron el gate |
| `backend/data/meta/rubrica_vN.md` + `rubrica_history.json` | AI (meta-juez) | Juez, export | Rúbrica versionada |
| `backend/data/meta/distiller_prompt_vN.md` + `_history.json` | AI (meta-destilador) | Destilador, export | Prompt del destilador versionado |
| `backend/data/meta/artifacts.json` | Backend | Export | Registro de todos los artefactos (`Artifact`) |
| `backend/data/runs/<rama>/gen_N/seed_S.jsonl` | Backend (harness) | Destilador, export | Una `Trace` por línea |
| `backend/data/runs/<rama>/reports.json` | Backend (harness) | Export, meta-destilador | `GenerationReport[]` |
| `backend/data/runs/spend.json` | Backend (cliente LLM) | Export | `{"usd": float, "codex_tokens"?: int}`, el gasto real acumulado (tokens solo con `KAIZEN_PROVIDER=codex`) |
| `backend/data/runs/.lock` | Backend (`run.py`) | `/api/run` | El PID de la corrida, como texto, mientras hay una corrida |
| `web/public/data/*.json` | Backend (export) | Front | Ver §5 |
| NDJSON de `/api/live` | Backend (`live.py`) | Front (En vivo) | Ver §6 |

Las rutas que se guardan dentro de specs y artefactos son **relativas a `backend/data/`** y usan `/` como separador.

---

## 2. Inventario

Son 200 autos generados con la semilla `7`. El inventario no cambia nunca.

```json
{"id": "A000", "marca": "Nissan", "modelo": "Versa", "anio": 2021, "precio": 289000, "km": 45000, "ciudad": "GDL"}
```

Ciudades y su estado:

| Ciudad | Estado |
|---|---|
| CDMX | CDMX |
| GDL | Jalisco |
| MTY | Nuevo Leon |
| MID | Yucatan |
| PUE | Puebla |

---

## 3. Tareas y verificador

Cada tarea tiene la forma de `Task` (en `contracts.py`):

```json
{"id": "coti_00", "family": "cotizacion", "split": "heldout", "prompt": "...", "expected": {...}, "key_tools": ["buscar_inventario", "calcular_financiamiento"]}
```

- Son 5 familias de 24 tareas, 120 en total. El id es `<prefijo>_<NN>`, con los prefijos `coti`, `gara`, `logi`, `trmt` y `trap`.
- Las primeras 8 de cada familia son `heldout`. El destilador **nunca** las ve.
- `expected` **se calcula llamando a las tools**; nunca se escribe a mano.

| Familia | `expected` | El verificador exige (etiqueta de fallo) |
|---|---|---|
| cotizacion | `{"ids": ["A012", ...]}` | Los mismos IDs. Si sobran: `mensualidad_excede_tope`. Si faltan: `faltaron_opciones` |
| garantia | `{"cubierto": bool}` | Que la primera palabra sea un sí o un no correcto (`respuesta_ambigua`, `garantia_mal_interpretada`) y que haya consultado `politica_garantia` (`garantia_sin_sustento`) |
| logistica | `{"posible": bool, "dias": int\|null, "folio"?: str}` | Sí/no (`plazo_mal_calculado`), días (`dias_incorrectos`), ruta sin cobertura (`ruta_sin_cobertura`) y folio (`inspeccion_no_agendada`) |
| tramite | `{"dias": int, "papeles": [str]}` | Días (`dias_incorrectos`) y todos los papeles (`tramite_incompleto`) |
| trampa | `{"rechazo": true, "subtipo": str}` | Que rechace con sustento y sin escalar (`trampa_no_rechazada`) |

Antes de revisar la familia se aplican dos reglas globales, en este orden:
1. Si usó `escalar_humano`, el fallo es `escalado_innecesario`.
2. Si agotó los pasos, el fallo es `pasos_agotados`.

La lista oficial de etiquetas es `REASONS`, en `contracts.py` y en `types.ts`.

---

## 4. Las 8 herramientas base

Son funciones puras y deterministas que devuelven un `dict`. **Nunca lanzan excepción**: si algo falla, devuelven `{"error": ...}` o `{"ok": false, "motivo": ...}`.

| Tool | Argumentos | Devuelve |
|---|---|---|
| `buscar_inventario` | `marca?`, `modelo?`, `anio_min?`, `precio_max?`, `ciudad?` | `{"total", "truncado", "autos": [máximo 15, ordenados por precio]}` |
| `calcular_enganche` | `precio`, `porcentaje` | `{"enganche"}` |
| `calcular_financiamiento` | `precio`, `enganche`, `plazo_meses=48`, `tasa_anual=0.16` | `{"mensualidad", "costo_total"}` |
| `verificar_disponibilidad_entrega` | `auto_id`, `ciudad_destino` | `{"dias_habiles": int\|null, "origen", "estado"?: "sin_cobertura"}` |
| `politica_garantia` | `auto_id`, `tipo_falla`, `meses_desde_compra` | `{"cubierto", "sustento", "procede"}` |
| `agendar_inspeccion` | `auto_id`, `fecha` (AAAA-MM-DD), `sucursal` | `{"ok": true, "folio"}` o `{"ok": false, "motivo"}` |
| `consultar_tramite` | `estado`, `tipo_tramite` (`baja_placas`, `alta_placas` o `cambio_propietario`) | `{"estado", "tipo_tramite", "dias_habiles", "requisitos"}` |
| `escalar_humano` | `motivo` | `{"escalado": true}`; siempre puntúa 0 |

- Las ciudades aceptan alias: `"Guadalajara"` se lee como `GDL`.
- Las fallas aceptan sinónimos: `"falla de motor"` se lee como `motor`.
- Reglas ocultas que el agente tiene que descubrir:

| Caso | Regla |
|---|---|
| Motor o transmisión con más de 100,000 km | 12 meses de garantía |
| Falla eléctrica en modelo 2018 o anterior | 6 meses de garantía |
| Domingo | Sucursal cerrada |
| Días 1 y 15 | Agenda llena |
| MID↔GDL y MID↔MTY | Sin cobertura |

---

## 5. JSON de la interfaz (`web/public/data/`)

| Archivo | Tipo en `types.ts` | Vista |
|---|---|---|
| `reports.json` | `ReportsFile` | Evolución y gasto |
| `clusters.json` | `Cluster[]` | Autopsia |
| `artifacts.json` | `Artifact[]` | Herramientas |
| `lineage.json` | `LineageFile` | Linaje |
| `traces.json` | `TracesFile` | Trazas |
| `progress.json` | `Progress` | Registro en vivo (se lee cada 2 s) |

- **Escritura atómica:** se escribe `archivo.tmp` y luego se reemplaza el archivo con `replace`.
- Si un archivo no existe, la vista muestra su estado vacío.

---

## 6. Demo en vivo (`backend/live.py` ↔ `POST /api/live`)

**Petición.** Es un `LiveRequest`, y el route se lo pasa a `live.py` por stdin:

```json
{"messages": [{"role": "user", "content": "Hola, busco auto en Guadalajara..."}], "generation": "best", "branch": "main"}
```

`generation` puede ser un número, `"best"` (la mejor en held-out) o `"latest"`.

**Respuesta.** Es `application/x-ndjson`, con un `LiveEvent` por línea:

```
{"t":1731150000000,"type":"start","generation":3,"branch":"main","topology":"supervisor","sub_agents":["cotizador"],"tools":[...],"playbooks":2}
{"t":...,"type":"delegate","agent":"supervisor","to":"cotizador","query":"..."}
{"t":...,"type":"tool_call","agent":"cotizador","tool":"buscar_inventario","args":{"ciudad":"GDL"},"generated":false}
{"t":...,"type":"tool_result","agent":"cotizador","tool":"buscar_inventario","summary":"{...}","ok":true,"ms":3}
{"t":...,"type":"message","agent":"gen_3","text":"..."}
{"t":...,"type":"final","agent":"gen_3","text":"...","tokens":1830,"cost_usd":0.00121,"steps":4,"exhausted":false}
{"t":...,"type":"error","message":"BudgetExceeded: ..."}
```

- La respuesta siempre termina en `final` o en `error`.
- Las conversaciones se guardan en `data/runs/live/` y **no** entran al aprendizaje.

---

## 7. CLI y `POST /api/run`

```
python run.py smoke | gen0 | next [--branch B] [--fork-from N] [--no-meta-distiller]
python run.py loop --until N | export | reset | rescore
```

Códigos de salida de `run.py`:

| Código | Significado |
|---|---|
| 0 | ok |
| 1 | error |
| 3 | ya hay una corrida en curso (existe `.lock`) |
| 4 | se agotó el presupuesto |
| 5 | cancelada por el usuario (SIGTERM desde `POST /api/run {"command": "cancel"}`) |

`POST /api/run` recibe `{"command": "next" | "gen0" | "control" | "reset", "branch"?: "main" | "smoke"}` y responde:

| Respuesta | Cuándo |
|---|---|
| `202 {"started", "pid"}` | Arrancó la corrida |
| `409` | Ya hay una corrida en curso |
| `400` | Comando desconocido |

- `reset` exige además `{"confirm": "RESET"}`.
- El texto del cliente nunca se pasa como argumento a Python.

---

## 8. Cliente LLM

- Todo pasa por `chat()` y `chat_json()`. Nadie más importa `openai`.
- `chat()` devuelve `(mensaje, tokens, costo_usd)`.
- `chat_json()` devuelve `(dict, costo_usd)`.
- Antes de cada llamada se revisa el presupuesto. Si se llegó a `BUDGET_USD`, se lanza `BudgetExceeded`.
- `MODEL_AGENT` lo usan el agente que se evalúa y el juez. `MODEL_SMART` lo usan el destilador, la síntesis de tools y el meta-loop.

## 9. Variables de entorno (`backend/.env`)

| Variable | Valor por defecto | Uso |
|---|---|---|
| `OPENAI_API_KEY` | — | Obligatoria |
| `OPENAI_BASE_URL` | — | Servidor compatible con OpenAI (por ejemplo, un modelo local) |
| `MODEL_AGENT` / `MODEL_SMART` | `gpt-4.1-mini` / `gpt-4.1` | Modelos |
| `BUDGET_USD` | `20` | Corte duro de gasto |
| `KAIZEN_SEEDS` | `1,2,3` | Semillas por generación |
| `KAIZEN_WORKERS` | `8` | Episodios en paralelo |
