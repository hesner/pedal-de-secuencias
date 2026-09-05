# MAVAVE_ANALYSIS.md — Análisis del controlador M-VAVE (modelo PD41)

**Estado: recomendación completa lista para revisión y aprobación (sección 6) — no implementada todavía.**

---

## 1. Capacidades según el manual (`PD41-Software-Instructions.pdf`)

El dispositivo se configura desde una **app de teléfono del fabricante, por Bluetooth** — no hay ninguna indicación de que esto se pueda hacer desde la Raspberry Pi. Dato importante confirmado por el usuario: **la configuración por Bluetooth funciona simultáneamente mientras el USB sigue conectado a la Raspberry Pi** — no hace falta desconectarlo para reconfigurar en vivo.

Hardware físico real (confirmado con foto, no coincide 1:1 con los diagramas del manual): **4 pedales (A, B, C, D)**. "E" y "F" no son pedales separados — son etiquetas impresas entre A-B y entre C-D, correspondientes a presionar esos dos pedales **simultáneamente**.

12 modos de operación, seleccionables solo desde la app:

| # | Modo | ¿Es MIDI estándar? |
|---|---|---|
| 1 | Program Change A (PC) | Sí |
| 2 | Program Change B (CC) | Sí |
| 3 | Custom Control (CC) | Sí |
| 4 | Advanced Custom Mode 1 (PC/CC/Note/SysEx, 5 sub-modos) | Sí |
| 5 | Advanced Custom Mode 2 (igual que 4 + cambio de grupo E/F, hasta 16 grupos) | Sí |
| 6 | Manufacturer Control | **No usar** — control propietario de otros productos M-VAVE (TANK-G, LOOPER PRO, LOST TEMPO) |
| 7 | Touchscreen (swipe gestures) | **No** — es HID, no MIDI |
| 8 | Video (rewind/play/pause/loop, requiere extensión de Chrome) | **No** — HID |
| 9-10 | Keyboard A/B | **No** — HID teclado |
| 11 | Multimedia keys | **No** — HID |
| 12 | Custom keyboard (combinaciones) | **No** — HID |

**Importante:** en los modos 7-12 el M-VAVE probablemente no se presente ante la Raspberry Pi como dispositivo MIDI en absoluto (se comporta como teclado/mouse USB). Solo los modos 1-5 son viables para este proyecto.

---

## 2. Validación empírica (sección 4.1.1) — manual vs. comportamiento real medido

Metodología: M-VAVE conectado por USB directo a la Raspberry Pi, captura en vivo con `aseqdump -p 20:0` (puerto ALSA `SINCO MIDI 1`), pulsaciones físicas realizadas por el usuario en tiempo real mientras se correlacionaban con el log.

### Modo "Advanced Custom Mode 1" — ⚠️ nota de contexto importante

**Esta configuración específica (notas 36/38/40, D como note-off masivo) es la configuración personalizada preexistente del usuario para otro sistema MIDI ajeno a este proyecto — no es el comportamiento de fábrica/genérico del modo.** No debe interpretarse como validación del manual para "Advanced Custom Mode 1" en general, solo como evidencia de que el modo permite ese tipo de configuración asimétrica. Para validar el manual genuinamente en este modo (por ejemplo, el sub-modo "Long Press") haría falta reconfigurar un footswitch de cero, lo cual pisaría la configuración existente del usuario para su otro sistema — pendiente de decidir si se justifica hacerlo.



| Acción | Manual dice | Realmente medido |
|---|---|---|
| Pulsar A | Envía un código MIDI correspondiente | `Note On, canal 0, nota 36, velocity 127` |
| Pulsar B | ídem | `Note On, canal 0, nota 38, velocity 127` |
| Pulsar C | ídem | `Note On, canal 0, nota 40, velocity 127` |
| Pulsar D | ídem (se esperaría nota propia, ej. 42) | **No manda nota propia — manda `Note Off` de las notas 36, 38 y 40 a la vez** (equivale a "soltar todo") |
| Soltar A/B/C | (no documentado explícitamente para este sub-modo) | **Nunca llega `Note Off`** al soltar — el manual describe este comportamiento como "Single Tap": un solo código por toque, sin evento de liberación |
| E (A+B simultáneo) | Cambia de grupo (según Modo 4 general) | **Sin efecto, ningún mensaje MIDI** — coincide con "Mode 4: Switching Groups: Cannot switch banks using buttons E and F" |
| F (C+D simultáneo) | ídem | **Sin efecto**, igual que E |

