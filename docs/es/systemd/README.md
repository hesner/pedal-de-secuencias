# Configuración de arranque automático

*[Read in English](../../../systemd/README.md)*

Hace que el pedal empiece a reproducir (loop de standby, escuchando al
controlador MIDI) automáticamente al encender la Raspberry Pi, sin
pantalla ni teclado (sección 1 de `MASTER_SPECIFICATION.md`).

Cinco piezas, aplicadas en este orden: flashear el sistema operativo y
configurar su primer arranque, el software del que depende este
proyecto, una entrada en `/etc/fstab` para que el USB de biblioteca se
monte solo, un servicio de `systemd` que corre `src/main.py`, y (como
paso final, deliberadamente el último) un overlay de solo lectura sobre
el propio sistema de archivos raíz de la Pi.

## 0. Flashear Raspberry Pi OS y configurar el primer arranque

Usando [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
(herramienta oficial, Windows/macOS/Linux):

1. **Choose OS** → "Raspberry Pi OS (other)" → **Raspberry Pi OS Lite
   (Legacy, 32-bit)** — el que `MASTER_SPECIFICATION.md` nombra como
   sistema operativo base de este proyecto.
2. **Choose storage** → tu tarjeta SD.
3. Antes de escribir, haz clic en el ícono de engranaje (o `Ctrl+Shift+X`)
   para abrir las opciones avanzadas y configurar, en la misma sesión:
   - **Hostname**: el despliegue de referencia de este proyecto (y cada
     ejemplo `ssh pedal` en la documentación de este repo) usa `pedal`.
     Usa el que quieras, solo sustitúyelo mentalmente donde estos
     documentos digan `pedal`/`pedal.local`.
   - **Enable SSH**, autenticación por contraseña (o pega una llave
     pública si prefieres no usar contraseña).
   - **Username and password**: tu elección, sin requisito fijo — lo que
     pongas acá se vuelve `<YOUR_USER>` en la sección 3
     (`pedal-core.service`) más adelante.
   - **Configure WiFi** (SSID, contraseña, país) si esta Pi no va a estar
     por Ethernet — o sáltatelo y usa Ethernet en su lugar, que es a lo
     que recurrieron las propias pruebas de este proyecto cuando el WiFi
     se puso inestable (ver `TESTING.md`).
   - Idioma/zona horaria/teclado según corresponda.
4. Escribe, mueve la tarjeta a la Pi y enciéndela. El primer arranque
   tarda un minuto o dos más de lo normal (redimensión de partición,
   llaves SSH del host).
5. Desde otra máquina en la misma red:
   ```
   ssh <tu-usuario>@<hostname>.local
   ```
   La resolución `.local` (mDNS) no es totalmente confiable en la
   práctica (conocida por fallar por WiFi). Si no resuelve, saca la IP
   de la Pi de la lista de clientes DHCP de tu router y usa `ssh
   <tu-usuario>@<esa-ip>`.

## 1. Prerequisitos de software

Raspberry Pi OS (este proyecto se desarrolló contra Lite) ya trae
`python3`; instala el resto:

```
sudo apt update
sudo apt install -y mpv ffmpeg ntfs-3g
```

- `mpv` — maneja toda la reproducción (`src/core/player.py`, sobre su
  socket IPC en JSON; no hace falta `python-mpv` ni ningún otro paquete
  de Python de terceros).
- `ffmpeg` — solo lo usa `scripts/generate_fallback_standby.sh`, para
  generar el video de standby de respaldo local una vez.
- `ntfs-3g` — solo hace falta si tu USB de biblioteca está formateado en
  NTFS, como en el setup de referencia de este proyecto; usa el driver
  que corresponda al sistema de archivos de tu propio USB (ej.
  `exfat-fuse` para exFAT).

Sin `requirements.txt`: el lado Python de este proyecto (`src/`) es solo
librería estándar, deliberadamente, así que no hay nada que instalar con
`pip`.

## 2. USB de biblioteca — `/etc/fstab`

Agrega una línea como esta (obtén el UUID real de tu propio USB con
`sudo blkid /dev/sda1`, o el dispositivo que corresponda):

```
UUID=07C1339846657D95  /media/usb  ntfs-3g  ro,nofail,x-systemd.device-timeout=10  0  0
```

- `ro`: montado de solo lectura por defecto, igual que este proyecto
  opera siempre en el día a día (sección 2 de `MASTER_SPECIFICATION.md`
  — el USB de biblioteca nunca debe formatearse automáticamente ni sus
  archivos borrarse solos). Remonta en lectura-escritura a mano (`sudo
  mount -o remount,rw /media/usb`) solo para gestión deliberada de la
  biblioteca, y vuelve a `ro` después.
- `nofail` + `x-systemd.device-timeout=10`: si el USB no está conectado
  al arrancar, no cuelgues la secuencia de arranque esperándolo — desiste
  después de 10s y continúa. `pedal-core.service` (abajo) maneja que el
  USB siga ausente después de eso cayendo al video de standby local (ver
  `src/core/player.py`).

Prueba la línea **sin reiniciar** antes de confiar en ella:

```
sudo mount -a
mount | grep /media/usb
```

## 3. El servicio — `pedal-core.service`

```
sudo cp systemd/pedal-core.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pedal-core.service
```

Revísalo:

```
sudo systemctl status pedal-core
journalctl -u pedal-core -f
```

La unidad tal como está en el repo usa placeholders — `<YOUR_USER>` y
`<YOUR_USB_UUID>` — en `User=` y `ExecStart=`. Reemplaza ambos con tus
propios valores antes de copiarla (el despliegue de referencia de este
proyecto usa `User=hesner`, ruta de checkout `/home/hesner/chocolatepi`,
y UUID `07C1339846657D95`, coincidiendo con la entrada de `/etc/fstab`
de la sección 2). Edítalos de nuevo más adelante si la ruta de checkout,
el usuario, o el USB de biblioteca cambian.

`Restart=always` hace que el servicio siga reintentando cada 5s si
termina por cualquier razón (el M-VAVE aún no enumerado, el USB aún no
montado, ...) — no hay teclado/pantalla para reiniciarlo a mano en un
appliance real, así que tiene que recuperarse solo.

Usa `Wants=`/`After=` para el mount del USB deliberadamente, no
`RequiresMountsFor=`: esta última es una dependencia dura, así que
desconectar el USB mientras el servicio corre hace que systemd detenga
todo el servicio (video, audio, todo) en vez de dejar que `Player` caiga
al video de standby local como está diseñado — confirmado de la forma
difícil, desconectando el USB durante una prueba en vivo y sin obtener
ni el standby real ni el de respaldo en pantalla, porque no había nada
corriendo. `Wants=`/`After=` solo afecta el orden de arranque; nunca
tumba este servicio por lo que el USB haga después.

## Comportamiento del USB (decisión final)

Política operativa aprobada: el músico apaga la Pi, cambia el contenido
del USB en otra computadora, vuelve a conectar el USB a la Pi, y la
enciende de nuevo. Editar la biblioteca con el show en curso
explícitamente **no** es un flujo de trabajo soportado.

Se intentó un hot-swap totalmente automático (desconectar, editar,
reconectar, sin reiniciar) vía una regla de `udev` + un servicio de
remount, y por separado vía sondeo en segundo plano; ambos se
abandonaron por poco confiables en esta combinación de hardware/sistema
de archivos — ver `CHANGELOG.md`/el historial de git si te tienta
reconstruir uno.

**Comportamiento final decidido**, implementado en `Player`
(`src/core/player.py`):

- Si el USB de biblioteca está presente se revisa **exactamente una vez,
  al arrancar** — vía `/dev/disk/by-uuid/<usb_uuid>` (el mismo UUID que
  en `/etc/fstab` y `--usb-uuid`). Revisar la ruta de `--standby` o su
  punto de montaje directamente se probó primero y resultó poco
  confiable bajo el overlay del sistema de archivos raíz de abajo (ver
  el docstring de `Player._usb_device_is_present()` para los detalles).
- **USB ausente al arrancar**: se reproduce el standby de respaldo local
  en su lugar ("Please insert the USB into the Raspberry Pi").
- **USB retirado mientras ya está corriendo**: no se detecta — el
  sistema sigue mostrando/reproduciendo lo que ya tenía. Recuperarse (o
  tomar una actualización de biblioteca hecha mientras estaba apagada)
  siempre requiere un reinicio; no hay forma soportada de lograrlo sin
  uno.

## 4. Sistema de archivos raíz de solo lectura (paso final de blindaje)

Requisito: debe ser seguro apagar la Pi en cualquier momento (desconectar
la energía) sin riesgo de corromper su propio sistema de archivos — este
appliance no tiene botón de apagado. El requisito de biblioteca de solo
lectura de `MASTER_SPECIFICATION.md` (sección 2) ya cubre el USB; esto
cubre la propia tarjeta SD de la Pi.

Habilitado vía el sistema de archivos overlay integrado de Raspberry Pi
OS (`raspi-config` → Performance Options → Overlay File System):

```
sudo raspi-config nonint do_overlayfs 0   # habilitar (1 para deshabilitar de nuevo)
```

Luego edita `/boot/firmware/cmdline.txt` (remóntalo `rw` primero: `sudo
mount -o remount,rw /boot/firmware`) y agrega `:recurse=0` al parámetro
`overlayroot=tmpfs` que se acaba de agregar, para que la línea quede
`overlayroot=tmpfs:recurse=0`. Vuelve a montar `/boot/firmware` como
`ro` y `sudo reboot`.

**`recurse=0` es obligatorio, no opcional**: el valor por defecto
(`recurse=1`) envuelve todos los mounts en su propio overlay, incluido
`/media/usb` — y ese overlay generado automáticamente no tiene
`nofail`, así que arrancar sin el USB de biblioteca caía directo en
systemd emergency mode (sin SSH, irrecuperable en un appliance sin
pantalla) en vez de caer al standby local como pretenden las secciones
2/3. `recurse=0` limita el overlay solo a `/`; `/media/usb` y
`/boot/firmware` ya tienen su propio `ro` en `/etc/fstab` de todas
formas, así que no pierden protección.

Después de reiniciar, `/` es un `overlay` (`mount | grep ' / '` muestra
`lowerdir=/media/root-ro` — la SD real, montada `ro` — con
`upperdir=/media/root-rw` en `tmpfs`, es decir RAM). Toda escritura
durante la operación normal cae en RAM y se descarta en cada reinicio;
la tarjeta SD en sí nunca se toca, así que una pérdida de energía
abrupta no puede corromperla.

**Aplica esto al final, una vez que no se espere más desarrollo del lado
de la Pi**: cualquier cosa escrita a la Pi mientras el overlay está
activo (incluyendo sincronizar una versión nueva de este código) se
pierde en el siguiente reinicio, ya que solo cae en la capa superior
respaldada por RAM. Para hacer más cambios: desactívalo temporalmente
(`do_overlayfs 1`, reiniciar), haz y verifica los cambios normalmente,
luego reactívalo — `do_overlayfs 0` reestablece `overlayroot=tmpfs`
**sin** `:recurse=0`, así que rehaz esa edición a `cmdline.txt` cada vez
antes de reiniciar de vuelta a él.

Compromiso aceptado, confirmado como aceptable: `~/pedal-core.log` y el
journal de systemd también se vuelven efímeros (se borran en cada
reinicio, junto con todo lo demás en `/`) — aceptable porque solo se
usan en vivo, durante una sesión activa de debugging por SSH, no se
leen después.

## Mantenimiento / acceso físico

Correr el servicio significa que `mpv` ocupa permanentemente la salida
HDMI (ver `--force-window=yes` en `src/core/player.py`) — esto es algo a
nivel de software, no un bloqueo a nivel de sistema operativo. Para
recuperar la consola física/login para mantenimiento:

```
sudo systemctl stop pedal-core
```

El acceso SSH no se ve afectado de todas formas, sin importar qué esté
haciendo el servicio. Si el sistema de archivos overlay (sección 4) está
activo, ten en cuenta que los comandos `sudo` siguen funcionando
normalmente — solo las escrituras a `/` y `/boot/firmware` caen en el
overlay respaldado por RAM en vez de la SD real, no fallan.
