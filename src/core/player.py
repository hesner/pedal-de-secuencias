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

The video lane is explicitly muted whenever it's showing standby (see
Player.go_to_standby()) and unmuted whenever it's playing a real clip
(Player.play()) -- standby is meant to be a silent visual loop, so this
is enforced rather than just assumed about how standby.mp4 happens to be
authored. Muting (not disabling the audio track outright) is deliberate:
an earlier version used aid=no/aid=auto instead, but toggling a track's
enabled state forces mpv to tear down and rebuild its ALSA connection,
which was audible as a click every time a video clip started or ended.
Muting keeps the stream continuously open, so there's nothing to tear
down. Both lanes are also forced to the same fixed output sample
rate/layout (see _FIXED_AUDIO_SAMPLE_RATE below), which is what makes it
safe for `dmix` to mix the muted video stream and the audio-only lane's
real stream at the same time without glitching.

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

# Both lanes are forced to output audio at this fixed rate/layout,
# regardless of each source file's own format (see the note in Player.__init__
# and AudioPlayer.__init__): real setlist files were measured at 44100Hz
# while standby.mp4's audio was 48000Hz, and every switch between the two
# rates forced ALSA's shared `dmix` device to renegotiate -- audible as a
# crackle right at the start of a track. mpv resamples internally to this
# rate before handing audio to ALSA, so dmix's format never changes.
_FIXED_AUDIO_SAMPLE_RATE = 48000