**Discrepancia/hallazgo no documentado:** el botón D actuando como "note-off masivo" de A/B/C no aparece descrito en el manual — es una configuración específica que alguien (probablemente de fábrica) le dio a D en este sub-modo, no un comportamiento genérico del modo. Relevante para el diseño de STOP (sección 4.5): un patrón similar podría usarse deliberadamente para una acción "detener todo".

### Modo "Program Change A"

| Acción | Manual dice | Realmente medido |
|---|---|---|
| Pulsar A (grupo 1) | PC 0-127 según grupo | `Program Change, canal 0, programa 0` ✅ coincide |
| Pulsar B (grupo 1) | — | `Program Change, programa 1` ✅ |
| Pulsar C (grupo 1) | — | `Program Change, programa 2` ✅ |
| Pulsar D (grupo 1) | — | `Program Change, programa 3` ✅ |
| E (A+B) — cambiar de grupo | "Use buttons E and F to switch groups" | Confirmado: manda `Control Change, controlador 2, valor N` (N parece ser un contador interno de grupo, offset no confirmado con precisión — no es necesariamente igual al número mostrado en pantalla) |
| Pulsar A en grupo mostrado como "7" | Debería seguir el patrón de grupos | `Program Change, programa 24` — **confirma la fórmula `PC = (grupo_mostrado - 1) × 4 + offset(A=0,B=1,C=2,D=3)`** |
| Pulsar B/C/D en grupo "7" | — | `25, 26, 27` — ✅ confirma la fórmula exactamente |
| Display mostrando el "código PC específico" | El manual dice literalmente: *"Display: The specific PC code will be shown on the display screen"* | **Discrepancia real:** la pantalla muestra **"grupo+letra"** (ej. `7A`, `7b`, `7c`, `7d`), **no el número crudo del PC** (24, 25, 26, 27). El manual describe mal este comportamiento. |

**⚠️ Corrección importante (2026-09-05, sesión de validación en vivo posterior): solo hay 8 grupos reales, no 32.** El cálculo original de capacidad (32 grupos × 4 = 128 combinaciones) asumía que el rango completo de Program Change (0-127) se reparte en 32 grupos de 4. Validado en vivo con hardware real que **el contador de grupo cicla con período 8**, no 32:

| Acción | Resultado medido |
|---|---|
| Desde grupo mostrado "1", presionar E varias veces hasta el límite inferior | Llega a grupo mostrado "8" (no se queda en "1", no sigue bajando) |
| Presionar F desde grupo "8" | Vuelve a grupo "1" — wraparound confirmado |
| Presionar A en grupo "8" (pantalla estable, sin parpadeo) | `Program Change, programa 28` — coincide con la fórmula `(8-1)×4+0=28`, confirmando que "8" es un grupo real y válido |
| Presionar A en grupo "1" tras el wraparound desde "8" | `Program Change, programa 0` — idéntico al "1A" original, confirma que el ciclo vuelve genuinamente al mismo grupo 1 |

Esto coincide con un texto de la propia app (Advanced device control) que se había descartado antes por parecer una traducción ambigua: *"A total of 8 groups of 32 timbre"* — la lectura correcta es **8 grupos, 32 valores de PC en total usados** (8×4=32), no "32 grupos". El rango de PC realmente usado por este modo es **0-31**, nunca 32-127, sin importar cuántas veces se presione E/F.

