"""
Player: controls the mpv process(es) that actually play media (section 2
of MASTER_SPECIFICATION.md -- looping standby, immediate STOP, and
audio-only tracks that keep the standby video looping while they play).

There are two independent playback lanes, each backed by its own
persistent mpv process, both talking JSON IPC over a Unix socket using
only the standard library (`socket` + `json` -- no `python-mpv`
dependency):

- `Player` (the video lane): always shows something on the HDMI output --
  either the looping standby video, or a real video clip with its
  embedded audio. This is the only lane the audience actually sees.
- `AudioPlayer` (the audio-only lane): a second, silent-by-default mpv
  instance with no video output, used only for standalone MP3/WAV
  tracks. It shares the same physical Behringer card as the video lane
  through the ALSA `dmix` device configured in `~/.asoundrc`
  (TESTING.md), so both can produce sound at once without conflicting
  over the audio device.

The Core is the one that decides which lane a given track goes to (see
core.py) -- based on Library.resolve()'s `is_audio_only` classification,
it either calls `Player.play()` (video clip) or `AudioPlayer.play()`
(audio-only), while making sure the *other* lane is in its idle state
(video lane on standby, or audio lane silent).

Assumption worth documenting: standby.mp4 is authored with no meaningful
audio of its own (silence, or negligible ambient sound), so it playing
at the same time as the audio-only lane's real content is not expected to
clash. If that assumption turns out to be wrong in practice, the video
lane's audio track would need to be explicitly muted while the audio-only
lane is active.

Known limitation (documented, not fixed): if a track finishes playing on
its own (natural end-of-file) at almost the exact same instant a new
SelectTrack is handled, there is a narrow race between the end-file event
and the new loadfile command. In practice this means a footswitch press
landing within a few milliseconds of a song's natural end could be
followed by an unwanted jump back to standby. Acceptable for now given
how rare it is in real playing; revisit if it's ever observed in
practice.
"""

import json
import logging
import os
import socket
import subprocess
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_S = 5.0
_CONNECT_RETRY_INTERVAL_S = 0.1


