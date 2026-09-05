"""
Player: controls a single, persistent mpv process over its JSON IPC socket
(section 2 of MASTER_SPECIFICATION.md -- looping standby, immediate STOP).
Playback flags match what was empirically validated in TESTING.md
(hardware decoding, direct DRM/KMS output, audio through the Behringer
card via the `dmix` ALSA device configured in `~/.asoundrc`).

Deliberately talks to mpv's raw JSON IPC protocol over a Unix socket using
only the standard library (`socket` + `json`) instead of adding the
`python-mpv` dependency -- fewer moving parts, and this project only
needs `loadfile` plus observing `end-file` events.

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
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_S = 5.0
_CONNECT_RETRY_INTERVAL_S = 0.1


class Player:
    def __init__(
        self,
        standby_path: str,
        socket_path: str = "/tmp/pedal-mpv.sock",
        audio_device: str = "alsa/mixcodec",
    ):
        self.standby_path = standby_path
        self.socket_path = socket_path
        self.audio_device = audio_device

        self._process: Optional[subprocess.Popen] = None
        self._command_sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = threading.Event()

        # Set by the Core after construction; called from the listener
        # thread whenever mpv reports a file ended.
        self.on_end_file: Optional[Callable[[str], None]] = None

    def start(self):
        """Launches mpv in idle mode, connects to its IPC socket, and
        starts looping the standby video."""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self._process = subprocess.Popen(
            [
                "mpv",
                "--idle=yes",
                "--force-window=no",
                "--hwdec=v4l2m2m-copy",
                "--gpu-context=drm",
                "--vo=gpu",
                f"--audio-device={self.audio_device}",
                f"--input-ipc-server={self.socket_path}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self._command_sock = self._connect()
        self._start_listener()
        self.go_to_standby()

    def stop(self):
        """Clean shutdown of the whole player -- for the Core's own
        shutdown, not for the abstract STOP action (see go_to_standby)."""
        self._stop_listener.set()
        if self._command_sock is not None:
            try:
                self._send({"command": ["quit"]})
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

    def play(self, path: str):
        """Loads and plays a real track. Always issues a fresh
        'loadfile replace', even if it's the same file already playing --
        that's what makes pressing the same footswitch twice restart the
        song from the beginning (approved behavior)."""
        self._send({"command": ["loadfile", path, "replace"]})
        self._send({"command": ["set_property", "loop-file", "no"]})

    def go_to_standby(self):
        """Immediate, highest-priority action -- returns to the looping
        standby video. Used both for the abstract STOP action and
        automatically when a real track finishes playing on its own."""
        self._send({"command": ["loadfile", self.standby_path, "replace"]})
        self._send({"command": ["set_property", "loop-file", "inf"]})

    # -- IPC plumbing -----------------------------------------------------

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

    def _send(self, command: dict):
        if self._command_sock is None:
            raise RuntimeError("Player is not started -- call start() first")
        data = (json.dumps(command) + "\n").encode("utf-8")
        # Guards against the listener thread and the main thread writing
        # to the socket at the same time (the listener only reads on its
        # own dedicated connection, but sharing this lock costs nothing
        # and keeps every write here serialized).
        with self._send_lock:
            try:
                self._command_sock.sendall(data)
            except OSError as e:
                logger.error("Failed sending command to mpv: %s", e)

    def _start_listener(self):
        """Background thread: mpv also pushes event messages (e.g.
        end-file) on the IPC socket -- we open a second, dedicated
        connection to read those, since the first one is used for
        sending commands from the main thread."""
        try:
            event_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            event_sock.connect(self.socket_path)
        except OSError as e:
            logger.error(
                "Could not open a second IPC connection for events: %s", e
            )
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
