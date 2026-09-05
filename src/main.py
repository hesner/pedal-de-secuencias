#!/usr/bin/env python3
"""
Real runtime entry point: wires the MIDI Adapter to the Mapper and the
Mapper to the Core, so every controller action actually drives audio/video
playback -- unlike live_test.py, which only prints what would happen.

Usage (on the Raspberry Pi):
    python3 src/main.py --usb-root /media/usb --standby /media/usb/standby.mp4

Ctrl+C to exit.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from adapter import MVaveAdapter, DeviceNotFoundError  # noqa: E402
from mapper import Mapper  # noqa: E402
from core import Library, Player, AudioPlayer, Core  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--usb-root",
        required=True,
        help="Path where the library USB drive is mounted (contains active_show.txt)",
    )
    parser.add_argument(
        "--standby",
        required=True,
        help="Path to the standby video (looped when nothing is playing)",
    )
    parser.add_argument(
        "--log-file",
        default=os.path.expanduser("~/pedal-core.log"),
        help="Where to write the Core's log (default: ~/pedal-core.log)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(args.log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("main")

    mapper = Mapper(tracks_per_group=4)
    library = Library(usb_root=args.usb_root)
    player = Player(standby_path=args.standby)
    audio_player = AudioPlayer()
    core = Core(library=library, player=player, audio_player=audio_player)
    core.start()

    try:
        with MVaveAdapter(port_name_pattern="SINCO") as adapter:
            logger.info("Connected to the controller. Listening for actions...")
            for channel, program in adapter.program_changes():
                action = mapper.map_program_change(program)
                logger.info("[channel %d] PC=%d -> %r", channel, program, action)
                core.handle_action(action)
    except DeviceNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Exiting.")
    finally:
        core.stop()


if __name__ == "__main__":
    main()
