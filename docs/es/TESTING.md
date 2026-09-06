# TESTING.md — Registro de pruebas

## Prueba 4.0 — Validación de audio + video simultáneo en la Raspberry Pi real

**Fecha:** 2026-09-04 / 2026-09-05
**Objetivo:** confirmar que la Raspberry Pi 2 puede reproducir un video H.264 con audio embebido (sin desincronizarse, ni al inicio ni con el tiempo) simultáneamente con un MP3 independiente, con la interfaz de audio USB Behringer, el M-VAVE y el USB de biblioteca conectados a la vez (los 3 dispositivos reales del show).

### Entorno confirmado

- **Hardware:** Raspberry Pi 2 Model B **Rev 1.1** (revisión `a01041`, SoC BCM2836 real — `/proc/cpuinfo` reporta "BCM2835" como nombre genérico del árbol de dispositivos, no es el chip real). Esta revisión es ARMv7 puro, sin soporte de 64-bit: la elección de imagen de 32-bit no es solo preferencia, es la única compatible con esta placa exacta.
- **Sistema operativo:** Raspbian GNU/Linux 12 (bookworm), kernel `6.12.93+rpt-rpi-v7`. Confirmado headless real (`systemctl get-default` → `multi-user.target`, sin ningún compositor gráfico corriendo) tras reflashear con la variante Lite correcta — el primer intento había instalado por error la variante con escritorio (`graphical.target` + compositor `labwc`), detectado y corregido antes de esta prueba.
- **Interfaz de audio:** Behringer U-PHORIA UM2 -- confirmado contra la etiqueta física del equipo. Se identifica en el bus USB como un simple Texas Instruments PCM2902 ("Burr-Brown from TI", "USB Audio CODEC" en `lsusb -v`/`aplay -l`), sin ninguna marca Behringer en el descriptor USB -- esto es esperado para este equipo, no una señal de que se detectó la interfaz equivocada; las interfaces más económicas de Behringer son conocidas por dejar sin modificar los strings USB por defecto del fabricante del chip.
- **Controlador MIDI:** detectado como `SINCO` (chip Jieli Technology) vía `amidi -l` — muy probablemente el M-VAVE o un controlador de la misma familia de referencia.
- **USB de biblioteca:** pendrive NTFS de 7.6GB, montado manualmente en modo **solo lectura** para esta prueba (Lite no trae automount de escritorio).

### Pila de reproducción de video — resultado de la investigación pedida en 4.0

- `omxplayer`: **no disponible** en esta imagen (deprecado/retirado).
- `mpv` y `ffmpeg`/`ffplay`/`ffprobe`: **no vienen instalados** en Raspberry Pi OS Lite por defecto; se instalaron sin problema (paquete no destructivo).
- Decisión: **`mpv`**, con:
  - Decodificación por hardware: `--hwdec=v4l2m2m-copy` (usa `/dev/video10`, el decodificador V4L2 M2M de la Pi). El modo "zero-copy" (`--hwdec=auto` con salida `drmprime`) **falla** (`Failed to commit atomic request (-22)`) en esta combinación de driver DRM/mpv 0.35.1 — no usar.
  - Salida de video: `--gpu-context=drm --vo=gpu` (renderizado directo por DRM/KMS, sin necesidad de X11/Wayland).
  - Salida de audio: **por la tarjeta Behringer, no por HDMI** (decisión confirmada: en el diseño final, todo el audio —el embebido del clip y cualquier pista independiente— sale por la interfaz de audio, HDMI es solo para video). Nota: además, la tarjeta `vc4hdmi` de esta pantalla de prueba solo expone formato `IEC958_SUBFRAME_LE` (passthrough digital), no PCM directo — otro motivo por el que HDMI no es viable para audio aquí, aunque sea irrelevante para el diseño final.
  - Para mezclar el audio embebido del video **y** un audio independiente en la misma tarjeta física al mismo tiempo, se necesita un PCM ALSA `plug:dmix`, definido en `~/.asoundrc` (ver más abajo) — un `dmix` crudo por línea de comandos falla si las dos fuentes no comparten exactamente formato/tasa/canales.

### Configuración ALSA usada (`~/.asoundrc` en la Pi, usuario `hesner`)

```
pcm.mixcodec {
    type plug
    slave.pcm "dmix:CARD=CODEC,DEV=0"
}
ctl.mixcodec {
    type hw
    card CODEC
}
```

### Resultados — prueba de 5 minutos, carga simultánea real

Video 1920x1080/30fps H.264+AAC (audio embebido) + MP3 independiente de 300s, reproducidos a la vez, con Behringer + M-VAVE + USB de biblioteca conectados. Métricas muestreadas cada 10s durante toda la prueba.

