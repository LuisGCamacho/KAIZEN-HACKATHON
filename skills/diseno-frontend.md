---
name: diseno-frontend
description: Guía de diseño de interfaz para la web de KAIZEN (Next.js + Tailwind 4) que cubre jerarquía visual, espaciado, tipografía, color con tokens, estados (cargando, vacío, error), visualización de datos, accesibilidad, responsive y textos. Úsala siempre que crees o modifiques una vista, un componente o una gráfica en web/, o cuando revises cómo se ve algo.
---

# Diseño frontend en KAIZEN

KAIZEN es un **instrumento de evidencia**: muestra que un agente se mejora solo y lo demuestra con números reales. El diseño tiene que transmitir **rigor, claridad y confianza**, no espectáculo. Piensa en un buen panel científico o en una terminal editorial: monocromático y preciso, con un solo acento.

## Proceso (antes de escribir JSX)

1. **¿Qué pregunta responde esta vista?** Escríbela en una frase. Ejemplo para Autopsia: "¿qué fallos tuvo el agente y cuáles se cerraron?". Todo lo que no ayuda a responderla sobra.
2. **¿Cuál es el dato más importante?** Ese va primero, más grande y con más contraste. Solo puede haber **un** protagonista por pantalla.
3. **¿Qué ve el usuario sin datos, cargando y con error?** Diseña esos tres estados antes que el estado lleno.
4. **Reutiliza.** Revisa `components/ui/` (`Card`, `StatCard`, `Badge`, `Chip`, `Tabs`, `Collapsible`, `CodeBlock`, `DataGate`, `EmptyState`, `Skeleton`) antes de crear algo nuevo.

## 1. Jerarquía visual

- Crea jerarquía con **tamaño, peso y contraste**, no con colores ni cajas de más.
- Hay tres niveles de texto: el principal (`text-ink`), el secundario (`text-ink-2`) y el terciario o metadato (`text-ink-3`/`text-ink-4`). Si todo es `text-ink`, nada destaca.
- Las cifras importantes van con `text-figure` en `font-mono`. Las etiquetas encima de las cifras, con `text-label`, en mayúsculas pequeñas y tracking amplio.
- Cada vista empieza con `PageHeader`: un título (`text-view`) y un subtítulo que explica **qué se mide y de dónde sale**.

## 2. Espaciado y layout

- Usa la escala de Tailwind de forma consistente: `gap-1`/`gap-2` dentro de un componente, `gap-3`/`gap-5` entre tarjetas y `space-y-5` entre secciones. No inventes valores arbitrarios (`mt-[13px]`).
- Agrupa por proximidad: lo relacionado va junto y lo distinto, separado. El espacio en blanco es la herramienta principal para agrupar, antes que los bordes.
- Usa grids que se adapten solos: `grid-cols-[repeat(auto-fit,minmax(320px,1fr))]`. Evita breakpoints fijos cuando un grid fluido basta.
- Alinea todo a una misma rejilla. Los bordes izquierdos de títulos, tarjetas y tablas deben coincidir.
- Limita la longitud de línea del texto corrido a `max-w-prose` o `max-w-md` para que sea legible.

## 3. Tipografía

- Hay solo dos familias: **Inter** (`font-ui`) para la interfaz y **JetBrains Mono** (`font-mono`) para IDs (`A012`, `coti_03`), números, código, rutas y JSON.
- Usa solo dos o tres pesos: 400 para el cuerpo, 500 para énfasis y 600 para títulos. No uses negritas por todas partes.
- Los números en columnas o que cambian en vivo usan `tabular-nums`, para que no "bailen".
- La escala está definida por los tokens: `text-view`, `text-figure`, `text-base`, `text-sm`, `text-id`, `text-code`, `text-label`. No uses otras.

## 4. Color

- **Solo tokens de `globals.css`.** Prohibido usar colores literales (`#fff`, `text-[#333]`, `style={{color}}`).
- La paleta es monocromática: `ink`, `ink-2`, `ink-3`, `ink-4`, `bg`, `panel`, `soft`, `chip`, `line`, `line-strong`, `grid`, `diff-add` y `diff-del`.
- **`seal` (rojo) es el único acento y significa una sola cosa: "esto lo escribió la máquina"** (tools generadas, playbooks, prompts destilados, eventos `generated: true`). Nunca lo uses para errores, botones, alertas ni decoración; si aparece en todos lados, pierde su significado.
- Los estados (ok/fallo, aceptada/rechazada) se distinguen con **forma, texto o icono además del tono**: un ✓ o ✗, la palabra "rechazada" o un borde punteado. Nunca solo con color (accesibilidad y daltonismo).

## 5. Estados (obligatorios en cada vista)

| Estado | Cómo se ve | Componente |
|---|---|---|
| Cargando | Esqueleto con la forma del contenido final; nunca una pantalla en blanco | `Skeleton` vía `DataGate` |
| Vacío | Título que dice qué falta, explicación breve y **el comando que lo resuelve** | `EmptyState` (`command="python run.py gen0"`) |
| Error | Qué falló, en lenguaje humano, y qué hacer | Texto `text-ink-2` + acción |
| Parcial | Datos que se están llenando (corrida en curso), con un indicador de progreso | `progress.json` |
| Lleno | El diseño principal | — |

