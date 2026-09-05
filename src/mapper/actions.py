"""
Acciones abstractas del Core (sección 3 de MASTER_SPECIFICATION.md).

Estas clases son lo único que el Mapper le entrega al Core. El Core nunca
debe ver un número de Program Change, un canal MIDI, ni ningún concepto del
controlador físico (grupos, footswitches A-D, etc.) — solo estas acciones.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectTrack:
    """Seleccionar una secuencia (track) dentro de un setlist.

    setlist y track son 1-indexados (más natural para humanos / logs).
    """
    setlist: int
    track: int


@dataclass(frozen=True)
class Stop:
    """Acción global de máxima prioridad: detener todo inmediatamente."""
    pass
