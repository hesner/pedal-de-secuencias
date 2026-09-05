# Contributing

## Language

Everything in this repository -- code, comments, commit messages,
documentation -- is written in English first. Spanish translations live
under `docs/es/` alongside the English original; if you change a root
`.md` file that has a Spanish counterpart, please update both (or say so
in your PR if you can't, and someone will follow up).

## Before opening a PR

```
python3 -m unittest discover -s tests -v
```

All tests must pass; they don't require any hardware. CI runs this same
command automatically on every push and pull request.

## Adding support for a different MIDI controller

This is the most likely reason to contribute. The architecture exists
specifically so this is a contained change:

```
MIDI CONTROLLER  →  Adapter  →  Mapper  →  Core
```

- Your work belongs in a new module under `src/adapter/`, following the
  shape of `src/adapter/mvave_adapter.py`.
- The `Mapper` (`src/mapper/`) and `Core` (`src/core/`) should need zero
  changes -- they only ever see standard MIDI Program Change messages and
  abstract actions (`SelectTrack`, `Stop`), never anything specific to a
  particular controller. If you find yourself needing to change either
  one to support a new controller, something about the controller likely
  belongs in the Adapter instead -- open an issue to discuss first.
- Document what you tested it against (device, firmware/mode, and how
  you confirmed the mapping) the way `MAVAVE_ANALYSIS.md` does for the
  M-VAVE PD41.

## Design rationale and prior decisions

`MASTER_SPECIFICATION.md` is this project's actual contract -- every
approved architectural decision and why it was made. `TESTING.md` has
the hardware validation history. Read both before proposing a change to
existing behavior; there's a good chance the alternative was already
tried and rejected for a documented reason (e.g. USB hot-swap-while-
running, or forcing the display's native refresh rate).

## Code style

Match what's already there: small, single-purpose modules, dataclasses
for plain data (see `src/mapper/actions.py`), no third-party Python
dependencies (standard library only), comments that explain *why*
rather than restating the code.
