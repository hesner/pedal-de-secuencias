# MAVAVE_ANALYSIS.md — M-VAVE controller analysis (PD41 model)

**Status: full recommendation ready for review and approval (section 6) — not implemented yet.**

---

## 1. Capabilities per the manual (`PD41-Software-Instructions.pdf`)

The device is configured from a **manufacturer's phone app, over Bluetooth** — there's no indication this can be done from the Raspberry Pi. Important fact confirmed by the user: **Bluetooth configuration works simultaneously while the USB stays connected to the Raspberry Pi** — no need to disconnect it to reconfigure live.

Real physical hardware (confirmed with a photo, doesn't match the manual's diagrams 1:1): **4 footswitches (A, B, C, D)**. "E" and "F" are not separate footswitches — they are labels printed between A-B and between C-D, corresponding to pressing those two footswitches **simultaneously**.

12 operating modes, selectable only from the app:

| # | Mode | Standard MIDI? |
|---|---|---|
| 1 | Program Change A (PC) | Yes |
| 2 | Program Change B (CC) | Yes |
| 3 | Custom Control (CC) | Yes |
| 4 | Advanced Custom Mode 1 (PC/CC/Note/SysEx, 5 sub-modes) | Yes |
| 5 | Advanced Custom Mode 2 (same as 4 + E/F group switching, up to 16 groups) | Yes |
| 6 | Manufacturer Control | **Do not use** — proprietary control for other M-VAVE products (TANK-G, LOOPER PRO, LOST TEMPO) |
| 7 | Touchscreen (swipe gestures) | **No** — it's HID, not MIDI |
| 8 | Video (rewind/play/pause/loop, requires a Chrome extension) | **No** — HID |
| 9-10 | Keyboard A/B | **No** — HID keyboard |
| 11 | Multimedia keys | **No** — HID |
| 12 | Custom keyboard (combinations) | **No** — HID |

**Important:** in modes 7-12 the M-VAVE probably doesn't present itself to the Raspberry Pi as a MIDI device at all (it behaves as a USB keyboard/mouse). Only modes 1-5 are viable for this project.

---

## 2. Empirical validation (section 4.1.1) — manual vs. measured real behavior

Methodology: M-VAVE connected via USB directly to the Raspberry Pi, live capture with `aseqdump -p 20:0` (ALSA port `SINCO MIDI 1`), physical presses performed by the user in real time while correlating with the log.

### "Advanced Custom Mode 1" — ⚠️ important context note

**This specific configuration (notes 36/38/40, D as a mass note-off) is the user's pre-existing custom configuration for another MIDI system unrelated to this project — it is not the factory/generic behavior of the mode.** It should not be interpreted as validating the manual for "Advanced Custom Mode 1" in general, only as evidence that the mode allows that kind of asymmetric configuration. To genuinely validate the manual in this mode (for example, the "Long Press" sub-mode) a footswitch would need to be reconfigured from scratch, which would overwrite the user's existing configuration for their other system — pending a decision on whether that's worth doing.

| Action | Manual says | Actually measured |
|---|---|---|
| Press A | Sends a corresponding MIDI code | `Note On, channel 0, note 36, velocity 127` |
| Press B | same | `Note On, channel 0, note 38, velocity 127` |
| Press C | same | `Note On, channel 0, note 40, velocity 127` |
| Press D | same (a distinct note would be expected, e.g. 42) | **Doesn't send its own note — sends `Note Off` for notes 36, 38, and 40 at once** (equivalent to "release everything") |
| Release A/B/C | (not explicitly documented for this sub-mode) | **`Note Off` never arrives** on release — the manual describes this behavior as "Single Tap": a single code per tap, no release event |
| E (A+B simultaneous) | Changes group (per general Mode 4) | **No effect, no MIDI message** — matches "Mode 4: Switching Groups: Cannot switch banks using buttons E and F" |
| F (C+D simultaneous) | same | **No effect**, same as E |

