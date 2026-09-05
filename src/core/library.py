"""
Library: resolves an abstract SelectTrack(setlist, track) into a real file
path on the library USB drive (section 2 of MASTER_SPECIFICATION.md).

Directory convention on the USB (agreed with the user):

    <usb_root>/
    ├── active_show.txt          -- one line: exact name of the active show folder
    ├── <Show name>/
    │   ├── Set 1/
    │   │   ├── A - Song name.mp3
    │   │   ├── B - Song name.mp4
    │   │   └── C - Song name.wav
    │   └── Set 7/
    │       └── ...
    └── standby.mp4

track 1/2/3 map to letters A/B/C respectively -- track 4 (D) never reaches
this class in practice, since the Mapper already turns it into Stop()
before the Core sees it.

Supported file types (section 2 of MASTER_SPECIFICATION.md):
- Video, with embedded audio: .mp4, .mov, .mpeg/.mpg
- Audio-only: .mp3, .wav -- these behave the same way (the standby video
  keeps looping on screen while the audio plays over it)

resolve() reports which kind a file is via ResolvedTrack.is_audio_only,
so the Core (via the Player) knows whether to switch the video or just
overlay audio on top of the current standby loop.

Robustness rule (explicitly requested by the user): if more than one
folder matches the requested Set number (e.g. "Set 7" and "Set 07" both
present by mistake), or more than one file matches the requested track
letter within a Set, the first one found is used, in whatever order the
filesystem happens to list them -- no specific order is guaranteed or
required. The goal is that a naming mistake in the library never makes a
Set/track unreachable; it just makes which duplicate gets picked
unspecified.

This class never writes to or deletes anything on the USB -- read-only,
matching the "never format/delete the library" requirement in section 2.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_TRACK_LETTERS = {1: "A", 2: "B", 3: "C"}
_SET_FOLDER_RE = re.compile(r"^Set (\d+)$")
_AUDIO_ONLY_EXTENSIONS = {"mp3", "wav"}
_VIDEO_EXTENSIONS = {"mp4", "mov", "mpeg", "mpg"}
_ALL_EXTENSIONS = _AUDIO_ONLY_EXTENSIONS | _VIDEO_EXTENSIONS


@dataclass(frozen=True)
class ResolvedTrack:
    """What Library.resolve() hands back: a real file path plus enough
    information for the Player to decide how to play it."""
    path: str
    is_audio_only: bool


def _track_file_pattern(letter: str) -> re.Pattern:
    extensions = "|".join(_ALL_EXTENSIONS)
    return re.compile(rf"^{letter} - .+\.({extensions})$", re.IGNORECASE)


class Library:
    def __init__(self, usb_root: str):
        self.usb_root = usb_root

    def active_show_path(self) -> Optional[str]:
        """Returns the absolute path to the active show's folder, or None
        if active_show.txt is missing, empty, or points to a folder that
        doesn't exist."""
        pointer_path = os.path.join(self.usb_root, "active_show.txt")
        try:
            with open(pointer_path, "r", encoding="utf-8") as f:
                show_name = f.read().strip()
        except OSError:
            logger.warning("Could not read %s", pointer_path)
            return None

        if not show_name:
            logger.warning("%s is empty", pointer_path)
            return None

        show_path = os.path.join(self.usb_root, show_name)
        if not os.path.isdir(show_path):
            logger.warning(
                "active_show.txt points to '%s', but that folder doesn't "
                "exist under %s",
                show_name, self.usb_root,
            )
            return None

        return show_path

    def resolve(self, setlist: int, track: int) -> Optional[ResolvedTrack]:
        """Returns a ResolvedTrack for this setlist/track, or None if it
        can't be found (missing show, missing Set folder, or no file for
        that letter -- an empty slot is a normal, expected situation, not
        an error)."""
        letter = _TRACK_LETTERS.get(track)
        if letter is None:
            logger.warning(
                "track %d has no assigned letter (only 1-3 / A-C are valid)",
                track,
            )
            return None

        show_path = self.active_show_path()
        if show_path is None:
            return None

        set_folder = self._find_set_folder(show_path, setlist)
        if set_folder is None:
            logger.info("Set %d not found in '%s'", setlist, show_path)
            return None

        file_path = self._find_track_file(set_folder, letter)
        if file_path is None:
            logger.info(
                "No file for track %s in '%s' (empty slot)", letter, set_folder
            )
            return None

        extension = file_path.rsplit(".", 1)[-1].lower()
        return ResolvedTrack(path=file_path, is_audio_only=extension in _AUDIO_ONLY_EXTENSIONS)

    def _find_set_folder(self, show_path: str, setlist: int) -> Optional[str]:
        try:
            entries = sorted(os.listdir(show_path))
        except OSError:
            return None

        # If more than one entry matches this Set number, the first one
        # found wins -- see the robustness rule in the module docstring.
        for entry in entries:
            match = _SET_FOLDER_RE.match(entry)
            if match and int(match.group(1)) == setlist:
                full_path = os.path.join(show_path, entry)
                if os.path.isdir(full_path):
                    return full_path
        return None

    def _find_track_file(self, set_folder: str, letter: str) -> Optional[str]:
        pattern = _track_file_pattern(letter)
        try:
            entries = sorted(os.listdir(set_folder))
        except OSError:
            return None

        # Same rule as above: first match wins if there happen to be
        # duplicates for the same letter.
        for entry in entries:
            if pattern.match(entry):
                return os.path.join(set_folder, entry)
        return None
