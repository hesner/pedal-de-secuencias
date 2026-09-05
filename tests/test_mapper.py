"""
Mapper tests. Require no hardware -- they validate the pure logic against
the real data captured from the M-VAVE in MAVAVE_ANALYSIS.md (section
"Empirical validation", "Program Change A" mode) and against the approved
STOP decision.

Run with: python -m pytest tests/test_mapper.py -v
(or, if pytest isn't installed: python -m unittest tests/test_mapper.py)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mapper import Mapper, SelectTrack, Stop  # noqa: E402


class TestMapperGroup1(unittest.TestCase):
    """Corresponds to the first batch of physical tests: A,B,C,D in group 1
    (right after selecting Program Change A mode) sent Program Change 0,
    1, 2, 3 respectively."""

    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_0_is_track_A_of_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(0), SelectTrack(setlist=1, track=1)
        )

    def test_pc_1_is_track_B_of_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(1), SelectTrack(setlist=1, track=2)
        )

    def test_pc_2_is_track_C_of_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(2), SelectTrack(setlist=1, track=3)
        )

    def test_pc_3_footswitch_D_is_stop_not_a_track(self):
        # Measured: D is the footswitch reserved for STOP (offset 3 = last
        # one in the group), not a real track.
        self.assertEqual(self.mapper.map_program_change(3), Stop())


class TestMapperGroup7(unittest.TestCase):
    """Corresponds to the second batch: after switching groups with E, the
    M-VAVE display showed "7A".."7d", and A,B,C,D sent Program Change 24,
    25, 26, 27."""

    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_24_is_track_A_of_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(24), SelectTrack(setlist=7, track=1)
        )

    def test_pc_25_is_track_B_of_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(25), SelectTrack(setlist=7, track=2)
        )

    def test_pc_26_is_track_C_of_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(26), SelectTrack(setlist=7, track=3)
        )

    def test_pc_27_footswitch_D_is_stop(self):
        self.assertEqual(self.mapper.map_program_change(27), Stop())


class TestMapperEdgeCases(unittest.TestCase):
    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_127_last_valid_value_is_stop(self):
        # 127 = group 32 (index 31), offset 3 -> STOP
        self.assertEqual(self.mapper.map_program_change(127), Stop())

    def test_pc_126_last_real_track_of_last_group(self):
        self.assertEqual(
            self.mapper.map_program_change(126), SelectTrack(setlist=32, track=3)
        )

    def test_negative_program_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mapper.map_program_change(-1)

    def test_program_above_127_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mapper.map_program_change(128)

    def test_tracks_per_group_is_configurable(self):
        # If a controller with 8 buttons per group instead of 4 is used
        # someday, only this parameter changes -- the Core and the
        # abstract actions don't change.
        mapper8 = Mapper(tracks_per_group=8)
        self.assertEqual(
            mapper8.map_program_change(0), SelectTrack(setlist=1, track=1)
        )
        self.assertEqual(
            mapper8.map_program_change(6), SelectTrack(setlist=1, track=7)
        )
        self.assertEqual(mapper8.map_program_change(7), Stop())  # offset 7 = last

    def test_tracks_per_group_minimum_is_enforced(self):
        with self.assertRaises(ValueError):
            Mapper(tracks_per_group=1)


if __name__ == "__main__":
    unittest.main()
