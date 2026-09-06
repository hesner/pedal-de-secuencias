# Automatic boot setup

Makes the pedal start playing (standby loop, listening for the MIDI
controller) automatically when the Raspberry Pi is powered on, with no
screen or keyboard needed (section 1 of `MASTER_SPECIFICATION.md`).

Four pieces, applied in this order: the software this project depends
on, an `/etc/fstab` entry so the library USB mounts on its own, a
`systemd` service that runs `src/main.py`, and (as the final,
deliberately-last step) a read-only overlay on the Pi's own root
filesystem.

## 0. Software prerequisites

Raspberry Pi OS (this project was developed against Lite) already ships
`python3`; install the rest:

```
sudo apt update
sudo apt install -y mpv ffmpeg ntfs-3g
```

- `mpv` -- drives all playback (`src/core/player.py`, over its JSON IPC
  socket; no `python-mpv` or other third-party Python package needed).
- `ffmpeg` -- only used by `scripts/generate_fallback_standby.sh`, to
  generate the local fallback standby video once.
- `ntfs-3g` -- only needed if your library USB is formatted NTFS, as in
  this project's own reference setup; use whatever driver matches your
  own USB drive's filesystem instead (e.g. `exfat-fuse` for exFAT).

No `requirements.txt`: the Python side of this project (`src/`) is
standard-library only, deliberately, so there's nothing to `pip install`.

## 1. Library USB — `/etc/fstab`

Add a line like this (get the real UUID for your own USB drive with
`sudo blkid /dev/sda1`, or whatever device it shows up as):

```
UUID=07C1339846657D95  /media/usb  ntfs-3g  ro,nofail,x-systemd.device-timeout=10  0  0
```

- `ro`: mounted read-only by default, matching how this project always
  operates day to day (section 2 of `MASTER_SPECIFICATION.md` -- the
  library USB must never be auto-formatted or have files auto-deleted).
  Remount read-write by hand (`sudo mount -o remount,rw /media/usb`) only
  for deliberate library management, then remount `ro` again afterward.
- `nofail` + `x-systemd.device-timeout=10`: if the USB isn't plugged in
  at boot, don't hang the boot sequence waiting for it -- give up after
  10s and continue. `pedal-core.service` (below) handles the USB still
  being absent after that by falling back to the local standby video
  (see `src/core/player.py`).

Test the line **without rebooting** before trusting it:

```
sudo mount -a
mount | grep /media/usb
```

## 2. The service — `pedal-core.service`

```
sudo cp systemd/pedal-core.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pedal-core.service
```

Check it:

```
sudo systemctl status pedal-core
journalctl -u pedal-core -f
```

The unit as committed here uses placeholders -- `<YOUR_USER>` and
`<YOUR_USB_UUID>` -- in `User=` and `ExecStart=`. Replace both with your
own values before copying it in (this project's own reference deployment
uses `User=hesner`, checkout path `/home/hesner/chocolate-pi`, and
UUID `07C1339846657D95`, matching the `/etc/fstab` entry from section 1).
Edit them again later if the checkout path, user, or library USB drive
ever changes.

`Restart=always` means the service keeps retrying every 5s if it exits
for any reason (M-VAVE not enumerated yet, USB not mounted yet, ...) --
there's no keyboard/screen to restart it by hand on a real appliance, so
it needs to recover on its own.

Deliberately uses `Wants=`/`After=` for the USB mount, not
`RequiresMountsFor=`: the latter is a hard dependency, so unplugging the
USB while the service is running makes systemd stop the whole service
(video, audio, everything) instead of letting `Player` fall back to the
local standby video the way it's designed to -- confirmed the hard way,
by unplugging the USB during a live test and getting neither the real
nor the fallback standby on screen, because nothing was running at all.
`Wants=`/`After=` only affects the order things start in at boot; it
never tears this service down because of what the USB does afterward.

## USB behavior (final decision)

