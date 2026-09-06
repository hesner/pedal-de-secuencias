# MASTER SPECIFICATION — Proyecto "Chocolate Pi"

**Este documento es el contrato de Claude con este proyecto.** Define qué se debe construir, qué decisiones ya están aprobadas y no se deben cuestionar sin evidencia, qué decisiones están pendientes de investigación, cómo debe ser el flujo de trabajo entre nosotros y el agente, y cómo se revisan las decisiones a medida que aparece evidencia real (sección 9).

No implementes nada hasta haber leído este documento completo y confirmado que lo entendiste.

---

## 1. Qué es este proyecto

Un pedal/caja de control en vivo, basado en Raspberry Pi, que:

- Recibe eventos MIDI estándar desde un controlador MIDI USB (cualquiera capaz de enviar Program Change 0-127 en el formato definido en este documento; ver sección 4 sobre el controlador con el que se validó la arquitectura).
- Dispara **audio** (canciones/samples/efectos) y **video** (clips + standby) en tiempo real.
- Se usa en presentaciones en vivo de la banda **NO FUTURO**.
- Debe funcionar como un *appliance* dedicado: sin pantalla ni teclado durante el show, arranque automático al conectar alimentación.

El objetivo final es que sea **open source**, con documentación bilingüe (es/en).

Todo el trabajo de arquitectura, especificación, supervisión e implementación se hace directamente entre el usuario y Claude — no hay ninguna otra herramienta de IA involucrada en el proyecto.

---

## 2. Decisiones ya aprobadas (NO renegociables)

Estas decisiones están cerradas. Claude puede pedir aclaraciones, pero no debe proponer alternativas a menos que descubra un impedimento técnico real y lo justifique explícitamente.

| Área | Decisión |
|---|---|
| Hardware base | Raspberry Pi 2 |
| Sistema operativo | Raspberry Pi OS Legacy Lite (32-bit) |
| Interfaz de audio | Cualquier interfaz de audio USB compatible con la clase estándar (validada empíricamente con una Behringer U-PHORIA UM2 — ver TESTING.md) |
| Controlador MIDI | Cualquier controlador MIDI USB estándar capaz de enviar Program Change 0-127, sin depender de funciones propietarias (arquitectura diseñada y validada empíricamente con un M-VAVE PD41 — ver sección 4, MAVAVE_ANALYSIS.md y TESTING.md) |
| Salida de video | HDMI, exclusivamente para el público (no para monitoreo del músico) |
| Audio | Reproducción de MP3 y WAV. Ambos son formatos de solo audio y se comportan igual: el video de standby sigue en loop en pantalla mientras suena el audio |
| Video | MP4/MOV/MPEG, códec H.264 |
| Sincronización audio-video | Los clips de video llevan su audio embebido en el mismo archivo (no son pistas separadas). Video y audio de un mismo clip **nunca deben desincronizarse**; esto es un requisito crítico, no solo deseable. Los archivos MP3/WAV independientes (fila "Audio") son para elementos de audio-only de la biblioteca, sin relación con la sincronización de clips de video |
| Prioridad audio/video | **El audio siempre tiene prioridad sobre el video.** El audio nunca debe entrecortarse, saltar, ni atrasarse durante una presentación en vivo; el video puede congelarse o perder cuadros en su lugar si alguna vez hay que elegir entre los dos. El audio es el maestro de tiempo: el video se ajusta a él, nunca al revés (`mpv --video-sync=audio`, `src/core/player.py`) |
| Modo de reposo | Video de standby (`standby.mp4`) en loop cuando no hay nada reproduciéndose |
| Transición de video | Debe ser suave (sin cortes bruscos) entre clips y standby |
| STOP | Es una acción global, de máxima prioridad, debe detener todo inmediatamente |
| Almacenamiento | Biblioteca de setlists/secuencias en USB externo. **Este USB NUNCA debe formatearse ni sus archivos borrarse automáticamente** |
| Arquitectura | Modular, por capas (ver sección 3) |
| Protocolo | MIDI estándar — ninguna función propietaria del controlador puede filtrarse al Core |
| Futuro | Debe soportar reemplazar el controlador MIDI actual por otro sin tocar el Core; posible portal web de administración más adelante |
| Licencia/visibilidad | Proyecto open source, licencia MIT -- máximamente permisiva, uso comercial permitido, sin copyleft |
| Documentación | Bilingüe, español e inglés |
| Roles | El usuario define arquitectura/especificación junto con Claude (chat); **Claude Code es el agente de implementación**. No hay otra herramienta de IA en el proyecto |
| Entorno de desarrollo | Claude Code corre **nativo en Windows** (sin WSL2). Todo lo específico de hardware/OS (audio, MIDI, video, systemd) se prueba directamente contra la Raspberry Pi real vía SSH, no en un entorno Linux simulado en el PC |

