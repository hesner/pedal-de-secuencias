"""
Abstract Core actions (section 3 of MASTER_SPECIFICATION.md).

These classes are the only thing the Mapper hands to the Core. The Core
must never see a Program Change number, a MIDI channel, or any concept
from the physical controller (groups, footswitches A-D, etc.) -- only
these actions.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectTrack:
    """Select a sequence (track) within a setlist.

    setlist and track are 1-indexed (more natural for humans / logs).
    """
    setlist: int
    track: int


@dataclass(frozen=True)
class Stop:
    """Global, highest-priority action: stop everything immediately."""
    pass
