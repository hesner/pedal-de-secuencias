"""
MIDI Mapper for the approved strategy (see MAVAVE_ANALYSIS.md, section
"4.2-4.4 Comparison of alternatives and recommendation").

Translates standard MIDI events (Program Change) into abstract Core
actions (SelectTrack, Stop). It knows nothing about USB, ALSA, or the
physical controller specifically -- it only receives (channel, program)
already decoded by the Adapter.

Portability principle (explicitly agreed with the user): this logic is
based EXCLUSIVELY on the final Program Change value. It must never read
or depend on any Control Change a controller sends internally for its own
button combinations (e.g. switching group/bank) -- that CC is a detail
specific to how each manufacturer signals its own combos, and it must not
cross into this layer. This way, any MIDI controller that sends Program
Change 0-127 (by whatever means) works with this same Mapper unchanged,
with no dependence on any proprietary feature.

Formula: PC = (group - 1) * tracks_per_group + offset, offset =
0..(tracks_per_group - 1) depending on the footswitch (A=0, B=1, C=2,
D=3).

STOP decision (approved): the last footswitch of every group (offset =
tracks_per_group - 1) is always interpreted as STOP, regardless of the
active group/setlist -- this way STOP is available instantly from any
point in the show, without sacrificing a mode or footswitch outside the
normal navigation scheme. Accepted cost: (tracks_per_group - 1) real
tracks remain per setlist.

Design note (explicitly flagged for the user's review): the diagram in
section 3 of MASTER_SPECIFICATION.md lists SELECT_SETLIST and
SELECT_TRACK as separate actions. This implementation combines them into
a single SelectTrack(setlist, track) action, because the Mapper never
receives a MIDI event that means "only the setlist changed, no track
yet" (the controller doesn't send Program Change until an actual
footswitch is pressed) -- the Mapper stays stateless. If the Core needs
to react differently when the setlist changes vs. when only the track
changes within the same setlist, that "did the setlist change from the
previous one?" comparison belongs to the Core, which does keep session
state -- not to the Mapper. Pending the user's confirmation on whether
this simplification is acceptable, or whether they'd rather the Mapper
emit the two actions separately.

Hardware note: this formula and the whole logic were designed and
empirically validated against a real MIDI controller, an M-VAVE PD41
(see MAVAVE_ANALYSIS.md and the live validation in TESTING.md); they work
the same with any other MIDI controller that sends Program Change 0-127
in this same format, with no code changes.
"""

from .actions import SelectTrack, Stop


class Mapper:
    def __init__(self, tracks_per_group: int = 4):
        if tracks_per_group < 2:
            raise ValueError(
                "tracks_per_group must be >= 2 (at least 1 real track + "
                "1 reserved for STOP is needed)"
            )
        self.tracks_per_group = tracks_per_group
        self._stop_offset = tracks_per_group - 1

    def map_program_change(self, program: int):
        """Translates a Program Change number (0-127) into an abstract
        action.

        Returns a Stop or SelectTrack instance. Never returns None: every
        valid Program Change (0-127) produces an action.
        """
        if not (0 <= program <= 127):
            raise ValueError(f"Program Change out of range: {program}")

        group_index, offset = divmod(program, self.tracks_per_group)

        if offset == self._stop_offset:
            return Stop()

        setlist = group_index + 1
        track = offset + 1
        return SelectTrack(setlist=setlist, track=track)
