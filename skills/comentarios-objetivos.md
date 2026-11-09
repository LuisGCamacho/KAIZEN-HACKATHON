---
name: comentarios-objetivos
description: Cómo escribir comentarios y docstrings objetivos en KAIZEN, que expliquen el porqué y las restricciones sin adornos ni opiniones. Úsala al agregar o revisar comentarios, docstrings o encabezados de archivo en Python o TypeScript.
---

# Comentarios objetivos

Un buen comentario le da al lector información que **el código no puede expresar por sí solo**: la razón de una decisión, una restricción externa, una regla del negocio o un riesgo. Debe ser **verificable, breve y neutral**.

## Qué comentar

1. **El porqué**, no el qué:
   ```python
   # ❌ Recorre las trazas y filtra las de train
   # ✅ El destilador solo ve train: si viera held-out, la métrica dejaría de ser honesta
   fallos = [t for t in trazas if t.split == "train" and not t.verdict.passed]
   ```
2. **Restricciones e invariantes:** lo que no se debe romper.
   `# Escritura atómica: la interfaz hace polling y no debe leer un JSON a medias`
3. **Reglas del dominio o valores con origen:**
   `UMBRAL_MULTI_PASO = 0.4  # más del 40 % de fallos de logística/trámite justifica un supervisor`
4. **Decisiones no obvias o contraintuitivas**, con la alternativa que se descartó:
   `# Un solo intento: si el modelo se atora, se pierde la tool, no la generación entera`
5. **Seguridad:** por qué existe una validación.
   `// El texto del cliente nunca se pasa como argumento a Python`
6. **Encabezado de archivo:** una o dos líneas con qué hace el módulo y su papel en KAIZEN.
   `"""Verificador programático: la métrica oficial. Binario y sin LLM."""`

## Qué NO comentar

- **Lo que el código ya dice:** `i += 1  # suma uno`. Si un comentario solo repite el código, bórralo o mejora los nombres.
- **Opiniones o adjetivos:** "solución elegante", "hack feo", "esto es genial", "obviamente". El comentario informa, no juzga.
- **Historial:** "antes usábamos X", "lo cambió Ana". Eso va en el mensaje del commit.
- **Código comentado.** Bórralo; git lo conserva.
- **Promesas vagas:** `# TODO: mejorar`. Si dejas un TODO, di qué falta y por qué no se hizo ahora: `# TODO: soportar la rama control con un fork distinto de 2 (hoy está fijo en export.py)`.

## Estilo

- **En español**, como el resto del código. Frases cortas y en presente.
- Una línea siempre que se pueda. Si necesitas un párrafo, probablemente la función necesita dividirse o un nombre mejor.
- Usa datos concretos en lugar de palabras vagas: "máximo 15 autos, ordenados por precio" en vez de "algunos autos".
- **Mantenlos verdaderos.** Si cambias el código, actualiza su comentario en el mismo cambio. Un comentario falso es peor que ninguno.
- Docstrings (Python) y JSDoc `/** */` (TS) en funciones públicas o no triviales. Di qué devuelven y qué pasa en el caso borde:
  ```python
  def juzgar(...) -> tuple[float | None, float | None, float]:
      """Devuelve (p_pasa, explicacion, usd). Si el juez falla, la nota queda en None (no se inventa)."""
  ```
  ```ts
  /** Mayor held-out y, en empate, la más nueva. Misma regla que backend/evaluation/history.py. */
  export function bestOf(gens: Generation[]): number | null {
  ```

## Prueba rápida

Antes de dejar un comentario, pregúntate:
1. ¿Le dice al lector algo que **no** puede ver en el código? Si no, bórralo.
2. ¿Es un hecho comprobable o una opinión? Si es una opinión, reescríbelo como un hecho.
3. ¿Seguirá siendo cierto si alguien cambia una línea cercana? Si no, acércalo al código que describe o hazlo más específico.