**Undocumented discrepancy/finding:** button D acting as a "mass note-off" for A/B/C is not described in the manual — it's a specific configuration someone (probably at the factory) gave D in this sub-mode, not a generic behavior of the mode. Relevant to the STOP design (section 4.5): a similar pattern could be used deliberately for a "stop everything" action.

### "Program Change A" mode

| Action | Manual says | Actually measured |
|---|---|---|
| Press A (group 1) | PC 0-127 depending on group | `Program Change, channel 0, program 0` ✅ matches |
| Press B (group 1) | — | `Program Change, program 1` ✅ |
| Press C (group 1) | — | `Program Change, program 2` ✅ |
| Press D (group 1) | — | `Program Change, program 3` ✅ |
| E (A+B) — change group | "Use buttons E and F to switch groups" | Confirmed: sends `Control Change, controller 2, value N` (N appears to be an internal group counter, offset not precisely confirmed — not necessarily equal to the number shown on the display) |
| Press A in the group shown as "7" | Should follow the group pattern | `Program Change, program 24` — **confirms the formula `PC = (displayed_group - 1) × 4 + offset(A=0,B=1,C=2,D=3)`** |
| Press B/C/D in group "7" | — | `25, 26, 27` — ✅ confirms the formula exactly |
| Display showing the "specific PC code" | The manual literally says: *"Display: The specific PC code will be shown on the display screen"* | **Real discrepancy:** the display shows **"group+letter"** (e.g. `7A`, `7b`, `7c`, `7d`), **not the raw PC number** (24, 25, 26, 27). The manual describes this behavior incorrectly. |

**⚠️ Important correction (2026-09-05, later live validation session): there are only 8 real groups, not 32.** The original capacity calculation (32 groups × 4 = 128 combinations) assumed the full Program Change range (0-127) is split into 32 groups of 4. Validated live with real hardware that **the group counter cycles with a period of 8**, not 32:

| Action | Measured result |
|---|---|
| From displayed group "1", press E repeatedly down to the lower limit | Reaches displayed group "8" (doesn't stay at "1", doesn't keep decreasing) |
| Press F from group "8" | Goes back to group "1" — wraparound confirmed |
| Press A in group "8" (display stable, not blinking) | `Program Change, program 28` — matches the formula `(8-1)×4+0=28`, confirming that "8" is a real, valid group |
| Press A in group "1" after the wraparound from "8" | `Program Change, program 0` — identical to the original "1A", confirming the cycle genuinely returns to the same group 1 |

This matches a piece of text from the app itself (Advanced device control) that had been dismissed earlier as an ambiguous translation: *"A total of 8 groups of 32 timbre"* — the correct reading is **8 groups, 32 total PC values used** (8×4=32), not "32 groups." The PC range actually used by this mode is **0-31**, never 32-127, no matter how many times E/F is pressed.

**Impact on maximum capacity:** with D reserved for STOP in every group (already-approved decision, section 4.5), the real capacity is `8 groups × 3 real songs (A,B,C) = 24 songs maximum`, not 96 as previously calculated. This is not enough for the band's real repertoire (~25-30 songs) — it reopens the strategy discussion, see the follow-up discussion in the chat with the user.

*Process note: during this test, a brief episode of erratic MIDI messages was observed (a burst of Control Change on controllers 2/3, and channel-reset messages 124-127) coinciding with a dropped ALSA connection between the M-VAVE and the listener process on the Raspberry Pi — initially interpreted as a possible invalid firmware state, but after a clean reconnection the behavior was deterministic and reproducible (confirmed twice). This is attributed to a USB/MIDI reconnection hiccup, not to the pedal's group logic.*

**Partial conclusion for this mode:** very predictable, mathematically clean, and the easiest to map in the Mapper without ambiguity — a good candidate for alternatives A/C in section 4.2. **Corrected maximum capacity: 24 songs (8 groups × 3), not 96.**