---

## 3. Arquitectura obligatoria (capas)

El sistema debe estar organizado en capas independientes. El Core **nunca** debe conocer conceptos específicos del controlador MIDI usado (bancos, grupos, pantalla de 2 dígitos, etc.). Solo debe conocer acciones abstractas.

```
CONTROLADOR MIDI (cualquiera compatible)
        │
        ▼
   MIDI ADAPTER          (traduce el hardware específico a eventos MIDI estándar)
        │
        ▼
STANDARD MIDI EVENTS      (Note On/Off, PC, CC, SysEx — formato estándar)
        │
        ▼
   MIDI MAPPER            (traduce eventos MIDI estándar a acciones abstractas)
        │
        ▼
  ABSTRACT ACTIONS        (SELECT_SETLIST, SELECT_TRACK, PLAY, STOP, NEXT, PREVIOUS, ...)
        │
        ▼
       CORE               (lógica de reproducción de audio/video, biblioteca, standby)
```

Regla explícita: **ningún banco/grupo del controlador MIDI debe convertirse literalmente en un concepto del Core.** Aunque la estrategia final termine siendo "Grupo del controlador = Setlist", esa equivalencia debe vivir en el Adapter/Mapper, nunca en el Core.

Esto permite que en el futuro un controlador distinto (otro MIDI, una app móvil, etc.) pueda generar las mismas acciones abstractas sin modificar el Core.

---

## 4. Paso previo obligatorio y decisión pendiente — Estrategia del controlador MIDI

### 4.0 Paso previo — Validar audio + video simultáneo en la Raspberry Pi real

**Antes de iniciar el análisis del M-VAVE (4.1 en adelante), valida esto primero, conectado por SSH a la Raspberry Pi real:**

La Raspberry Pi 2 es hardware limitado (quad-core Cortex-A7, 1GB RAM, USB 2.0 compartido entre todos los puertos). Antes de construir el MIDI Engine y el resto de la arquitectura, hay que confirmar que el hardware puede sostener el caso de uso real:

- Reproducir un video H.264 con audio embebido (sección 2 — audio y video del mismo clip nunca deben desincronizarse) por HDMI, **y** un MP3 independiente si aplica al mismo tiempo, sin cortes, pops de audio, ni deriva de sincronización entre audio y video.
- Hacerlo con la interfaz de audio USB Behringer, el M-VAVE **y el USB de biblioteca** conectados simultáneamente (los 3 dispositivos reales del show), para detectar problemas de ancho de banda/energía en el bus USB compartido. El USB de biblioteca solo debe conectarse para esta medición — no escribir ni modificar nada en él.
- Determinar y documentar qué stack de reproducción de video es viable en Raspberry Pi OS Legacy Lite sin entorno gráfico (por ejemplo, si `omxplayer` sigue disponible en esta imagen específica, o si hace falta usar `mpv` con salida DRM/KMS, `ffplay` u otra alternativa). Esto es parte del resultado esperado de esta prueba, no una decisión previa.
- Medir uso de CPU/RAM durante esa prueba, y verificar específicamente que audio y video permanezcan sincronizados a lo largo del tiempo (no solo al inicio de la reproducción).

