---
name: sin-hardcode
description: Cómo evitar valores hardcodeados en KAIZEN (secretos, rutas, URLs, modelos, números mágicos, colores, textos repetidos) y dónde debe vivir cada tipo de valor. Úsala al escribir o revisar código que contenga números, cadenas, rutas, claves, URLs o colores literales.
---

# Sin hardcode

**Hardcodear** es escribir directo en el código un valor que debería tener nombre, configurarse o venir de una sola fuente. El problema no es el literal en sí: es que nadie sabe qué significa, se repite en varios lugares o cambia según el entorno.

## Dónde vive cada cosa

| Tipo de valor | Dónde va | Ejemplo en KAIZEN |
|---|---|---|
| Secretos (API keys, tokens) | `backend/.env` (nunca en git) y `.env.example` con un valor falso | `OPENAI_API_KEY` |
| Cambia por entorno o máquina | Variable de entorno con un default razonable | `MODEL_AGENT`, `BUDGET_USD`, `KAIZEN_WORKERS`, `KAIZEN_PYTHON` |
| Rutas de archivos | `backend/core/paths.py` | `RUNS`, `SPECS`, `WEB_DATA`, `rel()` |
| Regla o parámetro del algoritmo | Constante en MAYÚSCULAS al inicio del módulo, con un comentario | `TOP_CLUSTERS = 3`, `MAX_LINEAS = 200` |
| Vocabulario compartido entre back y web | Contratos: `core/contracts.py` ↔ `web/lib/types.ts` | `REASONS`, `Topology` |
| Datos del dominio (tablas) | Diccionarios con nombre en `env/` | `DIAS_RUTA`, `MESES_GARANTIA` |
| Colores, radios, tamaños de texto | Tokens en `web/app/globals.css` | `text-ink-2`, `rounded-card`, `bg-seal` |
| Allowlists de seguridad | Constante con nombre junto a donde se usa | `COMMANDS` y `BRANCHES` en `/api/run` |

## Reglas

1. **Nunca pongas secretos en el código**, ni siquiera de prueba. Si aparece uno en un diff, es un bloqueo. Si llegó a subirse, hay que rotarlo (sacarlo de git no basta).
2. **No dejes números mágicos.** Si un número no es obvio (`0`, `1`, `100` como porcentaje), dale nombre:
   ```python
   # ❌
   if multi / len(fallos) > 0.4:
   # ✅
   UMBRAL_MULTI_PASO = 0.4  # más del 40 % de fallos multi-paso justifica un supervisor
   if multi / len(fallos) > UMBRAL_MULTI_PASO:
   ```
3. **No construyas rutas a mano** (`"data/runs/" + rama`). Usa `paths.RUNS / rama`. En specs y artefactos, guarda rutas relativas con `rel()`.
4. **No copies listas del contrato.** Importa `REASONS`, `FAMILIES` o los tipos de `types.ts`; no los reescribas en otro archivo.
5. **No escribas colores literales en la web** (`#c8322d`, `text-[#5a5a5a]`, `style={{color: ...}}`). Si falta un token, agrégalo a `globals.css`.
6. **No dupliques URLs ni endpoints.** Define `/api/live` y `/api/run` una sola vez (en `lib/live.ts` y en el helper correspondiente) y reutilízalos.
7. **Toda variable de entorno nueva** se documenta en `.env.example` y en la tabla de variables de `backend/AGENTS.md`, con su default.
8. **Los textos de la interfaz que se repiten** (mensajes de estado vacío, etiquetas de familias) van en una constante o un mapa, no copiados en cada componente.

## Lo que NO es hardcode (no lo abstraigas)

Llevar esta regla al extremo también ensucia el código. No lo hagas con:
- **Valores obvios y locales:** `range(3)` en un test, `padding` de un componente con clases de Tailwind, `[:300]` comentado como "recorte para el resumen".
- **Datos del entorno de evaluación** que *deben* estar fijos para que la métrica sea reproducible: la semilla `7`, los 200 autos y las 120 tareas. Ya viven con nombre en `env/` y `contracts.py`.
- **Valores de prueba en tests:** un test puede tener sus datos literales; así se lee qué prueba.

Regla práctica: **si cambiar el valor obliga a buscarlo en más de un lugar, o si alguien preguntaría "¿por qué este número?", necesita un nombre.**

## Checklist

- [ ] ¿Hay claves, tokens o contraseñas en el diff? → `.env`
- [ ] ¿Algún número sin nombre cuyo significado no sea obvio? → constante con comentario
- [ ] ¿Rutas armadas con strings? → `core/paths.py`
- [ ] ¿Listas o tipos copiados del contrato? → importarlos
- [ ] ¿Colores o medidas literales en la web? → tokens de `globals.css`
- [ ] ¿Variable de entorno nueva sin documentar? → `.env.example` + `AGENTS.md`
