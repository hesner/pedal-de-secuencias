"""
MIDI Adapter for the M-VAVE (see section 3 of MASTER_SPECIFICATION.md).

Its only job is: find the controller's ALSA port and hand already-decoded
standard MIDI events (channel, program) upward. It doesn't translate
anything semantically -- under the approved strategy (the M-VAVE's
"Program Change A" mode) the hardware already sends standard Program
Change directly, so this Adapter is intentionally thin.

If the M-VAVE is replaced in the future by a controller that does need
real translation (for example, one that only sends Note On/Off and needs
converting to Program Change), that extra work goes here, never in the
Mapper or the Core.

Requires: python3-mido and python3-rtmidi (installed via apt on the Pi).
"""

import mido


class DeviceNotFoundError(RuntimeError):
    pass


class MVaveAdapter:
    def __init__(self, port_name_pattern: str = "SINCO"):
        """port_name_pattern: substring (case-insensitive) to look for among
        the available MIDI input ports. Defaults to "SINCO", which is the
        name the M-VAVE PD41 reports to ALSA (confirmed empirically, see
        MAVAVE_ANALYSIS.md -- the M-VAVE does NOT identify itself with the
        string "M-VAVE" at the USB/ALSA level).
        """
        self.port_name_pattern = port_name_pattern
        self._port = None

    def _find_port_name(self) -> str:
        available = mido.get_input_names()
        matches = [p for p in available if self.port_name_pattern.lower() in p.lower()]
        if not matches:
            raise DeviceNotFoundError(
                f"No MIDI input port containing '{self.port_name_pattern}' "
                f"was found. Available ports: {available!r}. "
                f"Is the controller connected via USB?"
            )
        return matches[0]

    def open(self) -> str:
        """Opens the port and leaves it ready to receive messages.
        Returns the exact name of the opened port (useful for logs)."""
        port_name = self._find_port_name()
        self._port = mido.open_input(port_name)
        return port_name

    def close(self):
        if self._port is not None:
            self._port.close()
            self._port = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def program_changes(self):
        """Infinite (blocking) generator: yields (channel, program) for
        every Program Change message received. Any other kind of MIDI
        message (Note On/Off, Control Change, etc.) is silently ignored --
        it isn't relevant to the approved strategy.

        NOTE: the Control Change the M-VAVE sends when using its E/F button
        combination to switch groups is deliberately ignored -- see the
        portability note in mapper.py.
        """
        if self._port is None:
            raise RuntimeError(
                "The adapter isn't open -- call open() first "
                "(or use it with 'with MVaveAdapter() as adapter:')"
            )
        for msg in self._port:
            if msg.type == "program_change":
                yield msg.channel, msg.program