| Métrica | Resultado |
|---|---|
| Sincronía audio-video (avsync) | Se mantuvo entre 0 y ~140ms durante los 5 minutos, **sin tendencia a crecer**. Cumple el requisito crítico de la sección 2 (no desincronización progresiva). |
| Memoria | Estable: ~293→312 MB usados de 921MB totales, siempre >600MB libres. Sin fugas visibles. |
| CPU | ~25-30% de uso durante la reproducción (70%+ idle). **La CPU no es el cuello de botella.** |
| Cuadros de video perdidos | **~70% de los cuadros** (creciendo de forma sostenida y lineal, ~21 fps perdidos de 30fps objetivo). Confirmado real (no artefacto de generación de material de prueba). |
| Subvoltaje durante la prueba | Ninguno nuevo (bits de `throttled` sin cambios durante los 5 minutos de carga real). |

### Hallazgo pendiente de resolver: pérdida de cuadros de video

Causa identificada: `mpv` reporta `Assuming 60.000000 FPS for display sync` mientras el contenido es de 30fps — hay un desajuste 30-en-60 que el pipeline actual no maneja bien, resultando en descarte masivo de cuadros para mantener la sincronía de audio (que sí se prioriza correctamente).

- **No es un límite de hardware/CPU** — hay CPU de sobra durante la prueba.
- Se probó `--video-sync=display-resample` como posible corrección: **empeoró el resultado** (introdujo hasta 600ms de deriva real de audio-video, además de seguir perdiendo cuadros). Descartado.
- Se investigó forzar un modo DRM nativo de 30Hz como posible corrección de raíz, pero **la pantalla usada en esta prueba (un monitor de PC Dell P2422H) no soporta ningún modo 1080p30 real** — su EDID solo ofrece 50/59.94/60Hz. No se pudo probar el forzado de 30Hz por esta limitación del monitor de prueba, no de la Pi.
- **Importante — probable artefacto del entorno de prueba, no del hardware real del show:** el usuario confirmó que este monitor de PC **no es representativo** de la pantalla que se usará en los shows (que normalmente son televisores). Los televisores, siguiendo CEA-861, casi siempre sí incluyen modos nativos de 24/25/30Hz para contenido de video. Es probable que este problema de pérdida de cuadros **no ocurra con un TV real**, ya que eliminaría el desajuste 30-en-60 de raíz.
- **Pendiente:** repetir esta prueba específica de pérdida de cuadros con un televisor real (o cualquier pantalla que ofrezca un modo 1080p30 nativo) antes de dar por buena o por mala la reproducción de video en producción. No bloqueante para continuar con otras partes del proyecto (como el análisis del M-VAVE) mientras se consigue una pantalla de prueba representativa.

### Hallazgo de alimentación eléctrica (resuelto)

- **Cargador genérico de Chromecast (Google)**, cable estándar: causó un evento de subvoltaje real que **colgó la Raspberry Pi** durante la prueba de carga sostenida (mensaje "Undervoltage detected!" en pantalla, sistema sin responder). Confirmado con `vcgencmd get_throttled` (bits de subvoltaje/throttling históricos) y `dmesg` (el hub USB completo, los 6 puertos, se desconectó y reconectó 4 veces seguidas en los primeros ~95s de arranque).
- **Solución aplicada:** cargador de 5V/2.5A. Con este cambio, en el arranque solo se observó un evento breve y no recurrente (3 de 6 puertos, una sola vez, ~89s), y **no hubo ningún cuelgue** en los 18+ minutos siguientes de uso, incluida una prueba completa de carga sostenida (decodificación 1080p + doble flujo de audio).
- **Recomendación abierta:** si el evento breve residual molesta, probar además un cable USB de alimentación corto y de calibre grueso — no confirmado como necesario, solo como posible mejora adicional.

### Conclusión de la prueba 4.0

El hardware (Raspberry Pi 2 Rev 1.1 + USB Behringer + M-VAVE + USB de biblioteca, con fuente de 5V/2.5A) sostiene la reproducción simultánea de audio+video sin desincronización y sin agotar CPU/RAM — el requisito crítico de la sección 2 (audio y video de un mismo clip nunca desincronizados) queda validado.

**No se puede dar por cerrada del todo la sección 4.0** hasta repetir la verificación de pérdida de cuadros con una pantalla representativa del show (un televisor real, no el monitor de PC usado en esta prueba) — hay evidencia de que el problema encontrado es específico de las limitaciones de refresco de este monitor de prueba (sin modo 1080p30 nativo) y probablemente no se replique con un TV real. Queda como tarea de seguimiento; no bloquea continuar con el análisis del M-VAVE (sección 4.1) mientras se consigue una pantalla de prueba adecuada.
