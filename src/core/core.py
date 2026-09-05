"""
Core: the layer that owns audio/video playback (section 3 of
MASTER_SPECIFICATION.md). Only knows abstract actions (SelectTrack, Stop)
-- never a Program Change number, a MIDI channel, or any concept from the
physical controller.
"""

import logging
from typing import Optional, Tuple

from mapper import SelectTrack, Stop

from .library import Library
from .player import Player

logger = logging.getLogger(__name__)


class Core:
    def __init__(self, library: Library, player: Player):
        self.library = library
        self.player = player
        self._current: Optional[Tuple[int, int]] = None
        self.player.on_end_file = self._on_end_file

    def start(self):
        self.player.start()
        logger.info("Core started, standby playing.")

    def handle_action(self, action):
        if isinstance(action, Stop):
            self._go_to_standby()
        elif isinstance(action, SelectTrack):
            self._select_track(action.setlist, action.track)
        else:
            logger.warning("Unknown action received: %r", action)

    def _select_track(self, setlist: int, track: int):
        path = self.library.resolve(setlist, track)
        if path is None:
            logger.warning(
                "SelectTrack(setlist=%d, track=%d) has no matching file "
                "-- ignoring (empty slot, or missing show/Set)",
                setlist, track,
            )
            return

        logger.info("Playing setlist=%d track=%d -> %s", setlist, track, path)
        self.player.play(path)
        self._current = (setlist, track)

    def _go_to_standby(self):
        logger.info("STOP -- returning to standby.")
        self.player.go_to_standby()
        self._current = None

    def _on_end_file(self, reason: str):
        """Called from the Player's listener thread when mpv reports a
        file ended. Only auto-return to standby when a real track
        finished playing on its own (reason == 'eof') and we're not
        already in standby -- never for a track we ourselves just
        replaced via a new loadfile (that produces a different reason)."""
        if reason == "eof" and self._current is not None:
            logger.info("Track finished on its own -- returning to standby.")
            self._go_to_standby()