**Impacto en la capacidad máxima:** con D reservado para STOP en cada grupo (decisión ya aprobada, sección 4.5), la capacidad real es `8 grupos × 3 canciones reales (A,B,C) = 24 canciones máximo`, no 96 como se había calculado antes. Esto es insuficiente para el repertorio real de la banda (~25-30 canciones) — replantea la estrategia, ver discusión de seguimiento en el chat con el usuario.

*Nota de proceso: durante esta prueba se observó un episodio breve de mensajes MIDI erráticos (ráfaga de Control Change en los controladores 2/3, y mensajes de reset de canal 124-127) coincidiendo con una caída de la conexión ALSA entre el M-VAVE y el proceso oyente en la Raspberry Pi — se interpretó inicialmente como un posible estado inválido del firmware, pero tras reconectar limpiamente el comportamiento fue determinístico y reproducible (confirmado dos veces). Se atribuye a un hipo de reconexión USB/MIDI, no a la lógica de grupos del pedal.*

**Conclusión parcial de este modo:** muy predecible, matemáticamente limpio, y el más fácil de mapear en el Mapper sin ambigüedad — buen candidato para las alternativas A/C de la sección 4.2. **Capacidad máxima corregida: 24 canciones (8 grupos × 3), no 96.**

**Hallazgo sobre pulsación larga (relevante para STOP, sección 4.5):** en "Program Change A", **una pulsación larga (2-3s) no manda ningún mensaje MIDI** — solo se reconocen toques cortos. Confirmado dos veces (con y sin buffering de la herramienta de captura descartado como causa), y confirmado que el botón sigue funcionando normal para toques cortos inmediatamente después. Esto implica que **los modos 1/2 (Program Change A/B) no sirven por sí solos para implementar un STOP por pulsación larga** — para eso hace falta usar Advanced Custom Mode 1/2 con un footswitch configurado explícitamente en su sub-modo "Long Press" o "Short Tap-Long Press".

### Modo "Program Change B"

| Acción | Manual dice | Realmente medido |
|---|---|---|
| Pulsar A (grupo 1) | Manda códigos **CC**, de `CC(0,0)` a `CC(127,0)` | `Program Change, canal 0, programa 0` — **idéntico a Program Change A, no es CC** |
| Pulsar B/C/D (grupo 1) | ídem | `Program Change, programa 1, 2, 3` — mismo patrón que Program Change A |

**Discrepancia confirmada y significativa:** contrario a lo que dice el manual, "Program Change B" **no manda códigos CC** — a nivel de mensaje MIDI es indistinguible de "Program Change A" en las pruebas realizadas (grupo 1, pulsación corta). Procedimiento descartado como causa (el usuario confirmó que el cambio de modo en la app se refleja de inmediato en la pantalla física del pedal, sin pasos adicionales de sincronización). No se ha encontrado todavía bajo qué condición este modo produciría un mensaje distinto al de "Program Change A" — pendiente de seguir investigando si se prioriza aclarar esto.

### Modo "Custom Control"

| Acción | Manual dice | Realmente medido |
|---|---|---|
| Pulsar A (1er toque) | Footswitch [A] preasignado a "Bank Select MSB" (CC0) en la captura del manual | `Control Change, canal 0, controlador 0, valor 127` ✅ coincide |
| Pulsar A (2do toque) | "Clicking on the corresponding footswitch will send a toggle code" | `Control Change, controlador 0, valor 0` ✅ **confirma el toggle 127/0 exactamente como describe el manual** |
| Pantalla mientras se mantiene presionado | No documentado | Muestra un guion **"—"** temporal mientras el botón está físicamente presionado, vuelve al valor normal al soltar |

**Conclusión de este modo:** el único de los tres validados hasta ahora donde el comportamiento coincide 100% con el manual, sin discrepancias.

---

## 3. Capacidad real de la pantalla física (2 caracteres, no solo numérica)

