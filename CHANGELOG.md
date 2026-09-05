# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project doesn't use version numbers yet -- it's a single dedicated
appliance build, not a versioned library -- so entries are grouped by
date instead until that changes.

## [Unreleased]

## 2026-09-05 -- Initial public release

First open-source release. Actively used and validated against real
hardware (Raspberry Pi 2, Behringer USB audio interface, M-VAVE PD41
MIDI controller, library USB drive).

- Layered architecture (Adapter → Mapper → Core) so controller-specific
  code never leaks into playback logic.
- `Adapter` validated against an M-VAVE PD41 in Program Change A mode
  (see `MAVAVE_ANALYSIS.md` for the empirical mapping and its
  correction: 8 groups, not 32).
- `Core`: library resolution from a USB drive, `mpv`-driven video with a
  standby loop, a dedicated audio-only lane for standalone tracks, and
  audio always prioritized over video.
- Local fallback standby video for when the library USB isn't present at
  boot.
- `systemd` auto-boot service; USB presence checked once at boot only
  (no live hot-swap -- a reboot is required to pick up library changes).
- Read-only root filesystem (Raspberry Pi OS overlay) so the Pi can be
  power-cycled at any moment without filesystem corruption risk.
- MIT license, bilingual documentation (English primary, Spanish under
  `docs/es/`), GitHub Sponsors.
