"""
MIDI Mapper para la estrategia aprobada (ver MAVAVE_ANALYSIS.md, sección
"4.2-4.4 Comparación de alternativas y recomendación").

Traduce eventos MIDI estándar (Program Change) a acciones abstractas del
Core (SelectTrack, Stop). No conoce nada de USB, ALSA, ni del controlador
físico específicamente — solo recibe (canal, programa) ya decodificados por
el Adapter.

Principio de portabilidad (acordado explícitamente con el usuario): esta
lógica se basa ÚNICAMENTE en el valor final de Program Change. Nunca debe
leer ni depender de ningún Control Change que un controlador mande
internamente para sus propias combinaciones de botones (p. ej. cambio de
grupo/banco) — ese CC es un detalle propio de cómo cada fabricante
señaliza sus propios combos, no debe cruzar a esta capa. Así, cualquier
controlador MIDI que mande Program Change 0-127 (por el medio que sea)
funciona con este mismo Mapper sin cambios, sin depender de ninguna función
propietaria.

Fórmula: PC = (grupo - 1) × tracks_per_group + offset, offset =
0..(tracks_per_group - 1) según el footswitch (A=0, B=1, C=2, D=3).

Decisión de STOP (aprobada): el último footswitch de cada grupo (offset =
tracks_per_group - 1) siempre se interpreta como STOP, sin importar el
grupo/setlist activo — así STOP queda disponible al instante desde
cualquier punto del show, sin sacrificar un modo o footswitch fuera del
esquema normal de navegación. Costo aceptado: quedan (tracks_per_group - 1)
tracks reales por setlist.

Nota de diseño (marcada explícitamente para revisión del usuario): el
diagrama de la sección 3 de MASTER_SPECIFICATION.md lista SELECT_SETLIST y
SELECT_TRACK como acciones separadas. Esta implementación las combina en
una sola acción SelectTrack(setlist, track), porque el Mapper nunca recibe
un evento MIDI que signifique "solo cambió el setlist, sin track todavía"
(el controlador no manda Program Change hasta que se presiona un
footswitch real) — el Mapper se mantiene sin estado (stateless). Si el
Core necesita reaccionar de forma distinta cuando cambia el setlist vs.
cuando solo cambia el track dentro del mismo setlist, esa comparación de
"¿cambió el setlist respecto al anterior?" le corresponde al Core, que sí
mantiene estado de sesión — no al Mapper. Pendiente de que el usuario
confirme si esta simplificación es aceptable o si prefiere que el Mapper
emita las dos acciones por separado.

Nota de hardware: esta fórmula y la lógica completa fueron diseñadas y
validadas empíricamente contra un controlador MIDI real, un M-VAVE PD41
(ver MAVAVE_ANALYSIS.md y la validación en vivo en TESTING.md); funcionan
igual con cualquier otro controlador MIDI que envíe Program Change 0-127 en
este mismo formato, sin cambios de código.
"""

from .actions import SelectTrack, Stop


class Mapper:
    def __init__(self, tracks_per_group: int = 4):
        if tracks_per_group < 2:
            raise ValueError(
                "tracks_per_group debe ser >= 2 (se necesita al menos "
                "1 track real + 1 reservado para STOP)"
            )
        self.tracks_per_group = tracks_per_group
        self._stop_offset = tracks_per_group - 1

    def map_program_change(self, program: int):
        """Traduce un número de Program Change (0-127) a una acción abstracta.

        Devuelve una instancia de Stop o SelectTrack. No devuelve None:
        todo Program Change válido (0-127) produce una acción.
        """
        if not (0 <= program <= 127):
            raise ValueError(f"Program Change fuera de rango: {program}")

        group_index, offset = divmod(program, self.tracks_per_group)

        if offset == self._stop_offset:
            return Stop()

        setlist = group_index + 1
        track = offset + 1
        return SelectTrack(setlist=setlist, track=track)
