"""
Library tests. No hardware needed -- they build a temporary directory tree
matching the USB convention agreed with the user and check that
Library.resolve() finds the right files and classifies them correctly.

Run with: python -m pytest tests/test_library.py -v
(or: python -m unittest tests/test_library.py)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import Library  # noqa: E402


def _make_show(root, show_name, sets):
    """sets: dict like {1: {"A": "Song 1.mp3", "B": "Song 2.mp4"}}"""
    show_path = os.path.join(root, show_name)
    os.makedirs(show_path, exist_ok=True)
    for set_number, tracks in sets.items():
        set_path = os.path.join(show_path, f"Set {set_number}")
        os.makedirs(set_path, exist_ok=True)
        for letter, filename in tracks.items():
            with open(os.path.join(set_path, f"{letter} - {filename}"), "w") as f:
                f.write("")
    return show_path


class TestLibraryResolve(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.usb_root = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_active_show(self, show_name):
        with open(
            os.path.join(self.usb_root, "active_show.txt"), "w", encoding="utf-8"
        ) as f:
            f.write(show_name)

    def test_resolves_existing_track(self):
        _make_show(
            self.usb_root,
            "Concert April 24",
            {7: {"A": "Song One.mp3", "B": "Song Two.mp4", "C": "Song Three.mp3"}},
        )
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=7, track=1)

        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.path.endswith("A - Song One.mp3"))

    def test_track_2_maps_to_letter_B(self):
        _make_show(
            self.usb_root,
            "Concert April 24",
            {1: {"A": "One.mp3", "B": "Two.mp3", "C": "Three.mp3"}},
        )
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=2)

        self.assertTrue(resolved.path.endswith("B - Two.mp3"))

    def test_missing_active_show_file_returns_none(self):
        library = Library(self.usb_root)
        self.assertIsNone(library.resolve(setlist=1, track=1))

    def test_active_show_pointing_to_missing_folder_returns_none(self):
        self._write_active_show("Does Not Exist")
        library = Library(self.usb_root)
        self.assertIsNone(library.resolve(setlist=1, track=1))

    def test_missing_set_folder_returns_none(self):
        _make_show(self.usb_root, "Concert April 24", {1: {"A": "One.mp3"}})
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        self.assertIsNone(library.resolve(setlist=99, track=1))

    def test_empty_slot_returns_none(self):
        # Set 1 exists, but track C was never populated -- a normal,
        # expected situation, not an error.
        _make_show(
            self.usb_root, "Concert April 24", {1: {"A": "One.mp3", "B": "Two.mp3"}}
        )
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        self.assertIsNone(library.resolve(setlist=1, track=3))

    def test_track_4_is_not_a_valid_letter(self):
        # Track 4 (D) should never reach the Library in practice -- the
        # Mapper turns it into Stop() before the Core sees it. Still,
        # defend against misuse.
        _make_show(self.usb_root, "Concert April 24", {1: {"A": "One.mp3"}})
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        self.assertIsNone(library.resolve(setlist=1, track=4))

    def test_inactive_show_is_ignored(self):
        _make_show(
            self.usb_root, "Concert April 24", {1: {"A": "Active song.mp3"}}
        )
        _make_show(
            self.usb_root, "Concert January 30", {1: {"A": "Archived song.mp3"}}
        )
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=1)

        self.assertTrue(resolved.path.endswith("Active song.mp3"))

    def test_duplicate_set_folders_still_resolve_to_something(self):
        # Explicit rule requested by the user: if more than one folder
        # matches the requested Set number (e.g. "Set 7" and "Set 07"
        # both present by a naming mistake), the first one found wins --
        # no particular order is required, but a Set must always be
        # found rather than the system getting confused or failing.
        show_path = os.path.join(self.usb_root, "Concert April 24")
        os.makedirs(os.path.join(show_path, "Set 7"), exist_ok=True)
        os.makedirs(os.path.join(show_path, "Set 07"), exist_ok=True)
        with open(os.path.join(show_path, "Set 7", "A - First.mp3"), "w") as f:
            f.write("")
        with open(os.path.join(show_path, "Set 07", "A - Second.mp3"), "w") as f:
            f.write("")
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=7, track=1)

        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.path.endswith(".mp3"))

    def test_duplicate_track_files_still_resolve_to_something(self):
        # Same rule, applied to two files matching the same track letter
        # within one Set.
        show_path = os.path.join(self.usb_root, "Concert April 24")
        set_path = os.path.join(show_path, "Set 1")
        os.makedirs(set_path, exist_ok=True)
        with open(os.path.join(set_path, "A - First take.mp3"), "w") as f:
            f.write("")
        with open(os.path.join(set_path, "A - Second take.mp3"), "w") as f:
            f.write("")
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=1)

        self.assertIsNotNone(resolved)
        self.assertTrue(os.path.basename(resolved.path).startswith("A - "))

    def test_mp3_is_classified_as_audio_only(self):
        _make_show(self.usb_root, "Concert April 24", {1: {"A": "Song.mp3"}})
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=1)

        self.assertTrue(resolved.is_audio_only)

    def test_wav_is_classified_as_audio_only(self):
        _make_show(self.usb_root, "Concert April 24", {1: {"A": "Song.wav"}})
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=1)

        self.assertTrue(resolved.is_audio_only)

    def test_mp4_is_classified_as_video(self):
        _make_show(self.usb_root, "Concert April 24", {1: {"A": "Clip.mp4"}})
        self._write_active_show("Concert April 24")

        library = Library(self.usb_root)
        resolved = library.resolve(setlist=1, track=1)

        self.assertFalse(resolved.is_audio_only)


if __name__ == "__main__":
    unittest.main()