Confirmado con fotos del dispositivo físico: la pantalla puede mostrar **letras además de números** (se observó `2d`, `11`, `1A`, `7A`, `7b`, `7c`, `7d`). Es de 2 caracteres. Contradice cualquier suposición de que fuera puramente numérica de 2 dígitos — es alfanumérica (7 u 14 segmentos, no confirmado cuál, pero el repertorio de caracteres incluye al menos dígitos y algunas letras minúsculas/mayúsculas).

---

## 4.5 Análisis de STOP (mecanismo más robusto)

Evidencia empírica recolectada específicamente para esta decisión:

| Mecanismo candidato | Resultado real | Viable para STOP |
|---|---|---|
| Pulsación larga en Program Change A/B | **No manda ningún MIDI** — confirmado dos veces | ❌ No |
| Pulsación larga en Custom Control | Se comporta igual que una corta (un solo toggle) | ❌ No aporta nada distinto |
| Combinación de 2 botones simultáneos (A+B) | **No genera ningún código de combinación** — cada botón manda su propio CC de forma independiente. Se observó además un posible rebote mecánico (doble toggle) en uno de los dos botones durante la prueba | ❌ No hay atajo de hardware; habría que detectarlo por software con ventanas de tiempo — más frágil, y menos "fiable" como pide la sección 4.3 |
| Combinación de 4 botones simultáneos | **Descartado sin probar — no es físicamente realista para un músico en vivo** (confirmado por el usuario: máximo 2 pedales a la vez, uno por pie) | ❌ Descartado por ergonomía, no por MIDI |
| Un footswitch dedicado a un único CC fijo en Custom Control | Comportamiento limpio y 100% predecible (validado arriba) | ✅ **Sí** |
| Sub-modo "Short Tap-Long Press" de Advanced Custom Mode 1 (config. existente del usuario para otro sistema) | Manual: "Sends two different MIDI codes with a short tap and a long press" | ✅ **Confirmado real, en dos botones distintos**: D corto → `Note Off` (36/38/40) / D largo → `Program Change 3`. A corto → `Note On 36` / A largo → `Program Change 0`. Patrón consistente, no es un caso aislado de un solo botón. |

### Recomendación preliminar de STOP (actualizada)

El hallazgo del botón D (short tap vs. long press mandando mensajes distintos) **reabre la pulsación larga como mecanismo viable**, siempre que se use el sub-modo "Short Tap-Long Press" de Advanced Custom Mode (no los modos simples 1/2/3, donde ya confirmamos que la pulsación larga no manda nada). Quedan dos opciones robustas, con un trade-off real dado que solo hay **4 footswitches físicos en total**:

| Opción | Ventaja | Costo |
|---|---|---|
| **(a)** Footswitch dedicado exclusivamente a un CC fijo en Custom Control | Más simple de implementar en el Mapper (una sola condición, sin temporización) | Sacrifica un footswitch completo solo para STOP — quedan 3 para todo lo demás (setlist/track/play/next) |
| **(b)** Un footswitch en modo "Short Tap-Long Press": toque corto = función normal (ej. NEXT), toque largo = STOP | Aprovecha el mismo footswitch para dos funciones — quedan los 4 disponibles para uso normal, STOP "gratis" encima de uno de ellos | Depende de que el Mapper distinga confiablemente corto vs. largo (más lógica que un CC plano, aunque el propio M-VAVE ya hace esa distinción en hardware, no el Mapper) |

Ambas minimizan la dependencia de funciones propietarias (CC y PC/Note son MIDI estándar en los dos casos) y son portables a otro controlador futuro. La decisión entre (a) y (b) depende de cuántos footswitches necesita realmente la estrategia final de navegación (sección 4.2) — **pendiente de esa comparación antes de recomendar una sola opción**, no se decide aquí.

---

## 4.2-4.4 Comparación de alternativas y recomendación

### Restricción física real (no estaba en el manual)

Solo hay **4 footswitches físicos** (A-D). "E" y "F" no son botones aparte — son combinaciones A+B y C+D. Esto acota mucho el espacio de diseño: cualquier alternativa tiene que repartir 4 acciones físicas (más cambio de grupo vía E/F donde esté disponible) entre selección de setlist, selección de track, y STOP.

