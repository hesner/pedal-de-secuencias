# USB de biblioteca — nombres de carpetas y archivos

*[Read in English](../../LIBRARY.md)*

Cómo organizar el USB de biblioteca para que `Library.resolve()`
(`src/core/library.py`) realmente encuentre lo que le pongas. Esto no lo
valida ninguna herramienta — si te equivocas en un nombre, la pista se
trata en silencio como un espacio vacío (sin error, no pasa nada al
presionar el pedal). Lee esto antes de editar la biblioteca, no después
de que un show salga mal.

## Estructura

```
<raíz del USB>/
├── active_show.txt          -- texto plano, una línea: el nombre de la carpeta del show activo
├── standby.mp4               -- en loop cuando no hay nada reproduciéndose
└── <Nombre del Show>/         -- ej. "Live", una carpeta por show/colección de setlists
    ├── Set 1/
    │   ├── A - nombre de canción.mp3
    │   ├── B - otra canción.mp4
    │   └── C - una tercera.wav
    ├── Set 2/
    │   └── ...
    └── Set N/
```

- **`active_show.txt`**: su contenido (sin espacios extra) debe coincidir
  exactamente con el nombre de una carpeta directamente bajo la raíz del
  USB. Si apunta a una carpeta que no existe, o está vacío/no se puede
  leer, se reproduce el standby de respaldo en vez de cualquier contenido
  real.
- **`Set N/`**: `N` es el número de setlist, coincide con el grupo del
  controlador (ver `MAVAVE_ANALYSIS.md` para cómo un número de grupo se
  mapea a `N` específicamente para el M-VAVE PD41). Los nombres de
  carpeta se comparan exactamente como `Set ` seguido de dígitos —
  `Set 1`, `Set 12`, no `set 1`, `Set1`, ni `Set 01`.
- **Archivos de pista**: exactamente un archivo por letra, `A`/`B`/`C`
  (el footswitch `D` siempre es STOP — nunca necesita archivo). Un
  espacio vacío (sin archivo para una letra) es normal y esperado, no un
  error.

## La única regla que realmente importa: el patrón del nombre de archivo

```
<Letra> - <lo que sea>.<extensión>
```

**Exactamente un espacio antes del guion, uno después.** La letra debe
ir seguida inmediatamente por ` - ` (espacio, guion, espacio), luego
cualquier nombre, luego una extensión soportada:

- Solo audio (el standby sigue en loop debajo, el audio suena encima):
  `.mp3`, `.wav`
- Video con audio embebido: `.mp4`, `.mov`, `.mpeg`, `.mpg`

Mayúsculas/minúsculas no importan ni en la letra ni en la extensión
(`a - x.MOV` calza perfecto). Lo único que tiene que ser exacto es ese
único espacio a cada lado del guion.

**Este es el error más fácil de cometer**, y falla completamente en
silencio — ningún error en ningún lado, el footswitch simplemente no
hace nada, porque un nombre de archivo que no calza se ve idéntico a un
espacio vacío intencional. Ya pasó una vez durante las pruebas de este
mismo proyecto: un archivo llamado `A  - IMG_0896.MOV` (dos espacios
antes del guion, fácil de teclear por accidente) no se reprodujo, sin
nada en el log que explicara por qué más allá de "no hay archivo para la
pista A (espacio vacío)".

```
A - mi canción.mp3        <- correcto
A  - mi canción.mp3       <- MAL (dos espacios antes del guion) -- ignorado en silencio
A- mi canción.mp3         <- MAL (sin espacio antes del guion) -- ignorado en silencio
A -mi canción.mp3         <- MAL (sin espacio después del guion) -- ignorado en silencio
```

**La forma más segura de evitarlo**: no escribas un nombre de archivo
nuevo desde cero. Duplica un archivo de pista que ya funcione (en el
mismo `Set` o en otro) y renombra solo la parte después de ` - `, así el
` - ` en sí nunca se vuelve a teclear.

Si una pista no suena y todo lo demás se ve bien (el archivo sí está
ahí, en el `Set` correcto, con el show correcto activo), renombra el
archivo para descartar un problema de espacios antes de asumir que es un
problema de códec o de hardware.

## Nota sobre códecs de video

Los videos de las carpetas `Set` se decodifican por hardware (`mpv
--hwdec=v4l2m2m-copy` en la Raspberry Pi 2), que soporta **H.264** — el
códec indicado en `MASTER_SPECIFICATION.md`. Un archivo `.mov` recién
salido de un iPhone suele ser **HEVC/H.265** en vez de H.264 (depende de
la configuración "Formatos" en Ajustes → Cámara de iOS), que esta ruta
de decodificación por hardware no soporta. Si un video se ve bien en un
teléfono/computador pero no a través del pedal, revisa su códec
(`ffmpeg -i <archivo>` lo muestra en la línea `Video:`) antes de
sospechar del nombre del archivo.

El ejemplo del doble espacio de arriba en realidad pasó junto con
exactamente esto: el mismo archivo, incluso arreglando el nombre,
tampoco se iba a reproducir, porque `ffmpeg -i` muestra que es `hevc
(Main 10) ... 3840x2160, 59.94 fps` — 4K, 10-bit, HEVC, 60fps. Cada
parte de eso está por encima de lo que este hardware puede decodificar
(H.264 es el único códec decodificado por hardware, y ni por software
tiene una posibilidad real de mantener el ritmo un 4K 10-bit HEVC en una
Pi 2). **Re-codifica antes de copiar a la biblioteca**, no solo renombres:

```
ffmpeg -i entrada.mov -c:v libx264 -pix_fmt yuv420p -vf scale=-2:1080 \
       -c:a aac -b:a 192k -movflags +faststart "A - nombre de canción.mp4"
```

`-pix_fmt yuv420p` importa más de lo usual acá — es lo que baja el HDR
de 10-bit al formato plano de 8-bit que espera el decodificador de
hardware. `scale=-2:1080` lo limita a 1080p (la resolución objetivo de
este proyecto); quita esa bandera solo si el origen ya es 1080p o menor.
Exporta directo como `.mp4` con el patrón correcto de `<Letra> - nombre`,
así este paso tampoco puede reintroducir el error de espaciado de arriba.