**Finding about long press (relevant to STOP, section 4.5):** in "Program Change A," **a long press (2-3s) sends no MIDI message at all** — only short taps are recognized. Confirmed twice (with capture-tool buffering ruled out as a cause), and confirmed that the button keeps working normally for short taps immediately afterward. This implies that **modes 1/2 (Program Change A/B) cannot by themselves implement a long-press STOP** — that requires using Advanced Custom Mode 1/2 with a footswitch explicitly configured in its "Long Press" or "Short Tap-Long Press" sub-mode.

### "Program Change B" mode

| Action | Manual says | Actually measured |
|---|---|---|
| Press A (group 1) | Sends **CC** codes, from `CC(0,0)` to `CC(127,0)` | `Program Change, channel 0, program 0` — **identical to Program Change A, not CC** |
| Press B/C/D (group 1) | same | `Program Change, program 1, 2, 3` — same pattern as Program Change A |

**Confirmed, significant discrepancy:** contrary to what the manual says, "Program Change B" **does not send CC codes** — at the MIDI message level it is indistinguishable from "Program Change A" in the tests performed (group 1, short press). Procedure ruled out as the cause (the user confirmed that switching modes in the app is reflected immediately on the pedal's physical display, with no extra sync steps). No condition has yet been found under which this mode would produce a message different from "Program Change A" — pending further investigation if clarifying this becomes a priority.

### "Custom Control" mode

| Action | Manual says | Actually measured |
|---|---|---|
| Press A (1st tap) | Footswitch [A] pre-assigned to "Bank Select MSB" (CC0) in the manual's capture | `Control Change, channel 0, controller 0, value 127` ✅ matches |
| Press A (2nd tap) | "Clicking on the corresponding footswitch will send a toggle code" | `Control Change, controller 0, value 0` ✅ **confirms the 127/0 toggle exactly as the manual describes** |
| Display while held down | Not documented | Shows a temporary dash **"—"** while the button is physically held, returns to the normal value on release |

**Conclusion for this mode:** the only one of the three validated so far where behavior matches the manual 100%, with no discrepancies.

---

## 3. Real capacity of the physical display (2 characters, not just numeric)

Confirmed with photos of the physical device: the display can show **letters in addition to numbers** (`2d`, `11`, `1A`, `7A`, `7b`, `7c`, `7d` were observed). It has 2 characters. This contradicts any assumption that it was purely 2-digit numeric — it is alphanumeric (7- or 14-segment, not confirmed which, but the character set includes at least digits and some lower/uppercase letters).

---

## 4.5 STOP analysis (most robust mechanism)

Empirical evidence collected specifically for this decision:

| Candidate mechanism | Real result | Viable for STOP |
|---|---|---|
| Long press in Program Change A/B | **Sends no MIDI at all** — confirmed twice | ❌ No |
| Long press in Custom Control | Behaves the same as a short press (a single toggle) | ❌ Doesn't offer anything different |
| Simultaneous 2-button combination (A+B) | **Generates no combination code** — each button sends its own CC independently. A possible mechanical bounce (double toggle) was also observed on one of the two buttons during the test | ❌ No hardware shortcut; it would have to be detected in software with timing windows — more fragile, and less "reliable" than section 4.3 requires |
| Simultaneous 4-button combination | **Discarded without testing — not physically realistic for a musician live** (confirmed by the user: at most 2 footswitches at once, one per foot) | ❌ Discarded for ergonomics, not for MIDI |
| A footswitch dedicated to a single fixed CC in Custom Control | Clean, 100% predictable behavior (validated above) | ✅ **Yes** |
| "Short Tap-Long Press" sub-mode of Advanced Custom Mode 1 (user's existing config for another system) | Manual: "Sends two different MIDI codes with a short tap and a long press" | ✅ **Confirmed real, on two different buttons**: short D → `Note Off` (36/38/40) / long D → `Program Change 3`. Short A → `Note On 36` / long A → `Program Change 0`. Consistent pattern, not a one-off on a single button. |

### Preliminary STOP recommendation (updated)

The finding about button D (short tap vs. long press sending different messages) **reopens long press as a viable mechanism**, provided the "Short Tap-Long Press" sub-mode of Advanced Custom Mode is used (not the simple modes 1/2/3, where we already confirmed a long press sends nothing). Two robust options remain, with a real trade-off given there are only **4 physical footswitches in total**:

| Option | Advantage | Cost |
|---|---|---|
| **(a)** A footswitch dedicated exclusively to a fixed CC in Custom Control | Simpler to implement in the Mapper (a single condition, no timing) | Sacrifices an entire footswitch just for STOP — 3 remain for everything else (setlist/track/play/next) |
| **(b)** A footswitch in "Short Tap-Long Press" mode: short tap = normal function (e.g. NEXT), long tap = STOP | Uses the same footswitch for two functions — all 4 remain available for normal use, STOP is "free" on top of one of them | Depends on the Mapper reliably telling short from long apart (more logic than a plain CC, although the M-VAVE itself already makes that distinction in hardware, not the Mapper) |

Both minimize dependence on proprietary features (CC and PC/Note are standard MIDI in both cases) and are portable to a future controller. The choice between (a) and (b) depends on how many footswitches the final navigation strategy actually needs (section 4.2) — **pending that comparison before recommending a single option**, not decided here.

---

## 4.2-4.4 Comparison of alternatives and recommendation

### Real physical constraint (not in the manual)

There are only **4 physical footswitches** (A-D). "E" and "F" are not separate buttons — they are the A+B and C+D combinations. This narrows the design space considerably: any alternative has to split 4 physical actions (plus group switching via E/F where available) among setlist selection, track selection, and STOP.

### Evaluating the 4 alternatives against the real evidence

**Alternative A — Bank/Group → Setlist; Footswitch → Track:**
This is literally what "Program Change A" mode already does out of the box: E/F changes group (validated: sends `CC controller 2`, group value), and A-D within a group send `Program Change = (group-1)×4 + offset`. The physical display **shows "group+letter" directly** (e.g. `7A`), giving the musician clear feedback about which setlist/track they're on — this carries "Very high" weight in section 4.3 and is already solved by the hardware itself, nothing to build. With **8 real groups** × 4 tracks (3 real + STOP), it covers 32 PC values — see the capacity correction in this mode's empirical validation section; this PD41's manual never mentions "128 timbres," that figure came from a different M-VAVE model.

**Alternative B — Program Change → global selection:**
This is an "unstructured" version of the same thing: treating the 128 PC values as a flat space, without conceptually distinguishing setlist from track. It works just as well at the MIDI level, but **wastes the display feedback** (which already comes naturally structured as group+letter) and shifts to the Mapper the responsibility of imposing a hierarchy the hardware already gives for free. Not recommended over A.

**Alternative C — Bank/Group → Setlist; PC/CC → Track:**
Very similar to A. The only real difference would be using CC instead of PC for the track — but **we already confirmed that "Program Change B" (the mode meant for CC) actually sends Program Change, not CC** (real manual discrepancy, section 2 of this document). This weakens the premise of "using CC for track" as something distinct from alternative A — in practice, it would end up being the same as A.

**Alternative D — CC/Note → abstract actions (no banks):**
This is what we saw in "Custom Control" mode: each footswitch is an independent CC toggle, fully flexible, with no bank concept. But **the display shows no useful information in this mode** (only `00` and a temporary dash when pressed) — it completely loses the "information visible on the display" criterion (Very high). It's the most flexible option for one-off actions (which is why we used it to think through STOP), but not for navigating setlists/tracks live.

### Final recommendation

**We recommend Alternative A (M-VAVE Bank/Group = Setlist; Footswitch = Track), implemented on top of "Program Change A" mode.** Reasons, backed by measured real evidence (not the manual):

1. **On-display information solved by hardware**: the musician sees "group+letter" without us building anything — meets the highest-weighted criterion with no engineering effort.
2. **Total mathematical predictability**: `PC = (group-1)×4 + offset`, validated with multiple real button presses, no ambiguity.
3. **100% standard MIDI** (Program Change), with no dependence on the manufacturer's proprietary features (Mode 6) or on Bluetooth configuration for normal live operation.
4. **Future compatibility**: any MIDI controller that can send Program Change plus some way of switching "banks" works as a replacement, without touching the Core (the group=setlist equivalence lives in the Adapter/Mapper, as required by section 3).
5. Real limitation to document: 4 tracks per setlist. If this turns out to be insufficient for NO FUTURO's real songs, it's a known cost of this alternative, not a surprise.

**STOP** (see section 4.5 above): the "Advanced Custom Mode 2 + long press" variant is discarded for three confirmed reasons:
1. There is no second free Advanced Custom Mode slot independent of the one the user already configured for another system — testing it would mean modifying that existing configuration.
2. That mode doesn't offer the display feedback (group+letter) that Program Change A does.
3. More importantly: **STOP must be available instantly from any point in the show**, regardless of which setlist/track the musician is on. Any mechanism tied to normal navigation (a specific footswitch within the group scheme, or a reserved PC value you have to "navigate to") violates that highest-priority requirement from section 2.

**Final STOP recommendation: dedicate one entire physical footswitch exclusively to STOP, outside the setlist/track navigation scheme.** Accepted cost: 3 footswitches remain for tracks instead of 4 (**8 real groups × 3 tracks = 24 combinations** — see the capacity correction above; the original "96 instead of 128" calculation assumed 32 groups, corrected to 8 groups after live validation) — that's the price of STOP being truly immediate and independent of navigation state, which is exactly the highest-weighted criterion ("Reliability of a permanent STOP: Very high") in section 4.3. The dedicated STOP footswitch would send a fixed standard MIDI code (e.g. a specific Note On or CC on a separate channel), interpreted by the Mapper as the abstract STOP action regardless of the active group/context — it requires no mode change on the M-VAVE and doesn't touch the user's existing configuration.

### Explicit design principle for future portability (architectural commitment)

For this recommendation to genuinely satisfy "future compatibility with another controller" (section 4.3), the Mapper **must compute setlist/track solely from the final received Program Change value** (`setlist = PC÷4 + 1`, `track = PC%4`), **without depending on the `Control Change, controller 2` message that the M-VAVE sends internally when using the E/F combination**. That CC is a detail specific to how the M-VAVE signals its own button combos — it must not cross into the Mapper as a source of truth, only the final Program Change matters. This way, replacing the M-VAVE with another controller that also sends Program Change (by whatever means: direct pads, a menu, a different bank scheme) requires no changes to the Mapper or the Core — only the Adapter specific to that new hardware, and only if the number of buttons per group changes (the "×4" in the formula).

**Do not implement yet** — this is a proposal for approval, per the workflow in section 6.

---

## 4. Pending validation (not completed in this session)

- "Program Change B" mode (CC) — exact behavior of `CC(n,0)`.
- "Custom Control" mode (Mode 3) — the described toggle (`CC(1,1)` / `CC(1,0)` alternating).
- "Advanced Custom Mode 2" — E/F group switching with up to 16 groups.
- "Long Press" / "Short Tap-Long Press" sub-mode of Advanced Custom Mode 1/2 — **explicit user decision: skipped for now**, to avoid overwriting their existing Advanced Custom Mode 1 configuration (used for another MIDI system unrelated to this project). If revisited, use Advanced Custom Mode 2 (free) instead of reconfiguring Mode 1.
- STOP mechanism (section 4.5) — separate analysis, not yet started.
- Reverse direction: whether something can be sent from the Raspberry Pi to the M-VAVE that produces a visible reaction (SysEx or other).
- Formal comparison against the criteria table in section 4.3 and final recommendation (section 4.4) — premature until the above is completed.

---

## 5. Relevant process notes

- The M-VAVE can be reconfigured from the phone app over Bluetooth **without disconnecting it from the Raspberry Pi's USB** — reduces friction for continued mode testing.
- It presents itself to Linux as a standard USB MIDI device, reported name: `SINCO` (Jieli Technology chip per `lsusb`) — it does not report the name "M-VAVE" at the USB/ALSA level.