### Evaluación de las 4 alternativas contra la evidencia real

**Alternativa A — Bank/Group → Setlist; Footswitch → Track:**
Es literalmente lo que el modo "Program Change A" ya hace de fábrica: E/F cambia de grupo (validado: manda `CC controlador 2`, valor de grupo), y A-D dentro de un grupo mandan `Program Change = (grupo-1)×4 + offset`. La pantalla física **muestra directamente "grupo+letra"** (ej. `7A`), dando al músico retroalimentación clara de en qué setlist/track está — esto pesa "Muy alto" en la sección 4.3 y aquí está resuelto por el propio hardware, no hay que construirlo. Con **8 grupos reales** × 4 tracks (3 reales + STOP), cubre 32 valores de PC — ver corrección de capacidad en la sección de validación empírica de este modo; el manual de este PD41 nunca menciona "128 timbres", esa cifra venía de otro modelo M-VAVE.

**Alternativa B — Program Change → selección global:**
Es una versión "sin estructura" de lo mismo: tratar los 128 valores de PC como un espacio plano, sin distinguir setlist de track a nivel conceptual. Funciona igual de bien a nivel MIDI, pero **desaprovecha la retroalimentación de pantalla** (que ya viene naturalmente estructurada como grupo+letra) y le pasa al Mapper la responsabilidad de imponer una jerarquía que el hardware ya da gratis. No se recomienda frente a A.

**Alternativa C — Bank/Group → Setlist; PC/CC → Track:**
Muy similar a A. La única diferencia real sería usar CC en vez de PC para el track — pero **ya confirmamos que "Program Change B" (el modo pensado para CC) en realidad manda Program Change, no CC** (discrepancia real del manual, sección 2 de este documento). Esto le quita fuerza a la premisa de "usar CC para track" como algo distinto de la alternativa A — en la práctica, terminaría siendo lo mismo que A.

**Alternativa D — CC/Note → acciones abstractas (sin bancos):**
Es lo que vimos en modo "Custom Control": cada footswitch es un toggle CC independiente, totalmente flexible, sin concepto de banco. Pero **la pantalla no muestra información útil en este modo** (solo `00` y un guion temporal al presionar) — pierde por completo el criterio "Información visible en la pantalla" (Muy alto). Es la opción más flexible para acciones puntuales (por eso la usamos para pensar STOP), pero no para navegar setlists/tracks en vivo.

### Recomendación final

**Recomendamos la Alternativa A (Bank/Group M-VAVE = Setlist; Footswitch = Track), implementada sobre el modo "Program Change A".** Razones, con respaldo de evidencia real medida (no del manual):

1. **Información en pantalla resuelta por hardware**: el músico ve "grupo+letra" sin que nosotros construyamos nada — cumple el criterio de mayor peso sin esfuerzo de ingeniería.
2. **Predecibilidad matemática total**: `PC = (grupo-1)×4 + offset`, validado con múltiples pulsaciones reales, sin ambigüedad.
3. **100% MIDI estándar** (Program Change), sin depender de las funciones propietarias del fabricante (Modo 6) ni de configuración vía Bluetooth para la operación normal en vivo.
4. **Compatibilidad futura**: cualquier controlador MIDI que pueda mandar Program Change + algún medio de cambiar de "banco" sirve como reemplazo, sin tocar el Core (la equivalencia grupo=setlist vive en el Adapter/Mapper, como exige la sección 3).
5. Limitación real a documentar: 4 tracks por setlist. Si esto resulta insuficiente para las canciones reales de NO FUTURO, es un costo conocido de esta alternativa, no una sorpresa.

