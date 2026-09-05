#!/usr/bin/env python3
"""
Hands-on smoke test for the Player/mpv integration: starts the persistent
mpv process, plays a real track, and confirms -- via mpv's own IPC state,
not just visually -- that the standby -> track -> standby transitions
actually happen. Complements the unit tests (which never touch a real
mpv process).

Needs two short video files to already exist. To generate throwaway ones
for this test (not part of the project's media library):

    ffmpeg -f lavfi -i color=c=blue:s=320x240:d=5 \\
           -f lavfi -i sine=frequency=440:duration=5 \\
           -c:v libx264 -c:a aac -shortest /tmp/standby.mp4
    ffmpeg -f lavfi -i color=c=red:s=320x240:d=5 \\
           -f lavfi -i sine=frequency=880:duration=5 \\
           -c:v libx264 -c:a aac -shortest /tmp/test_track.mp4

Usage (on the Raspberry Pi):
    python3 src/core_smoke_test.py --standby /tmp/standby.mp4 --track /tmp/test_track.mp4
"""

import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core import Player  # noqa: E402


def query_path(sock: socket.socket) -> str:
    """Sends a get_property "path" request over an already-connected IPC
    socket and returns mpv's reported current file path."""
    request = json.dumps({"command": ["get_property", "path"]}) + "\n"
    sock.sendall(request.encode("utf-8"))
    sock.settimeout(3.0)
    buffer = b""
    while True:
        buffer += sock.recv(4096)
        for line in buffer.split(b"\n"):
            if not line.strip():
                continue
            message = json.loads(line)
            if "error" in message and "data" in message:
                return message["data"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standby", required=True)
    parser.add_argument("--track", required=True)
    args = parser.parse_args()

    player = Player(standby_path=args.standby, socket_path="/tmp/pedal-smoke-test.sock")
    player.start()
    time.sleep(1)

    query_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    query_sock.connect(player.socket_path)

    current = query_path(query_sock)
    assert current == args.standby, f"expected standby, got {current!r}"
    print(f"OK: starts on standby ({current})")

    player.play(args.track)
    time.sleep(1)
    current = query_path(query_sock)
    assert current == args.track, f"expected track, got {current!r}"
    print(f"OK: play() switches to the requested track ({current})")

    player.go_to_standby()
    time.sleep(1)
    current = query_path(query_sock)
    assert current == args.standby, f"expected standby again, got {current!r}"
    print(f"OK: go_to_standby() returns to standby ({current})")

    player.play(args.track)
    time.sleep(0.5)
    player.play(args.track)
    time.sleep(1)
    current = query_path(query_sock)
    assert current == args.track, f"expected track after repeat press, got {current!r}"
    print("OK: pressing the same track twice keeps playing it (restart behavior)")

    query_sock.close()
    player.stop()
    print("\nAll smoke test checks passed.")


if __name__ == "__main__":
    main()
