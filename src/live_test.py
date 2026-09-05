#!/usr/bin/env python3
"""
Live test script: connects the M-VAVE Adapter to the Mapper and prints
the resulting abstract action for every Program Change received. Meant
for hands-on validation (pressing real footswitches) before approving
step 7 of the workflow (section 6 of MASTER_SPECIFICATION.md).

Requirement: the M-VAVE must be in "Program Change A" mode (selected from
the manufacturer's app) -- this script doesn't change the controller's
mode, it only listens.

Usage (on the Raspberry Pi):
    cd ~/pedal_src_test   # or wherever the repo is
    python3 src/live_test.py

Ctrl+C to exit.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from adapter import MVaveAdapter, DeviceNotFoundError  # noqa: E402
from mapper import Mapper, SelectTrack, Stop  # noqa: E402


def main():
    mapper = Mapper(tracks_per_group=4)

    try:
        with MVaveAdapter(port_name_pattern="SINCO") as adapter:
            print("Connected. Waiting for Program Change (Ctrl+C to exit)...", flush=True)
            print("Remember: the M-VAVE must be in 'Program Change A' mode.\n", flush=True)

            for channel, program in adapter.program_changes():
                action = mapper.map_program_change(program)

                if isinstance(action, Stop):
                    print(f"[channel {channel}] PC={program:3d}  ->  STOP", flush=True)
                elif isinstance(action, SelectTrack):
                    print(
                        f"[channel {channel}] PC={program:3d}  ->  "
                        f"SelectTrack(setlist={action.setlist}, track={action.track})",
                        flush=True,
                    )
    except DeviceNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting.")


if __name__ == "__main__":
    main()
