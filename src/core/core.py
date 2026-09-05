"""
Core: the layer that owns audio/video playback (section 3 of
MASTER_SPECIFICATION.md). Only knows abstract actions (SelectTrack, Stop)
-- never a Program Change number, a MIDI channel, or any concept from the
physical controller.

Owns both playback lanes (see player.py) and decides which one a given
track goes to, based on Library.resolve()'s is_audio_only classification:
video clips replace what's on screen; audio-only tracks play over the
video lane, which is put on standby first if it wasn't already there.
"""

import logging
from typing import Optional, Tuple

from mapper import SelectTrack, Stop

from .library import Library
from .player import Player, AudioPlayer

logger = logging.getLogger(__name__)


class Core:
    def __init__(self, library: Library, player: Player, audio_player: AudioPlayer):
        self.library = library
        self.player = player
        self.audio_player = audio_player
        self._current: Optional[Tuple[int, int]] = None
        self.player.on_clip_finished = self._on_video_clip_finished
        self.audio_player.on_end_file = self._on_audio_end_file

    def start(self):
        self.player.start()
        self.audio_player.start()
        logger.info("Core started, standby playing.")

    def stop(self):
        self.player.stop()
        self.audio_player.stop()

    def handle_action(self, action):
        if isinstance(action, Stop):
            self._go_to_standby()
        elif isinstance(action, SelectTrack):
            self._select_track(action.setlist, action.track)
        else:
            logger.warning("Unknown action received: %r", action)

    def _select_track(self, setlist: int, track: int):
        resolved = self.library.resolve(setlist, track)
        if resolved is None:
            logger.warning(
                "SelectTrack(setlist=%d, track=%d) has no matching file "
                "-- ignoring (empty slot, or missing show/Set)",
                setlist, track,
            )
            return

        if resolved.is_audio_only:
            logger.info(
                "Playing audio-only setlist=%d track=%d -> %s (standby video keeps looping)",
                setlist, track, resolved.path,
            )
            self.player.go_to_standby()
            self.audio_player.play(resolved.path)
        else:
            logger.info(
                "Playing video setlist=%d track=%d -> %s", setlist, track, resolved.path
            )
            self.audio_player.silence()
            self.player.play(resolved.path)

        self._current = (setlist, track)

    def _go_to_standby(self):
        logger.info("STOP -- returning to standby.")
        self.player.go_to_standby()
        self.audio_player.silence()
        self._current = None

    def _on_video_clip_finished(self):
        """Called from the video lane's listener thread when a real clip
        finishes playing on its own. By this point the Player has already
        transitioned to standby itself (it queues standby right behind
        every clip precisely so this doesn't require a fresh command from
        here -- see Player.play()) -- so all that's left is clearing our
        own "currently selected" bookkeeping."""
        logger.info("Video clip finished on its own -- back to standby.")
        self._current = None

    def _on_audio_end_file(self, reason: str):
        """Same idea for the audio-only lane: when a standalone MP3/WAV
        finishes on its own, there's nothing to visually return to
        standby (the video lane never left it) -- just clear the
        "currently selected" state."""
        if reason == "eof" and self._current is not None:
            logger.info("Audio-only track finished on its own.")
            self._current = None