**STOP** (ver sección 4.5 arriba): se descarta la variante "Advanced Custom Mode 2 + long press" por tres motivos confirmados:
1. No existe un segundo slot libre de Advanced Custom Mode independiente del ya configurado por el usuario para otro sistema — probarlo implicaría modificar esa configuración existente.
2. Ese modo no ofrece la retroalimentación de pantalla (grupo+letra) que sí da Program Change A.
3. Más importante: **STOP debe estar disponible al instante desde cualquier punto del show**, sin depender de en qué setlist/track esté el músico. Cualquier mecanismo atado a la navegación normal (un footswitch específico dentro del esquema de grupos, o un valor de PC reservado al que haya que "llegar" navegando) viola ese requisito de máxima prioridad de la sección 2.

**Recomendación final de STOP: dedicar un footswitch físico completo, exclusivamente a STOP, fuera del esquema de navegación de setlist/track.** Costo aceptado: quedan 3 footswitches para tracks en vez de 4 (**8 grupos reales × 3 tracks = 24 combinaciones** — ver corrección de capacidad más arriba; el cálculo original de "96 en vez de 128" asumía 32 grupos, corregido a 8 grupos tras validación en vivo) — es el precio de que STOP sea verdaderamente inmediato e independiente del estado de navegación, que es justo el criterio de mayor peso ("Fiabilidad del STOP permanente: Muy alto") en la sección 4.3. El footswitch STOP dedicado mandaría un código MIDI estándar fijo (ej. una Note On o CC específica en un canal separado), interpretado por el Mapper como la acción abstracta STOP sin importar el grupo/contexto activo — no requiere cambiar de modo en el M-VAVE ni tocar la configuración existente del usuario.

### Principio de diseño explícito para portabilidad futura (compromiso de arquitectura)

Para que esta recomendación cumpla de verdad con "compatibilidad futura con otro controlador" (sección 4.3), el Mapper **debe calcular setlist/track únicamente a partir del valor final de Program Change recibido** (`setlist = PC÷4 + 1`, `track = PC%4`), **sin depender del mensaje `Control Change, controlador 2` que el M-VAVE manda internamente al usar la combinación E/F**. Ese CC es un detalle específico de cómo el M-VAVE señaliza sus propios combos de botones — no debe cruzar al Mapper como una fuente de verdad, solo el Program Change final importa. Así, reemplazar el M-VAVE por otro controlador que también mande Program Change (por el medio que sea: pads directos, menú, otro esquema de bancos) no requiere tocar el Mapper ni el Core — solo el Adapter específico de ese nuevo hardware, y solo si cambia la cantidad de botones por grupo (el "×4" de la fórmula).

**No implementar todavía** — esto es una propuesta para aprobación, según el flujo de la sección 6.

---

## 4. Pendiente de validar (no completado en esta sesión)

- Modo "Program Change B" (CC) — comportamiento exacto de `CC(n,0)`.
- Modo "Custom Control" (Mode 3) — el toggle descrito (`CC(1,1)` / `CC(1,0)` alternado).
- Modo "Advanced Custom Mode 2" — cambio de grupo E/F con hasta 16 grupos.
- Sub-modo "Long Press" / "Short Tap-Long Press" de Advanced Custom Mode 1/2 — **decisión explícita del usuario: se salta por ahora**, para no pisar su configuración existente de Advanced Custom Mode 1 (usada en otro sistema MIDI ajeno a este proyecto). Si se retoma, usar Advanced Custom Mode 2 (libre) en vez de reconfigurar el 1.
- Mecanismo de STOP (sección 4.5) — análisis separado, todavía no iniciado.
- Dirección inversa: si se le puede mandar algo desde la Raspberry Pi al M-VAVE que produzca una reacción visible (SysEx u otro).
- Comparación formal contra la tabla de criterios de la sección 4.3 y recomendación final (sección 4.4) — prematuro hasta completar lo anterior.

---

## 5. Notas de proceso relevantes

- El M-VAVE puede reconfigurarse desde la app de celular por Bluetooth **sin desconectarlo del USB** de la Raspberry Pi — reduce fricción para seguir probando modos.
- Aparece ante Linux como dispositivo MIDI USB estándar, nombre reportado: `SINCO` (chip Jieli Technology según `lsusb`) — no reporta el nombre "M-VAVE" a nivel USB/ALSA.
