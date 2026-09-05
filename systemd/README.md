# Automatic boot setup

Makes the pedal start playing (standby loop, listening for the MIDI
controller) automatically when the Raspberry Pi is powered on, with no
screen or keyboard needed (section 1 of `MASTER_SPECIFICATION.md`).

Two pieces: an `/etc/fstab` entry so the library USB mounts on its own,
and a `systemd` service that runs `src/main.py`.

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
  (see `src/core/player.py`) and simply not finding any setlist content
  until it's plugged in.

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

The unit as committed here hardcodes this project's current dev checkout
path (`/home/hesner/pedal_src_test`) and user (`hesner`) -- edit
`ExecStart`/`User` in `pedal-core.service` if either ever changes (e.g.
once this graduates from a dev checkout to a proper `git clone`d
deployment path).

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

Automatic mounting only happens **at boot** (the `fstab` entry above). A
fully automatic hot-swap while the system is already running (unplug,
edit the setlist files from a computer, replug, keep going with no
manual step at all) was attempted using a `udev` rule plus a companion
remount service, but proved unreliable on this hardware/filesystem combo
in practice: the mount point doesn't notice its underlying device
disappearing, a replugged drive often re-enumerates under a *different*
device node (`sdb` instead of `sda`), a normal unmount fails because
`pedal-core.service`'s own `mpv` keeps the standby video open
continuously, and a real USB (re)connection can fire more than one
matching `udev` event close together, racing two remount attempts against
each other. After several rounds of fixes each addressing one of those
issues, the approach was abandoned as not worth the fragility -- **decided
final behavior:**

- **USB missing at boot** (or removed at any point while running): the
  video lane's background checker (`Player._standby_checker_loop`,
  `src/core/player.py`) detects this within a couple of seconds via
  `os.statvfs()` on the library's mount point, and switches on its own to
  the local fallback standby ("Please insert the USB into the Raspberry
  Pi") -- no manual step needed just to show that message, at boot or
  mid-session alike.
- **Recovering real content after a mid-session disconnect**: requires
  power-cycling the Raspberry Pi (reinsert the USB, then reboot). There is
  no supported way to make the system pick the real content back up
  without a reboot once it has been unplugged while running.

## Maintenance / physical access

Running this as a service means `mpv` permanently occupies the HDMI
output (see `--force-window=yes` in `src/core/player.py`) -- this is a
software-level thing, not an OS-level lockout. To get the physical
console/login back for maintenance:

```
sudo systemctl stop pedal-core
```

SSH access is unaffected either way, regardless of what the service is
doing.
