#!/usr/bin/env python3
"""
Script de prueba en vivo: conecta el Adapter del M-VAVE al Mapper e
imprime en pantalla la acción abstracta resultante de cada Program Change
recibido. Pensado para validar a mano (presionando footswitches reales)
antes de aprobar el paso 7 del flujo de trabajo (sección 6 de
MASTER_SPECIFICATION.md).

Requisito: el M-VAVE debe estar en modo "Program Change A" (seleccionado
desde la app del fabricante) -- este script no cambia el modo del
controlador, solo escucha.

Uso (en la Raspberry Pi):
    cd ~/pedal_src_test   # o donde esté el repo
    python3 src/live_test.py

Ctrl+C para salir.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from adapter import MVaveAdapter, DispositivoNoEncontrado  # noqa: E402
from mapper import Mapper, SelectTrack, Stop  # noqa: E402


def main():
    mapper = Mapper(tracks_per_group=4)

    try:
        with MVaveAdapter(port_name_pattern="SINCO") as adapter:
            print("Conectado. Esperando Program Change (Ctrl+C para salir)...", flush=True)
            print("Recuerda: el M-VAVE debe estar en modo 'Program Change A'.\n", flush=True)

            for channel, program in adapter.program_changes():
                accion = mapper.map_program_change(program)

                if isinstance(accion, Stop):
                    print(f"[canal {channel}] PC={program:3d}  ->  STOP", flush=True)
                elif isinstance(accion, SelectTrack):
                    print(
                        f"[canal {channel}] PC={program:3d}  ->  "
                        f"SelectTrack(setlist={accion.setlist}, track={accion.track})",
                        flush=True,
                    )
    except DispositivoNoEncontrado as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


if __name__ == "__main__":
    main()