Si esta prueba falla o muestra cortes/desincronización, repórtalo antes de continuar — puede cambiar decisiones de arquitectura más arriba (por ejemplo, si el video debe ser opcional o de menor resolución). No se debe avanzar a construir el resto del sistema sin este resultado documentado en `TESTING.md`.

### 4.1–4.5 Decisión pendiente — Estrategia del controlador MIDI (tarea de análisis obligatoria)

**No implementes el MIDI Engine antes de completar esta tarea.**

Se te entregará (por separado, en otro mensaje/archivo) el manual de configuración del M-VAVE y una fotografía de su pantalla (display de 2 dígitos, tipo 7 segmentos).

### 4.1 Qué debes analizar del controlador

- Modos MIDI disponibles.
- Program Change: rango, comportamiento.
- Control Change: rango, comportamiento.
- Note On/Off: uso disponible.
- SysEx: si aplica.
- Bancos/grupos: cuántos hay, cómo se navegan.
- Qué puede mostrar realmente la pantalla de 2 dígitos (números, qué letras/caracteres son representables, qué pasa con valores >9 o >99).
- Comportamiento de pulsación corta, pulsación larga y combinaciones de botones.
- Qué configuración es persistente en el propio controlador vs. qué se puede controlar desde la Raspberry Pi vs. qué solo se configura desde software del fabricante.
- Qué comportamiento es estándar MIDI y cuál es específico/propietario del M-VAVE.

### 4.1.1 Validación empírica con el M-VAVE físico (obligatoria, no opcional)

**El manual es el punto de partida, no la fuente de verdad.** Los manuales de este tipo de controladores suelen estar incompletos o ser imprecisos en los detalles finos. La fuente de verdad es el comportamiento real medido.

Con el M-VAVE conectado por USB directamente a la Raspberry Pi (por SSH, no en un entorno simulado en el PC):

1. Identifica el dispositivo: `amidi -l`.
2. Captura en vivo los mensajes MIDI reales mientras se prueba físicamente cada botón, modo y combinación descrita en el manual: `aseqdump -p <puerto>` (o `amidi -p <puerto> -d` según corresponda).
3. Por cada elemento del manual (cada botón, cada modo, cada combinación, cada banco/grupo), registra en una tabla: *lo que dice el manual* vs. *lo que realmente se recibió* (canal, tipo de mensaje, número, valor).
4. Comprueba también la dirección inversa: si es posible enviarle algo a la Raspberry al M-VAVE (SysEx u otro mensaje) que produzca una reacción visible (por ejemplo, en la pantalla) — no asumas esto del manual, compruébalo empíricamente.
5. Documenta cualquier discrepancia entre el manual y el comportamiento real; esas discrepancias tienen prioridad sobre lo que diga el manual al momento de decidir la estrategia.

Esta tabla de comportamiento real medido debe incluirse en `MAVAVE_ANALYSIS.md`, junto con el análisis de alternativas — no reemplaza el análisis del manual (4.1), lo complementa y, en caso de conflicto, prevalece sobre él.

### 4.2 Alternativas a comparar (mínimo estas, más las que encuentres en el manual)

- **A**: M-VAVE Bank/Group → Setlist; Footswitch → Track.
- **B**: Program Change → selección global.
- **C**: Bank/Group → Setlist; PC/CC → Track.
- **D**: CC/Note → acciones abstractas (sin mapeo directo a bancos).

### 4.3 Criterios de evaluación (usa esta tabla, con este peso relativo)

| Criterio | Peso |
|---|---|
| Facilidad para el músico en vivo | Muy alto |
| Información visible en la pantalla del M-VAVE | Muy alto |
| Cantidad de setlists soportables | Alto |
| Cantidad de secuencias/tracks soportables | Muy alto |
| Facilidad para navegar en vivo | Muy alto |
| Fiabilidad del STOP permanente | Muy alto |
| Compatibilidad con MIDI estándar | Muy alto |
| Compatibilidad futura con otro controlador | Muy alto |
| Dependencia de funciones propietarias del M-VAVE | Alto (cuanto menor, mejor) |
| Complejidad de implementación | Medio |
| Escalabilidad futura | Muy alto |