class _MpvProcess:
    """Low-level plumbing shared by both playback lanes: spawns one mpv
    process with the given extra flags, connects to its IPC socket (one
    connection for sending commands, a second dedicated one for reading
    events), and exposes send()/close(). Not part of this module's public
    API -- Player and AudioPlayer are.
    """

    def __init__(self, socket_path: str, extra_args: List[str]):
        self.socket_path = socket_path
        self._extra_args = extra_args
        self._process: Optional[subprocess.Popen] = None
        self._command_sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = threading.Event()
        self.on_end_file: Optional[Callable[[str], None]] = None

    def start(self):
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self._process = subprocess.Popen(
            ["mpv", "--idle=yes", "--force-window=no",
             f"--input-ipc-server={self.socket_path}", *self._extra_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self._command_sock = self._connect()
        self._start_listener()

    def stop(self):
        self._stop_listener.set()
        if self._command_sock is not None:
            try:
                self.send({"command": ["quit"]})
            except OSError:
                pass
            self._command_sock.close()
            self._command_sock = None
        if self._process is not None:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def send(self, command: dict):
        if self._command_sock is None:
            raise RuntimeError("mpv process is not started -- call start() first")
        data = (json.dumps(command) + "\n").encode("utf-8")
        with self._send_lock:
            try:
                self._command_sock.sendall(data)
            except OSError as e:
                logger.error("Failed sending command to mpv: %s", e)

    def _connect(self) -> socket.socket:
        deadline = time.monotonic() + _CONNECT_TIMEOUT_S
        last_error: Optional[OSError] = None
        while time.monotonic() < deadline:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.socket_path)
                return sock
            except OSError as e:
                last_error = e
                time.sleep(_CONNECT_RETRY_INTERVAL_S)
        raise RuntimeError(
            f"Could not connect to mpv's IPC socket at {self.socket_path} "
            f"after {_CONNECT_TIMEOUT_S}s: {last_error}"
        )

    def _start_listener(self):
        try:
            event_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            event_sock.connect(self.socket_path)
        except OSError as e:
            logger.error("Could not open a second IPC connection for events: %s", e)
            return

        def _listen():
            buffer = b""
            while not self._stop_listener.is_set():
                try:
                    chunk = event_sock.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._handle_event_line(line)
            event_sock.close()

        self._listener_thread = threading.Thread(target=_listen, daemon=True)
        self._listener_thread.start()

    def _handle_event_line(self, line: bytes):
        if not line.strip():
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return
        if message.get("event") == "end-file" and self.on_end_file is not None:
            self.on_end_file(message.get("reason", ""))


class Player:
    """The video lane -- always shows something on screen: the looping
    standby video, or a real video clip with embedded audio."""

    def __init__(
        self,
        standby_path: str,
        socket_path: str = "/tmp/pedal-mpv-video.sock",
        audio_device: str = "alsa/mixcodec",
    ):
        self.standby_path = standby_path
        self._mpv = _MpvProcess(
            socket_path=socket_path,
            extra_args=[
                "--hwdec=v4l2m2m-copy",
                "--gpu-context=drm",
                "--vo=gpu",
                f"--audio-device={audio_device}",
            ],
        )

    @property
    def socket_path(self) -> str:
        return self._mpv.socket_path

    @property
    def on_end_file(self) -> Optional[Callable[[str], None]]:
        return self._mpv.on_end_file

    @on_end_file.setter
    def on_end_file(self, callback: Optional[Callable[[str], None]]):
        self._mpv.on_end_file = callback

    def start(self):
        """Launches mpv, connects to its IPC socket, and starts looping
        the standby video."""
        self._mpv.start()
        self.go_to_standby()

    def stop(self):
        self._mpv.stop()

    def play(self, path: str):
        """Loads and plays a real video clip. Always issues a fresh
        'loadfile replace', even if it's the same file already playing --
        that's what makes pressing the same footswitch twice restart the
        song from the beginning (approved behavior)."""
        self._mpv.send({"command": ["loadfile", path, "replace"]})
        self._mpv.send({"command": ["set_property", "loop-file", "no"]})

    def go_to_standby(self):
        """Immediate, highest-priority action -- returns to the looping
        standby video. Used for the abstract STOP action, automatically
        when a video clip finishes playing on its own, and whenever an
        audio-only track is selected (see AudioPlayer)."""
        self._mpv.send({"command": ["loadfile", self.standby_path, "replace"]})
        self._mpv.send({"command": ["set_property", "loop-file", "inf"]})


class AudioPlayer:
    """The audio-only lane -- no video output of its own. Used only for
    standalone MP3/WAV tracks, which play over whatever the video lane is
    currently showing (in practice, always the standby loop -- see
    core.py, which puts the video lane on standby before handing a track
    to this lane)."""

    def __init__(
        self,
        socket_path: str = "/tmp/pedal-mpv-audio.sock",
        audio_device: str = "alsa/mixcodec",
    ):
        self._mpv = _MpvProcess(
            socket_path=socket_path,
            extra_args=["--vid=no", f"--audio-device={audio_device}"],
        )

    @property
    def socket_path(self) -> str:
        return self._mpv.socket_path

    @property
    def on_end_file(self) -> Optional[Callable[[str], None]]:
        return self._mpv.on_end_file

    @on_end_file.setter
    def on_end_file(self, callback: Optional[Callable[[str], None]]):
        self._mpv.on_end_file = callback

    def start(self):
        self._mpv.start()

    def stop(self):
        self._mpv.stop()

    def play(self, path: str):
        """Plays an audio-only track. Same restart-on-repeat-press
        behavior as Player.play()."""
        self._mpv.send({"command": ["loadfile", path, "replace"]})
        self._mpv.send({"command": ["set_property", "loop-file", "no"]})

    def silence(self):
        """Stops whatever audio-only track might be playing, without
        touching the video lane. Used on STOP and whenever a video track
        is selected (its own embedded audio takes over)."""
        self._mpv.send({"command": ["stop"]})