Approved operational policy: the musician powers the Pi off, swaps the
USB's content on a separate computer, plugs the USB back into the Pi,
and powers the Pi back on. Editing the library while the show is
actively running is explicitly **not** a supported workflow.

A fully automatic hot-swap while the system keeps running (unplug, edit,
replug, keep going with no manual step or reboot at all) was attempted
using a `udev` rule plus a companion remount service, and separately
using a background thread that re-checked USB presence every couple of
seconds -- both approaches were abandoned: the `udev`/remount path proved
unreliable in practice on this hardware/filesystem combination (stale
mounts after unplug, the reconnected drive re-enumerating under a
different device node, `pedal-core.service`'s own `mpv` keeping the mount
busy, duplicate `udev` events racing two remount attempts against each
other), and once the actual operational policy was clarified to always
involve a reboot anyway, the background re-checking no longer matched how
this is really used and was simplified away.

**Decided final behavior**, implemented in `Player` (`src/core/player.py`):

- Whether the library USB is present is checked **exactly once, at
  startup** -- via `/dev/disk/by-uuid/<usb_uuid>` (the same UUID as in
  `/etc/fstab` and `--usb-uuid`), not by checking `--standby`'s path or
  its mount point directly. Both of the latter were tried first and found
  unreliable: `/dev/disk/by-uuid/` is populated live by udev from the
  actually-attached block devices and is unaffected by the root
  filesystem overlay (below); the other approaches gave false positives
  under one condition or the other (see the docstring on
  `Player._usb_device_is_present()` for the specifics of each).
- **USB missing at boot**: the local fallback standby plays instead
  ("Please insert the USB into the Raspberry Pi").
- **USB removed while already running**: not detected -- the system
  keeps showing/playing whatever it already had. Recovering (or first
  picking up a library update made while off) always requires a reboot;
  there is no supported way to make it happen without one.

## 3. Read-only root filesystem (final lock-down step)

Requirement: it must be safe to power the Pi off at any moment (pull the
plug) without risking corruption of its own filesystem -- this appliance
has no shutdown button. `MASTER_SPECIFICATION.md`'s read-only-library
requirement (section 2) already covers the USB; this covers the Pi's own
SD card.

Enabled via Raspberry Pi OS's built-in overlay filesystem (`raspi-config`
→ Performance Options → Overlay File System), which also write-protects
`/boot/firmware`:

```
sudo raspi-config nonint do_overlayfs 0   # enable (1 to disable again)
sudo reboot
```

After reboot, `/` is an `overlay` (`mount | grep ' / '` shows
`lowerdir=/media/root-ro` -- the real SD card, mounted `ro` -- with
`upperdir=/media/root-rw` on `tmpfs`, i.e. RAM). Every write during
normal operation lands in RAM and is discarded on every reboot; the SD
card itself is never touched, so an abrupt power loss can't corrupt it.

**Apply this last, once there's no more Pi-side development expected**:
anything written to the Pi while the overlay is active (including
syncing a new version of this code) is lost on the next reboot, since it
only ever lands in the RAM-backed upper layer. To make further changes:
temporarily disable (`do_overlayfs 1`, reboot), make and verify the
changes normally, then re-enable (`do_overlayfs 0`, reboot) once done.

Accepted trade-off, confirmed acceptable: `~/pedal-core.log` and the
systemd journal become ephemeral too (wiped every reboot, along with
everything else on `/`) -- acceptable since they're only ever used
live, during an active debugging session over SSH, not read back after
the fact.

## Maintenance / physical access

Running the service means `mpv` permanently occupies the HDMI output
(see `--force-window=yes` in `src/core/player.py`) -- this is a
software-level thing, not an OS-level lockout. To get the physical
console/login back for maintenance:

```
sudo systemctl stop pedal-core
```

SSH access is unaffected either way, regardless of what the service is
doing. If the overlay filesystem (section 3) is active, note that
`sudo` commands still work as usual -- only writes to `/` and
`/boot/firmware` land in the RAM-backed overlay instead of the real SD
card, they don't fail.