### 4.4 Entregable esperado

Un archivo `MAVAVE_ANALYSIS.md` con:

1. Capacidades reales encontradas en el manual.
2. **Tabla de validación empírica** (manual vs. comportamiento real medido, sección 4.1.1), con las discrepancias encontradas.
3. Limitaciones (pantalla, memoria, configuración).
4. Comparación de alternativas contra la tabla de criterios.
5. Ventajas/desventajas de cada alternativa.
6. **Una recomendación final justificada** ("Recomendamos la estrategia X porque...") — no elijas la más fácil de programar, elige la más robusta según los criterios y respaldada por el comportamiento real medido, no solo por el manual.

**Importante: no implementes la estrategia todavía.** Preséntala para aprobación (ver sección 6, flujo de trabajo).

### 4.5 STOP — análisis separado y obligatorio

El STOP es una acción global de máxima prioridad. Analiza todos los mecanismos disponibles (pulsación larga, combinaciones, CC, Note, PC, u otros) y determina la implementación más robusta. La decisión debe:

- Minimizar la dependencia de funciones propietarias del controlador.
- Preservar la posibilidad de usar otro controlador MIDI en el futuro.
- Ser justificada como decisión de ingeniería, no asumida de antemano.

### Nota de portabilidad (resultado de esta sección)

La arquitectura y el Mapper resultantes de este análisis (`src/mapper/`) están diseñados para funcionar con **cualquier controlador MIDI capaz de enviar Program Change 0-127 en este mismo formato**, sin cambios de código — ninguna función propietaria de ningún fabricante queda incorporada al Mapper ni al Core (sección 3). El controlador físico usado para diseñar y validar empíricamente esta estrategia, incluida una prueba en vivo con hardware real, fue un **M-VAVE PD41** (ver `MAVAVE_ANALYSIS.md` para el análisis y `TESTING.md` para la validación).

---

**Las secciones 5-9 cambian de registro**: todo lo de arriba es
arquitectura y decisiones de producto. De aquí en adelante, este
documento describe el *proceso de desarrollo* — cómo se construyó
realmente este proyecto a través de un agente de código con IA (Claude
Code) — se mantiene por transparencia, no porque un colaborador o
usuario lo necesite para entender o correr el sistema. Salta a
`TESTING.md` o `LIBRARY.md` si eso es lo que buscas.

## 5. Qué puede hacer Claude autónomamente vs. qué requiere aprobación

### Autónomo (sin pedir permiso)

- Crear archivos.
- Modificar código.
- Ejecutar pruebas.
- Instalar paquetes no destructivos.
- Analizar logs.
- Ejecutar comandos Git (add, commit en ramas de trabajo, diff, log).
- Crear documentación.
- Diagnosticar problemas.
- Proponer soluciones y alternativas.
- Probar distintos enfoques en un entorno de pruebas.

### Requiere aprobación explícita antes de actuar

- Cambiar cualquier decisión ya aprobada en la sección 2.
- Eliminar funcionalidades existentes.
- Cambiar requisitos.
- Formatear el USB de biblioteca.
- Borrar archivos de la biblioteca de setlists/secuencias.
- Borrar discos o modificar particiones.
- Cualquier operación destructiva sobre datos existentes.
- Contratar/activar servicios o consumir créditos de API adicionales.
- Reemplazar hardware.
- Abandonar una decisión arquitectónica ya aprobada (como la de la sección 3).

---

## 6. Flujo de trabajo obligatorio

Para cada requisito o módulo nuevo:

```
1. Definir el requisito (nosotros)
2. Claude analiza
3. Claude propone (sin implementar)
4. Nosotros aprobamos o pedimos ajustes
5. Claude implementa
6. Claude prueba
7. Nosotros validamos
8. git commit
9. Siguiente requisito
```

No se debe saltar del paso 2 al 5. Toda propuesta de arquitectura o de mapeo MIDI debe pasar por aprobación antes de convertirse en código definitivo.

---

## 7. Estructura de repositorio sugerida

```
CHOCOLATEPI/
│
├── PROJECT_REQUIREMENTS.md
├── ARCHITECTURE.md
├── MIDI_SPECIFICATION.md
├── MAVAVE_SPECIFICATION.md
├── MAVAVE_ANALYSIS.md        (generado por Claude, sección 4)
├── LIBRARY_SPECIFICATION.md
├── MEDIA_SPECIFICATION.md
├── HARDWARE_SPECIFICATION.md
├── API_SPECIFICATION.md
├── SECURITY.md
├── TESTING.md
├── ROADMAP.md
│
├── docs/
│   ├── es/
│   └── en/
│
└── src/
```

Estos archivos no necesitan existir todos desde el día uno; se crean a medida que cada área se define.

---

## 8. Primera instrucción a darle a Claude Code

Una vez Claude Code esté instalado y corriendo dentro del repositorio, la primera instrucción (antes de tocar código) debe ser aproximadamente:

> Este repositorio corresponde al proyecto "Chocolate Pi". Lee MASTER_SPECIFICATION.md completo. No implementes nada todavía. Confirma que entendiste las decisiones aprobadas (sección 2), la arquitectura por capas obligatoria (sección 3) y el flujo de trabajo (sección 6). Señala cualquier contradicción, riesgo técnico o ambigüedad que encuentres.

Cuando confirme, se le pide ejecutar primero la prueba de audio+video de la sección 4.0 vía SSH contra la Raspberry Pi real. Solo después de documentar ese resultado se le entrega el manual del M-VAVE y se le pide ejecutar el análisis de la sección 4.1 en adelante.

---

## 9. Revisión continua basada en evidencia

Este proyecto no es de arquitectura fija desde el día uno: se espera que las decisiones se ajusten a medida que aparece evidencia real de comportamiento en hardware (latencia MIDI, estabilidad de audio/video, uso de CPU/RAM, limitaciones reales del M-VAVE descubiertas en la práctica).

Claude debe monitorear activamente el desempeño real de lo que ya está implementado. Si detecta que una decisión aprobada no está funcionando como se esperaba, debe:

1. **Documentar la evidencia concreta** que sustenta el hallazgo (mediciones, logs, comportamiento observado) — nunca una opinión de estilo o preferencia sin datos detrás.
2. **Proponer una alternativa justificada**, incluyendo el costo/impacto de cambiarla en el punto actual del proyecto (qué se reescribe, qué se pierde, qué se gana).
3. **Esperar aprobación explícita** antes de implementar el cambio — el mismo mecanismo de la sección 6, no un atajo.

Esto aplica en **cualquier momento** del proyecto, no solo durante el análisis inicial: tanto si Claude detecta el problema por sí mismo ejecutando pruebas, como si nosotros lo notamos y se lo planteamos a él para que lo evalúe.

Ejemplo de cómo Claude debería plantearlo:

> "La estrategia de Bank/Group → Setlist funciona, pero en pruebas reales el cambio de grupo en el M-VAVE tarda ~400ms en reflejarse en pantalla, lo que puede confundir al músico en vivo. Evidencia: [logs/mediciones]. Propongo cambiar a la alternativa C (PC/CC → Track) porque elimina ese retraso. Costo del cambio: hay que reescribir el Mapper, no el Adapter ni el Core. ¿Apruebas este cambio?"

No se trata de rediseñar todo constantemente, sino de que ninguna decisión quede "congelada" solo porque ya se aprobó una vez — se ajusta cuando hay evidencia real que lo justifique, y siempre con nuestra aprobación antes de tocar código.
