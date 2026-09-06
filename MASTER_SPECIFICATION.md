# MASTER SPECIFICATION — "Chocolate Pi" Project

**This document is Claude's contract with this project.** It defines what must be built, which decisions are already approved and must not be questioned without evidence, which decisions are pending investigation, what the workflow between us and the agent must look like, and how decisions are reviewed as real evidence appears (section 9).

Do not implement anything until you have read this entire document and confirmed that you understood it.

---

## 1. What this project is

A live-performance control pedal/box, based on a Raspberry Pi, that:

- Receives standard MIDI events from a USB MIDI controller (any controller capable of sending Program Change 0-127 in the format defined in this document; see section 4 for the controller with which the architecture was validated).
- Triggers **audio** (songs/samples/effects) and **video** (clips + standby) in real time.
- Is used in live performances by the band **NO FUTURO**.
- Must work as a dedicated *appliance*: no screen or keyboard during the show, automatic boot on power-up.

The end goal is for it to be **open source**, with bilingual documentation (en/es).

All architecture, specification, supervision, and implementation work is done directly between the user and Claude — no other AI tool is involved in the project.

---

## 2. Decisions already approved (NOT renegotiable)

These decisions are closed. Claude may ask for clarification, but must not propose alternatives unless it discovers a real technical impediment and justifies it explicitly.

