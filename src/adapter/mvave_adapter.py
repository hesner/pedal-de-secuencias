"""
MIDI Adapter para el M-VAVE (ver sección 3 de MASTER_SPECIFICATION.md).

Su único trabajo es: encontrar el puerto ALSA del controlador y entregar
eventos MIDI estándar ya decodidos (canal, programa) hacia arriba. No
traduce nada semánticamente -- en la estrategia aprobada (modo "Program
Change A" del M-VAVE) el hardware ya manda Program Change estándar
directamente, así que este Adapter es intencionalmente delgado.

Si en el futuro se reemplaza el M-VAVE por un controlador que sí necesite
traducción real (por ejemplo, uno que solo mande Note On/Off y haya que
convertir a Program Change), ese trabajo adicional va aquí, nunca en el
Mapper ni en el Core.

Requiere: python3-mido y python3-rtmidi (instalados vía apt en la Pi).
"""

import mido


class DispositivoNoEncontrado(RuntimeError):
    pass


class MVaveAdapter:
    def __init__(self, port_name_pattern: str = "SINCO"):
        """port_name_pattern: subcadena (sin importar mayúsculas/minúsculas)
        a buscar entre los puertos MIDI de entrada disponibles. Por defecto
        busca "SINCO", que es el nombre que reporta el M-VAVE modelo PD41
        ante ALSA (confirmado empíricamente, ver MAVAVE_ANALYSIS.md -- el
        M-VAVE NO se identifica con la cadena "M-VAVE" a nivel USB/ALSA).
        """
        self.port_name_pattern = port_name_pattern
        self._port = None

    def _find_port_name(self) -> str:
        available = mido.get_input_names()
        matches = [p for p in available if self.port_name_pattern.lower() in p.lower()]
        if not matches:
            raise DispositivoNoEncontrado(
                f"No se encontró ningún puerto MIDI de entrada que contenga "
                f"'{self.port_name_pattern}'. Puertos disponibles: {available!r}. "
                f"¿Está el controlador conectado por USB?"
            )
        return matches[0]

    def open(self) -> str:
        """Abre el puerto y lo deja listo para recibir mensajes.
        Devuelve el nombre exacto del puerto abierto (útil para logs)."""
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
        """Generador infinito (bloqueante): produce (channel, program) por
        cada mensaje Program Change recibido. Cualquier otro tipo de
        mensaje MIDI (Note On/Off, Control Change, etc.) se ignora en
        silencio -- no es relevante para la estrategia aprobada.

        NOTA: se ignora deliberadamente el Control Change que el M-VAVE
        manda al usar su combinación de botones E/F para cambiar de grupo
        -- ver la nota de portabilidad en mapper.py.
        """
        if self._port is None:
            raise RuntimeError(
                "El adapter no está abierto -- llama a open() primero "
                "(o úsalo con 'with MVaveAdapter() as adapter:')"
            )
        for msg in self._port:
            if msg.type == "program_change":
                yield msg.channel, msg.program
