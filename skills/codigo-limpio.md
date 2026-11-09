---
name: codigo-limpio
description: Buenas prácticas de KAIZEN para escribir código simple, limpio y fácil de entender, prefiriendo la claridad sobre la eficiencia. Úsala siempre que escribas, modifiques o revises código en backend/ (Python) o web/ (TypeScript/React), antes de dar el cambio por terminado.
---

# Código limpio en KAIZEN

En este equipo, el código lo lee mucha gente con prisa: compañeros en un hackathon, jueces y agentes de código. **El objetivo es que cualquiera entienda un archivo en una sola lectura.**

## Principio rector: entender antes que optimizar

Cuando tengas que elegir entre código claro y código eficiente, **elige el claro**. Solo optimiza cuando:

1. hay un problema de rendimiento **medido** (no supuesto), y
2. la versión clara no lo resuelve.

Si optimizas, deja un comentario que diga qué se midió y por qué la versión simple no bastaba.

```python
# ✅ Claro: se lee de arriba abajo
aprobadas = []
for traza in trazas:
    if traza.verdict.passed:
        aprobadas.append(traza)

# ✅ También claro (comprensión corta y obvia)
aprobadas = [t for t in trazas if t.verdict.passed]

# ❌ Ingenioso, pero obliga a detenerse a descifrarlo
aprobadas = list(filter(lambda t: t.verdict.passed and not t.exhausted or False, trazas))
```

## Reglas

### Simplicidad
- **Haz lo que se pidió y nada más.** No agregues opciones, parámetros ni capas "por si acaso".
- **No abstraigas antes de tiempo.** Duplicar algo dos veces está bien; a la tercera, extrae una función.
- Prefiere funciones y datos simples (dicts, dataclasses) antes que clases con herencia.
- Usa early return en lugar de anidar `if` dentro de `if`. Un máximo de 2 o 3 niveles de indentación.
- Si una función no cabe en la pantalla (unas 40 líneas), probablemente hace demasiado. Divídela por pasos con nombre.
- Evita la magia: metaprogramación, decoradores propios o `getattr` dinámico, salvo que no haya otra forma.

### Nombres
- Usa nombres que digan **qué es**, no cómo se calcula: `mensualidad_maxima` en vez de `m2` o `tmp`.
- Las funciones son verbos (`calcular_enganche`, `cargarTrazas`). Los booleanos son preguntas (`es_heldout`, `hasData`).
- **Escribe en español**, como el resto del proyecto. Excepción: los campos de los contratos (`task_id`, `heldout_success`), que se respetan tal cual.
- No uses abreviaturas salvo las del dominio (`id`, `usd`, `gen`).

### Estructura
- Usa una sola fuente de verdad para cada cosa: los contratos en `contracts.py`/`types.ts`, las rutas en `core/paths.py` y los colores en `globals.css`.
- Separa la lógica pura (cálculos, transformaciones) de los efectos (leer archivos, llamar al LLM, red). La lógica pura se prueba fácil.
- Importa explícitamente. No uses `from x import *`.
- No dejes código muerto, `print` de depuración, `console.log` ni código comentado. Git ya guarda el historial.

### Errores
- **No silencies errores.** Nada de `except: pass` ni `catch {}` vacío. Si un error se tolera, comenta por qué.
- Captura excepciones concretas (`json.JSONDecodeError`), no `Exception`, salvo en la frontera (por ejemplo, `live.py` emitiendo un evento `error`).
- Los mensajes de error dicen qué falló y cómo arreglarlo: `"Falta OPENAI_API_KEY en backend/.env"`.
- Nunca inventes datos para tapar un fallo. Si falta un valor, queda `None` o `null` y la interfaz muestra "—".

### Tipos
- Python: type hints en las firmas públicas, `from __future__ import annotations` y dataclasses para estructuras.
- TypeScript: `strict`, sin `any`. Tipa contra `lib/types.ts`. Si algo puede faltar, márcalo con `?` o `| null` y manéjalo.

### Cambios pequeños
- Haz un cambio por commit, con un mensaje que explique el *porqué*.
- No reformatees ni renombres código ajeno en el mismo cambio en que arreglas otra cosa.
- Sigue el estilo del archivo que estás tocando, aunque prefieras otro.

## Checklist antes de terminar

- [ ] ¿Un compañero lo entiende sin que se lo expliques?
- [ ] ¿Hay algo que se pueda borrar sin perder funcionalidad? Bórralo.
- [ ] ¿Quedaron números o textos sueltos que deberían ser constantes o configuración? (ver `skills/sin-hardcode.md`)
- [ ] ¿Los comentarios explican el porqué y son objetivos? (ver `skills/comentarios-objetivos.md`)
- [ ] ¿Pasan las verificaciones? Backend: `.venv/Scripts/python -m pytest`. Web: `npm run lint` y `npm run build`.