| Area | Decision |
|---|---|
| Base hardware | Raspberry Pi 2 |
| Operating system | Raspberry Pi OS Legacy Lite (32-bit) |
| Audio interface | Any class-compliant USB audio interface (empirically validated with a Behringer U-PHORIA UM2 — see TESTING.md) |
| MIDI controller | Any standard USB MIDI controller capable of sending Program Change 0-127, without relying on proprietary features (architecture designed and empirically validated with an M-VAVE PD41 — see section 4, MAVAVE_ANALYSIS.md, and TESTING.md) |
| Video output | HDMI, exclusively for the audience (not for the musician's monitoring) |
| Audio | MP3 and WAV playback. Both are audio-only formats and behave identically: the standby video keeps looping on screen while the audio plays over it |
| Video | MP4/MOV/MPEG, H.264 codec |
| Audio-video sync | Video clips carry their audio embedded in the same file (not separate tracks). Video and audio of the same clip must **never drift out of sync**; this is a critical requirement, not merely desirable. Standalone MP3/WAV files (the "Audio" row) are for audio-only library items, unrelated to video-clip sync |
| Audio/video priority | **Audio always takes priority over video.** Audio must never stutter, skip, or lag during a live performance; video is allowed to freeze or drop frames instead if the two ever have to trade off. Audio is the timing master: video conforms to it, never the other way around (`mpv --video-sync=audio`, `src/core/player.py`) |
| Idle mode | Standby video (`standby.mp4`) looping when nothing is playing |
| Video transition | Must be smooth (no abrupt cuts) between clips and standby |
| STOP | A global, highest-priority action; it must stop everything immediately |
| Storage | Setlist/sequence library on an external USB drive. **This USB must NEVER be formatted, nor its files auto-deleted** |
| Architecture | Modular, layered (see section 3) |
| Protocol | Standard MIDI — no proprietary controller feature may leak into the Core |
| Future-proofing | Must support replacing the current MIDI controller with another without touching the Core; a future web admin portal is possible |
| License/visibility | Open source project, MIT license -- maximally permissive, commercial use allowed, no copyleft |
| Documentation | Bilingual, English and Spanish |
| Roles | The user defines architecture/specification together with Claude (chat); **Claude Code is the implementation agent**. No other AI tool is involved in the project |
| Development environment | Claude Code runs **natively on Windows** (no WSL2). Everything hardware/OS-specific (audio, MIDI, video, systemd) is tested directly against the real Raspberry Pi via SSH, not in a simulated Linux environment on the PC |

---

## 3. Mandatory architecture (layers)

The system must be organized into independent layers. The Core must **never** know controller-specific concepts (banks, groups, 2-digit display, etc.). It must only know abstract actions.

```
MIDI CONTROLLER (any compatible one)
        │
        ▼
   MIDI ADAPTER          (translates the specific hardware into standard MIDI events)
        │
        ▼
STANDARD MIDI EVENTS      (Note On/Off, PC, CC, SysEx — standard format)
        │
        ▼
   MIDI MAPPER            (translates standard MIDI events into abstract actions)
        │
        ▼
  ABSTRACT ACTIONS        (SELECT_SETLIST, SELECT_TRACK, PLAY, STOP, NEXT, PREVIOUS, ...)
        │
        ▼
       CORE               (audio/video playback logic, library, standby)
```

Explicit rule: **no bank/group from the MIDI controller may become a literal Core concept.** Even if the final strategy ends up being "controller group = setlist," that equivalence must live in the Adapter/Mapper, never in the Core.

This allows a different controller in the future (another MIDI device, a mobile app, etc.) to produce the same abstract actions without modifying the Core.

---

## 4. Mandatory prerequisite and pending decision — MIDI controller strategy

### 4.0 Prerequisite — Validate simultaneous audio + video on the real Raspberry Pi

**Before starting the controller analysis (4.1 onward), validate this first, connected via SSH to the real Raspberry Pi:**

The Raspberry Pi 2 is limited hardware (quad-core Cortex-A7, 1GB RAM, USB 2.0 shared across all ports). Before building the MIDI Engine and the rest of the architecture, we need to confirm the hardware can sustain the real use case:

- Play an H.264 video with embedded audio (section 2 — video and audio of the same clip must never drift out of sync) over HDMI, **and** an independent MP3 at the same time if applicable, with no dropouts, audio pops, or sync drift between audio and video.
- Do this with the USB Behringer audio interface, the MIDI controller, **and the library USB drive** connected simultaneously (the 3 real devices used in the show), to detect bandwidth/power issues on the shared USB bus. The library USB should only be connected for this measurement — do not write to or modify anything on it.
- Determine and document which video playback stack is viable on Raspberry Pi OS Legacy Lite without a graphical environment (for example, whether `omxplayer` is still available on this specific image, or whether `mpv` with DRM/KMS output, `ffplay`, or another alternative is needed). This is part of this test's expected outcome, not a prior decision.
- Measure CPU/RAM usage during the test, and specifically verify that audio and video stay in sync over time (not just at the start of playback).

If this test fails or shows dropouts/desync, report it before continuing — it may change architecture decisions above (for example, whether video should be optional or lower resolution). Do not proceed to build the rest of the system without this result documented in `TESTING.md`.

### 4.1–4.5 Pending decision — MIDI controller strategy (mandatory analysis task)

**Do not implement the MIDI Engine before completing this task.**

You will be given (separately, in another message/file) the controller's configuration manual and a photo of its display (2-digit, 7-segment-style).

### 4.1 What you must analyze about the controller

- Available MIDI modes.
- Program Change: range, behavior.
- Control Change: range, behavior.
- Note On/Off: available use.
- SysEx: if applicable.
- Banks/groups: how many there are, how they are navigated.
- What the 2-digit display can actually show (numbers, which letters/characters are representable, what happens with values >9 or >99).
- Behavior of short press, long press, and button combinations.
- Which configuration is persistent on the controller itself vs. what can be controlled from the Raspberry Pi vs. what can only be configured from the manufacturer's software.
- Which behavior is standard MIDI and which is specific/proprietary to the controller.

### 4.1.1 Empirical validation with the physical controller (mandatory, not optional)

**The manual is the starting point, not the source of truth.** Manuals for this kind of controller are often incomplete or imprecise on fine details. The source of truth is measured real-world behavior.

With the controller connected via USB directly to the Raspberry Pi (over SSH, not in a simulated environment on the PC):

1. Identify the device: `amidi -l`.
2. Capture real MIDI messages live while physically testing every button, mode, and combination described in the manual: `aseqdump -p <port>` (or `amidi -p <port> -d`, as appropriate).
3. For each element in the manual (each button, each mode, each combination, each bank/group), record in a table: *what the manual says* vs. *what was actually received* (channel, message type, number, value).
4. Also check the reverse direction: whether it's possible to send something from the Raspberry Pi to the controller (SysEx or another message) that produces a visible reaction (for example, on the display) — do not assume this from the manual, verify it empirically.
5. Document any discrepancy between the manual and real behavior; these discrepancies take priority over what the manual says when deciding the strategy.

This table of measured real behavior must be included in `MAVAVE_ANALYSIS.md`, along with the alternatives analysis — it does not replace the manual analysis (4.1), it complements it and, in case of conflict, takes precedence over it.

### 4.2 Alternatives to compare (at least these, plus any you find in the manual)

- **A**: Controller Bank/Group → Setlist; Footswitch → Track.
- **B**: Program Change → global selection.
- **C**: Bank/Group → Setlist; PC/CC → Track.
- **D**: CC/Note → abstract actions (no direct mapping to banks).

### 4.3 Evaluation criteria (use this table, with this relative weight)

| Criterion | Weight |
|---|---|
| Ease of use for the musician live | Very high |
| Information visible on the controller's display | Very high |
| Number of supportable setlists | High |
| Number of supportable sequences/tracks | Very high |
| Ease of navigating live | Very high |
| Reliability of a permanent STOP | Very high |
| Standard MIDI compatibility | Very high |
| Future compatibility with another controller | Very high |
| Dependence on proprietary controller features | High (the lower, the better) |
| Implementation complexity | Medium |
| Future scalability | Very high |

### 4.4 Expected deliverable

A `MAVAVE_ANALYSIS.md` file with:

1. Real capabilities found in the manual.
2. **Empirical validation table** (manual vs. measured real behavior, section 4.1.1), with the discrepancies found.
3. Limitations (display, memory, configuration).
4. Comparison of alternatives against the criteria table.
5. Pros/cons of each alternative.
6. **A final, justified recommendation** ("We recommend strategy X because...") — do not pick the easiest to program, pick the most robust one according to the criteria and backed by measured real behavior, not just by the manual.

**Important: do not implement the strategy yet.** Present it for approval (see section 6, workflow).

### 4.5 STOP — separate, mandatory analysis

STOP is a global, highest-priority action. Analyze every available mechanism (long press, combinations, CC, Note, PC, or others) and determine the most robust implementation. The decision must:

- Minimize dependence on proprietary controller features.
- Preserve the possibility of using a different MIDI controller in the future.
- Be justified as an engineering decision, not assumed up front.

### Portability note (result of this section)

The architecture and Mapper resulting from this analysis (`src/mapper/`) are designed to work with **any MIDI controller capable of sending Program Change 0-127 in this same format**, with no code changes — no manufacturer's proprietary feature is baked into the Mapper or the Core (section 3). The physical controller used to design and empirically validate this strategy, including a live test with real hardware, was an **M-VAVE PD41** (see `MAVAVE_ANALYSIS.md` for the analysis and `TESTING.md` for the validation).

---

## 5. What Claude can do autonomously vs. what requires approval

### Autonomous (no permission needed)

- Create files.
- Modify code.
- Run tests.
- Install non-destructive packages.
- Analyze logs.
- Run Git commands (add, commit on working branches, diff, log).
- Create documentation.
- Diagnose problems.
- Propose solutions and alternatives.
- Try different approaches in a test environment.

### Requires explicit approval before acting

- Changing any decision already approved in section 2.
- Removing existing functionality.
- Changing requirements.
- Formatting the library USB drive.
- Deleting files from the setlist/sequence library.
- Deleting disks or modifying partitions.
- Any destructive operation on existing data.
- Signing up for/activating services or consuming additional API credits.
- Replacing hardware.
- Abandoning an already-approved architectural decision (such as the one in section 3).

---

## 6. Mandatory workflow

For every new requirement or module:

```
1. Define the requirement (us)
2. Claude analyzes
3. Claude proposes (without implementing)
4. We approve or request adjustments
5. Claude implements
6. Claude tests
7. We validate
8. git commit
9. Next requirement
```

Do not skip from step 2 to step 5. Every architecture or MIDI mapping proposal must go through approval before becoming final code.

---

## 7. Suggested repository structure

```
CHOCOLATE-PI/
│
├── PROJECT_REQUIREMENTS.md
├── ARCHITECTURE.md
├── MIDI_SPECIFICATION.md
├── MAVAVE_SPECIFICATION.md
├── MAVAVE_ANALYSIS.md        (generated by Claude, section 4)
├── LIBRARY_SPECIFICATION.md
├── MEDIA_SPECIFICATION.md
├── HARDWARE_SPECIFICATION.md
├── API_SPECIFICATION.md
├── SECURITY.md
├── TESTING.md
├── ROADMAP.md
│
├── docs/
│   ├── en/
│   └── es/
│
└── src/
```

These files don't all need to exist from day one; they get created as each area is defined.

---

## 8. First instruction to give Claude Code

Once Claude Code is installed and running inside the repository, the first instruction (before touching any code) should be roughly:

> This repository corresponds to the "Chocolate Pi" project. Read MASTER_SPECIFICATION.md in full. Do not implement anything yet. Confirm that you understood the approved decisions (section 2), the mandatory layered architecture (section 3), and the workflow (section 6). Point out any contradiction, technical risk, or ambiguity you find.

Once confirmed, it is asked to first run the audio+video test from section 4.0 via SSH against the real Raspberry Pi. Only after documenting that result is it given the controller's manual and asked to carry out the analysis from section 4.1 onward.

---

## 9. Continuous evidence-based review

This project does not have a fixed architecture from day one: decisions are expected to be adjusted as real evidence of hardware behavior appears (MIDI latency, audio/video stability, CPU/RAM usage, real controller limitations discovered in practice).

Claude must actively monitor the real performance of what has already been implemented. If it detects that an approved decision is not working as expected, it must:

1. **Document the concrete evidence** supporting the finding (measurements, logs, observed behavior) — never a style opinion or preference without data behind it.
2. **Propose a justified alternative**, including the cost/impact of changing it at the project's current point (what gets rewritten, what is lost, what is gained).
3. **Wait for explicit approval** before implementing the change — the same mechanism as section 6, no shortcuts.

This applies **at any point** in the project, not just during the initial analysis: whether Claude detects the problem itself by running tests, or we notice it and raise it for Claude to evaluate.

Example of how Claude should raise it:

> "The Bank/Group → Setlist strategy works, but in real tests changing groups on the controller takes ~400ms to show on the display, which can confuse the musician live. Evidence: [logs/measurements]. I propose switching to alternative C (PC/CC → Track) because it eliminates that delay. Cost of the change: the Mapper needs to be rewritten, not the Adapter or the Core. Do you approve this change?"

This isn't about constantly redesigning everything, but about no decision staying "frozen" just because it was approved once — it gets adjusted when there is real evidence to justify it, and always with our approval before touching code.