- **Nunca uses datos inventados** para que una vista "se vea bien". Si no hay datos, se ve el estado vacío.
- Los valores ausentes se muestran como "—" (usa los formateadores de `lib/format.ts`), nunca como `0`, `NaN` o `undefined`.

## 6. Visualización de datos

- Cada gráfica responde una pregunta. Su título es esa pregunta o su respuesta ("Éxito por generación").
- **Muestra la incertidumbre:** cuando hay varias semillas, dibuja media y desviación (barras de error). Ocultarla haría pasar por más sólido de lo que es.
- Etiqueta directamente sobre la gráfica cuando se pueda, en lugar de usar una leyenda lejana. Si hay leyenda, que esté pegada a la gráfica.
- Los ejes empiezan en 0 para porcentajes y los ejes de éxito van de 0 a 100 %. Usa pocas líneas de rejilla, en `grid`.
- Diferencia las series con tono de tinta y tipo de trazo (sólido o punteado). `control` es una comparación y debe verse secundaria.
- Las gráficas son SVG a mano (`components/charts/`, `lib/chart.ts`), con `fill-ink-*` y `stroke-*` desde tokens, y un `<title>` o `aria-label` que las describa.
- Para KPIs usa `StatCard`: etiqueta, cifra grande y un detalle con contexto (por ejemplo, "gen 0: 0.42").

## 7. Interacción y movimiento

- Todo lo clicable tiene `hover`, `focus-visible` (ya definido de forma global) y un estado `disabled` claro.
- Las acciones que gastan dinero o borran algo (generar, reset) piden confirmación y muestran que están en curso. Desactívalas mientras corren (`progress.corriendo`).
- Animaciones mínimas, de 150 a 200 ms, solo para indicar un cambio de estado (aparece un paso en la línea de tiempo, se expande un `Collapsible`). Respeta `prefers-reduced-motion`. Nada de rebotes ni parallax.
- Las listas en streaming (demo en vivo) se pegan al final mientras el usuario no haga scroll hacia arriba (`use-stick-to-bottom`).

## 8. Accesibilidad

- HTML semántico: `<main>`, `<nav aria-label>`, `<button>` para acciones y `<a>`/`Link` para navegar. Nunca un `div` con `onClick`.
- Contraste mínimo de 4.5:1 en texto normal. `ink-4` solo para texto decorativo o deshabilitado.
- Todo es operable con teclado y el orden de tabulación sigue el visual.
- Las imágenes o gráficas informativas llevan `aria-label` o `<title>`; los iconos decorativos, `aria-hidden`.
- Las regiones que cambian solas (registro en vivo, progreso) usan `aria-live="polite"`.

## 9. Responsive

- El layout ya se apila: el sidebar y el `main` usan `flex-wrap`. Revisa cada vista a unos **375 px** de ancho, sin scroll horizontal de la página.
- Las tablas anchas van dentro de un contenedor con `overflow-x-auto`; la página nunca se desborda.
- Los objetivos táctiles miden al menos 36–40 px de alto.

## 10. Textos (microcopy)

- **Todo en español de México**, con tono directo, preciso y sin hype. Los números se formatean con `es-MX`.
- Di de dónde sale cada número: "Éxito en 40 tareas que el destilador nunca vio" es mejor que "Precisión".
- Aclara siempre que el juez y el trato **no cuentan en la métrica oficial**.
- Los botones dicen qué hacen: "Generar siguiente", no "Continuar" ni "OK".
- Nada de signos de exclamación, emojis ni "¡Ups!".

## Antipatrones (rechazar en revisión)

- Degradados, glassmorphism, sombras grandes, neón o fondos con ruido. La estética es plana con bordes `line`.
- Más de un acento de color, o `seal` usado para algo que no sea autoría de la máquina.
- Tarjetas dentro de tarjetas dentro de tarjetas. Usa un nivel de `Card` y separa el contenido interno con espacio.
- Iconos sin significado o decorativos por todos lados.
- Spinners a pantalla completa en lugar de esqueletos.
- Datos de ejemplo, lorem ipsum o números "de relleno".
- Tamaños, colores o márgenes arbitrarios (`text-[17px]`, `mt-[7px]`).

## Checklist antes de entregar

- [ ] La vista responde una pregunta clara y el dato principal destaca.
- [ ] Estados cargando, vacío y error diseñados y probados (sin `public/data/`).
- [ ] Solo tokens de color, tipografía y radios; `seal` solo para autoría de la máquina.
- [ ] Ningún estado se comunica solo con color.
- [ ] Funciona con teclado, tiene `focus-visible` y etiquetas ARIA donde hacen falta.
- [ ] Se ve bien a 375 px y en escritorio ancho.
- [ ] Textos en español, precisos y con la fuente de cada número.
- [ ] `npm run lint` y `npm run build` pasan.