class _MpvProcess:
    """Low-level plumbing shared by both playback lanes: spawns one mpv
    process with the given extra flags, connects to its IPC socket (one
    connection for sending commands, a second dedicated one for reading
    events), and exposes send()/close(). Not part of this module's public
    API -- Player and AudioPlayer are.

    Both connections get their own background reader thread. The command
    connection's replies (a JSON line per command sent, e.g.
    {"error": "success", ...}) are never inspected for their result --
    this class's callers don't currently need that -- but they still have
    to be read off the socket and discarded, or they simply pile up
    unread in the kernel's receive buffer for as long as this process
    keeps running. That never caused an observed problem in any single
    development session, but this is meant to run on an appliance that
    stays powered on indefinitely, not just for the length of one show,
    so it's drained properly rather than leaning on the buffer being
    "probably big enough" forever. A failed command is still logged, even
    though it isn't correlated back to which specific call sent it.
    """

    def __init__(self, socket_path: str, extra_args: List[str]):
        self.socket_path = socket_path
        self._extra_args = extra_args
        self._process: Optional[subprocess.Popen] = None
        self._command_sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._reader_threads: List[threading.Thread] = []
        self._stop_listener = threading.Event()
        self.on_end_file: Optional[Callable[[str], None]] = None

    def start(self):
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self._process = subprocess.Popen(
            ["mpv", "--idle=yes",
             f"--input-ipc-server={self.socket_path}", *self._extra_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self._command_sock = self._connect()
        self._spawn_reader(self._command_sock, self._handle_command_reply_line)

        event_sock = self._connect()
        self._spawn_reader(event_sock, self._handle_event_line)

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

    def _spawn_reader(self, sock: socket.socket, line_handler: Callable[[bytes], None]):
        """One background thread per connection, for as long as this
        process runs: reads newline-delimited JSON messages and hands
        each line to line_handler. Every open connection to mpv's IPC
        socket needs one of these -- an unread connection's incoming
        messages (replies to commands sent on it, plus every broadcast
        event) simply accumulate forever in the kernel's receive buffer
        otherwise."""

        def _read_loop():
            buffer = b""
            while not self._stop_listener.is_set():
                try:
                    chunk = sock.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line_handler(line)
            sock.close()

        thread = threading.Thread(target=_read_loop, daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _handle_command_reply_line(self, line: bytes):
        """Reply to a command sent on the command connection -- discarded
        (no caller currently needs the result of a specific command), but
        a failure is still worth a log line even without knowing which
        call triggered it."""
        if not line.strip():
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return
        error = message.get("error")
        if error is not None and error != "success":
            logger.warning("mpv command failed: %s", message)

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
    standby video, or a real video clip with embedded audio.

    drm_mode picks which physical display refresh rate mpv drives the
    screen at (mpv's --drm-mode; run `mpv --drm-mode=help` on the Pi with
    the real screen connected to see what it supports, as
    "WxH@refresh_hz", e.g. "1920x1080@25"). Defaults to mpv's own
    "preferred" (usually 60Hz) deliberately, not as an oversight: forcing
    the display's native mode to match standby.mp4's real 25fps was
    tested on the actual show TV (which does support a native 25Hz mode)
    and measured no benefit at all -- drop-frame-count was already 0 at
    60Hz, CPU usage for the video lane was statistically the same either
    way (~100%, a full core, inherent to this rendering pipeline on this
    SoC, unrelated to the refresh-rate mismatch that was suspected) --
    while looking visibly worse side by side, confirmed by the user
    watching both on the real TV. See TESTING.md. Left configurable
    (rather than removed) in case a future display/content combination
    benefits where this one didn't."""

    def __init__(
        self,
        standby_path: str,
        fallback_standby_path: str,
        usb_uuid: str,
        socket_path: str = "/tmp/pedal-mpv-video.sock",
        audio_device: str = "alsa/mixcodec",
        drm_mode: str = "preferred",
    ):
        # standby_path normally lives on the library USB; fallback_standby_path
        # lives locally on the Pi's own storage (see
        # scripts/generate_fallback_standby.sh) and is used automatically
        # whenever standby_path isn't reachable at startup -- library USB
        # not inserted when the Pi is powered on.
        #
        # Checked exactly once, in start() -- not continuously. Approved
        # operational policy: the musician powers the Pi off, swaps the
        # USB's content on a computer, plugs it back in, and powers the
        # Pi back on -- editing the library while the show is actively
        # running is explicitly not a supported workflow, so there's no
        # need to detect a USB inserted or removed mid-session, only
        # whether it's there at boot. An earlier version re-checked this
        # every couple of seconds in a background thread specifically to
        # support that mid-session case; removed since it no longer
        # matches how this is actually meant to be used, and every check
        # was that much more surface for something to go wrong (see the
        # overlay-filesystem incompatibility resolved in
        # _usb_device_is_present() below, for one).
        self.standby_path = standby_path
        self.fallback_standby_path = fallback_standby_path
        self.usb_uuid = usb_uuid
        self._resolved_standby: Optional[str] = None  # set once in start()
        self._mpv = _MpvProcess(
            socket_path=socket_path,
            extra_args=[
                # Keeps a video surface permanently mapped over the HDMI
                # output, even in the brief gap between one file ending
                # and the next being loaded. Without this, that gap
                # briefly let the Linux console/login screen underneath
                # show through on every clip transition.
                "--force-window=yes",
                "--hwdec=v4l2m2m-copy",
                "--gpu-context=drm",
                f"--drm-mode={drm_mode}",
                "--vo=gpu",
                # Audio must never stutter, skip, or drift during a live
                # show -- video is allowed to freeze or drop frames
                # instead. This is already mpv's own default, confirmed
                # in practice in TESTING.md (the alternative,
                # --video-sync=display-resample, was tried and discarded
                # specifically because it sacrificed audio sync), but set
                # explicitly here rather than relying on an unstated
                # default that could change in a future mpv version:
                # audio is the timing master, video frames are
                # dropped/repeated to keep up with it, never the reverse.
                "--video-sync=audio",
                f"--audio-device={audio_device}",
                f"--audio-samplerate={_FIXED_AUDIO_SAMPLE_RATE}",
                "--audio-channels=stereo",
            ],
        )
        # Tracks *which* standby file (real or fallback) is currently
        # playing, or None if we're playing a real clip instead. Lets
        # go_to_standby() avoid restarting the loop when nothing needs to
        # change -- see go_to_standby() below.
        self._current_standby_path: Optional[str] = None
        # Called (no arguments) when a real clip finishes playing on its
        # own -- set by the Core. Note this is a *different* thing from
        # the raw mpv "end-file" event: by the time this fires, standby is
        # already playing (see _handle_end_file below), so the Core just
        # needs to update its own bookkeeping, not ask for standby again.
        self.on_clip_finished: Optional[Callable[[], None]] = None
        self._mpv.on_end_file = self._handle_end_file

    @property
    def socket_path(self) -> str:
        return self._mpv.socket_path

    def start(self):
        """Launches mpv, connects to its IPC socket, checks exactly once
        whether the library USB is present (see _usb_device_is_present()),
        and starts looping the resulting standby video (real or
        fallback)."""
        self._mpv.start()
        self._resolved_standby = (
            self.standby_path if self._usb_device_is_present() else self.fallback_standby_path
        )
        self.go_to_standby()

    def stop(self):
        self._mpv.stop()

    def _usb_device_is_present(self) -> bool:
        """Whether the library USB (identified by its filesystem UUID,
        usb_uuid) is physically plugged in right now. Called exactly once,
        from start() -- see the note in __init__ on why this project
        doesn't re-check this while already running.

        Three earlier versions of this check turned out unreliable in
        practice:
        - Reading a byte of standby_path, and separately os.statvfs() on
          its directory: both kept answering from this ntfs-3g/FUSE
          mount's own cached state even with the USB completely
          unplugged (confirmed live -- `lsblk` showed nothing, yet both
          still succeeded).
        - Looking up standby_path's mount point in /proc/mounts and
          checking whether *that* device node still exists: reliable on
          its own, but broke once the root filesystem overlay was
          enabled (section on `systemd/`/overlayfs) -- with it active,
          /media/usb's own entry in /proc/mounts is itself an overlay
          (lowerdir=/media/root-ro/media/usb), not the real device, and
          that lowerdir path is a directory that always exists on disk
          regardless of whether anything is actually mounted there --
          confirmed live, this made the check permanently report
          "present" no matter what.

        Checking /dev/disk/by-uuid/<usb_uuid> directly sidesteps both
        problems: it's populated live by udev from the actual attached
        block devices, is unaffected by whatever the root filesystem is
        doing (overlay or not), and doesn't depend on standby_path's
        mount point being nested at any particular place."""
        return os.path.exists(f"/dev/disk/by-uuid/{self.usb_uuid}")

    def play(self, path: str):
        """Loads and plays a real video clip. Always issues a fresh
        'loadfile replace', even if it's the same file already playing --
        that's what makes pressing the same footswitch twice restart the
        song from the beginning (approved behavior).

        Queues standby right behind the clip (loadfile ... append), so
        that if the clip is left to play to its natural end, mpv advances
        to standby on its own, immediately -- with no gap where mpv would
        otherwise sit fully idle (no file loaded at all). That gap, even
        though brief, was long enough for mpv's own idle screen ("Drop
        files or URLs to play here") to flash on screen while waiting for
        our end-file handler to react and send a fresh loadfile."""
        self._mpv.send({"command": ["loadfile", path, "replace"]})
        self._mpv.send({"command": ["set_property", "loop-file", "no"]})
        self._mpv.send({"command": ["set_property", "mute", False]})
        self._mpv.send({"command": ["loadfile", self._resolved_standby, "append"]})
        self._current_standby_path = None

    def go_to_standby(self):
        """Immediate, highest-priority action -- returns to the looping
        standby video. Used for the abstract STOP action, automatically
        when a video clip finishes playing on its own, and whenever an
        audio-only track is selected (see AudioPlayer).

        A no-op if the correct standby (real or fallback, decided once at
        startup -- see _usb_device_is_present()) is already showing: the
        Core calls this defensively before every audio-only track (to
        make sure the video lane isn't mid-clip), and on every STOP --
        without this guard, each of those calls would reissue
        'loadfile ... replace' and visibly restart the loop from position
        0, even though nothing actually needed to change. This was caught
        by ear: the standby video was visibly jumping back to its start on
        every single footswitch press.

        The standby video is muted (mute=True), not audio-track-disabled:
        an earlier version used aid=no/aid=auto to fully disable/re-enable
        the audio track instead of muting it, reasoning that a
        muted-but-still-decoding stream would open a second simultaneous
        ALSA client on the shared `dmix` device (TESTING.md flags dmix as
        sensitive to more than one producer). In practice that toggle
        caused a different, worse click of its own: enabling/disabling a
        track forces mpv to tear down and rebuild its ALSA connection,
        audible every time a video clip started or ended. Muting instead
        keeps the stream open continuously -- no teardown, no click -- and
        dmix mixing two streams that share the exact same fixed format
        (see _FIXED_AUDIO_SAMPLE_RATE above) is precisely what it's
        designed to do, so this isn't expected to reintroduce the
        original crackling."""
        if self._current_standby_path == self._resolved_standby:
            return
        self._mpv.send({"command": ["loadfile", self._resolved_standby, "replace"]})
        self._mpv.send({"command": ["set_property", "loop-file", "inf"]})
        self._mpv.send({"command": ["set_property", "mute", True]})
        self._current_standby_path = self._resolved_standby

    def _handle_end_file(self, reason: str):
        """Reacts to mpv's raw end-file event for this lane. A reason of
        'eof' here can only mean the real clip queued by play() finished
        on its own -- and because that same call already queued standby
        right behind it, mpv has *already* started playing standby by the
        time this fires. So there's no loadfile to send: just fix up the
        properties that don't carry over from one playlist entry to the
        next (looping, volume), update our own bookkeeping, and let the
        Core know."""
        if reason != "eof" or self._current_standby_path is not None:
            return
        self._mpv.send({"command": ["set_property", "loop-file", "inf"]})
        self._mpv.send({"command": ["set_property", "mute", True]})
        self._current_standby_path = self._resolved_standby
        if self.on_clip_finished is not None:
            self.on_clip_finished()


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
            extra_args=[
                "--force-window=no",  # no video output at all on this lane
                "--vid=no",
                f"--audio-device={audio_device}",
                f"--audio-samplerate={_FIXED_AUDIO_SAMPLE_RATE}",
                "--audio-channels=stereo",
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
