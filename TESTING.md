# TESTING.md — Test log

## Test 4.0 — Validating simultaneous audio + video on the real Raspberry Pi

**Date:** 2026-09-04 / 2026-09-05
**Objective:** confirm that the Raspberry Pi 2 can play an H.264 video with embedded audio (without drifting out of sync, either at the start or over time) simultaneously with an independent MP3, with the USB Behringer audio interface, the M-VAVE, and the library USB drive all connected at once (the 3 real devices used in the show).

### Confirmed environment

- **Hardware:** Raspberry Pi 2 Model B **Rev 1.1** (revision `a01041`, real SoC BCM2836 — `/proc/cpuinfo` reports "BCM2835" as the device tree's generic name, not the real chip). This revision is pure ARMv7, with no 64-bit support: choosing the 32-bit image isn't just a preference, it's the only one compatible with this exact board.
- **Operating system:** Raspbian GNU/Linux 12 (bookworm), kernel `6.12.93+rpt-rpi-v7`. Confirmed genuinely headless (`systemctl get-default` → `multi-user.target`, no graphical compositor running) after reflashing with the correct Lite variant — the first attempt had mistakenly installed the desktop variant (`graphical.target` + `labwc` compositor), detected and fixed before this test.
- **Audio interface:** Behringer (Texas Instruments PCM2902 chip, identifies itself as `USB Audio CODEC`).
- **MIDI controller:** detected as `SINCO` (Jieli Technology chip) via `amidi -l` — very likely the M-VAVE or a controller from the same reference family.
- **Library USB drive:** 7.6GB NTFS thumb drive, manually mounted **read-only** for this test (Lite doesn't ship with desktop automount).

### Video playback stack — result of the investigation requested in 4.0

- `omxplayer`: **not available** on this image (deprecated/removed).
- `mpv` and `ffmpeg`/`ffplay`/`ffprobe`: **not installed** by default on Raspberry Pi OS Lite; installed without issue (non-destructive package).
- Decision: **`mpv`**, with:
  - Hardware decoding: `--hwdec=v4l2m2m-copy` (uses `/dev/video10`, the Pi's V4L2 M2M decoder). "Zero-copy" mode (`--hwdec=auto` with `drmprime` output) **fails** (`Failed to commit atomic request (-22)`) with this DRM driver/mpv 0.35.1 combination — do not use.
  - Video output: `--gpu-context=drm --vo=gpu` (direct DRM/KMS rendering, no X11/Wayland needed).
  - Audio output: **through the Behringer card, not HDMI** (confirmed decision: in the final design, all audio — the clip's embedded audio and any independent track — goes out through the audio interface, HDMI is video-only). Note: additionally, this test screen's `vc4hdmi` card only exposes `IEC958_SUBFRAME_LE` format (digital passthrough), not direct PCM — another reason HDMI isn't viable for audio here, even though it's irrelevant to the final design.
  - To mix the video's embedded audio **and** an independent audio track on the same physical card at the same time, an ALSA `plug:dmix` PCM is needed, defined in `~/.asoundrc` (see below) — a raw command-line `dmix` fails if the two sources don't share the exact same format/rate/channels.

### ALSA configuration used (`~/.asoundrc` on the Pi, user `hesner`)

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

### Results — 5-minute test, real simultaneous load

1920x1080/30fps H.264+AAC video (embedded audio) + an independent 300s MP3, played at the same time, with Behringer + M-VAVE + library USB all connected. Metrics sampled every 10s throughout the test.

| Metric | Result |
|---|---|
| Audio-video sync (avsync) | Stayed between 0 and ~140ms over the 5 minutes, **with no upward trend**. Meets the section 2 critical requirement (no progressive desync). |
| Memory | Stable: ~293→312 MB used out of 921MB total, always >600MB free. No visible leaks. |
| CPU | ~25-30% usage during playback (70%+ idle). **CPU is not the bottleneck.** |
| Dropped video frames | **~70% of frames** (growing steadily and linearly, ~21 fps dropped out of a 30fps target). Confirmed real (not a test-material generation artifact). |
| Undervoltage during the test | None new (`throttled` bits unchanged during the 5 minutes of real load). |

### Pending finding: video frame drops

Identified cause: `mpv` reports `Assuming 60.000000 FPS for display sync` while the content is 30fps — there's a 30-into-60 mismatch that the current pipeline doesn't handle well, resulting in massive frame dropping to keep audio in sync (which is correctly prioritized).

- **Not a hardware/CPU limit** — there's plenty of spare CPU during the test.
- `--video-sync=display-resample` was tried as a possible fix: **it made things worse** (introduced up to 600ms of real audio-video drift, on top of still dropping frames). Discarded.
- Forcing a native 30Hz DRM mode was investigated as a possible root fix, but **the screen used in this test (a Dell P2422H PC monitor) doesn't support any real 1080p30 mode** — its EDID only offers 50/59.94/60Hz. Forcing 30Hz couldn't be tested because of this test monitor's limitation, not the Pi's.
- **Important — likely an artifact of the test environment, not of the show's real hardware:** the user confirmed this PC monitor **is not representative** of the screen that will be used at shows (typically TVs). TVs, following CEA-861, almost always do include native 24/25/30Hz modes for video content. This frame-drop issue is likely **not to occur with a real TV**, since it would eliminate the 30-into-60 mismatch at its root.
- **Pending:** repeat this specific frame-drop test with a real TV (or any screen offering a native 1080p30 mode) before declaring production video playback good or bad. Not blocking for continuing other parts of the project (such as the M-VAVE analysis) while a representative test screen is obtained.

### Power supply finding (resolved)

- **Generic Chromecast (Google) charger**, standard cable: caused a real undervoltage event that **froze the Raspberry Pi** during the sustained-load test ("Undervoltage detected!" message on screen, system unresponsive). Confirmed with `vcgencmd get_throttled` (historical undervoltage/throttling bits) and `dmesg` (the entire USB hub, all 6 ports, disconnected and reconnected 4 times in a row within the first ~95s of boot).
- **Fix applied:** a 5V/2.5A charger. With this change, only a brief, non-recurring event was observed at boot (3 of 6 ports, once, ~89s), and **there was no freeze** during the following 18+ minutes of use, including a full sustained-load test (1080p decoding + dual audio stream).
- **Open recommendation:** if the residual brief event is bothersome, also try a short, thick-gauge power USB cable — not confirmed as necessary, just a possible additional improvement.

### Conclusion for test 4.0

The hardware (Raspberry Pi 2 Rev 1.1 + USB Behringer + M-VAVE + library USB, with a 5V/2.5A supply) sustains simultaneous audio+video playback without desync and without exhausting CPU/RAM — the section 2 critical requirement (audio and video of the same clip never out of sync) is validated.

**Section 4.0 cannot be considered fully closed** until the frame-drop check is repeated with a screen representative of the show (a real TV, not the PC monitor used in this test) — there is evidence that the issue found is specific to this test monitor's refresh limitations (no native 1080p30 mode) and likely won't reproduce with a real TV. This remains a follow-up task; it does not block continuing with the M-VAVE analysis (section 4.1) while a suitable test screen is obtained.
