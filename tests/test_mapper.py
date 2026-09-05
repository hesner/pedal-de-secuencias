"""
Pruebas del Mapper. No requieren hardware — validan la lógica pura contra
los datos reales capturados del M-VAVE en MAVAVE_ANALYSIS.md (sección
"Validación empírica", modo Program Change A) y contra la decisión de STOP
aprobada.

Correr con: python -m pytest tests/test_mapper.py -v
(o, si no hay pytest instalado: python -m unittest tests/test_mapper.py)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mapper import Mapper, SelectTrack, Stop  # noqa: E402


class TestMapperGrupo1(unittest.TestCase):
    """Corresponde a la primera tanda de pruebas físicas: A,B,C,D en el
    grupo 1 (recién seleccionado el modo Program Change A) mandaron
    Program Change 0, 1, 2, 3 respectivamente."""

    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_0_es_track_A_del_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(0), SelectTrack(setlist=1, track=1)
        )

    def test_pc_1_es_track_B_del_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(1), SelectTrack(setlist=1, track=2)
        )

    def test_pc_2_es_track_C_del_setlist_1(self):
        self.assertEqual(
            self.mapper.map_program_change(2), SelectTrack(setlist=1, track=3)
        )

    def test_pc_3_footswitch_D_es_stop_no_track(self):
        # Medido: D es el footswitch reservado para STOP (offset 3 = ultimo
        # del grupo), no un track real.
        self.assertEqual(self.mapper.map_program_change(3), Stop())


class TestMapperGrupo7(unittest.TestCase):
    """Corresponde a la segunda tanda: tras cambiar de grupo con E, la
    pantalla del M-VAVE mostró "7A".."7d", y A,B,C,D mandaron Program
    Change 24, 25, 26, 27."""

    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_24_es_track_A_del_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(24), SelectTrack(setlist=7, track=1)
        )

    def test_pc_25_es_track_B_del_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(25), SelectTrack(setlist=7, track=2)
        )

    def test_pc_26_es_track_C_del_setlist_7(self):
        self.assertEqual(
            self.mapper.map_program_change(26), SelectTrack(setlist=7, track=3)
        )

    def test_pc_27_footswitch_D_es_stop(self):
        self.assertEqual(self.mapper.map_program_change(27), Stop())


class TestMapperCasosLimite(unittest.TestCase):
    def setUp(self):
        self.mapper = Mapper(tracks_per_group=4)

    def test_pc_127_ultimo_valor_valido_es_stop(self):
        # 127 = grupo 32 (index 31), offset 3 -> STOP
        self.assertEqual(self.mapper.map_program_change(127), Stop())

    def test_pc_126_ultimo_track_real_del_ultimo_grupo(self):
        self.assertEqual(
            self.mapper.map_program_change(126), SelectTrack(setlist=32, track=3)
        )

    def test_program_negativo_rechazado(self):
        with self.assertRaises(ValueError):
            self.mapper.map_program_change(-1)

    def test_program_mayor_a_127_rechazado(self):
        with self.assertRaises(ValueError):
            self.mapper.map_program_change(128)

    def test_tracks_per_group_configurable(self):
        # Si el día de mañana se usa un controlador con 8 botones por
        # grupo en vez de 4, solo cambia este parámetro -- el Core y las
        # acciones abstractas no cambian.
        mapper8 = Mapper(tracks_per_group=8)
        self.assertEqual(
            mapper8.map_program_change(0), SelectTrack(setlist=1, track=1)
        )
        self.assertEqual(
            mapper8.map_program_change(6), SelectTrack(setlist=1, track=7)
        )
        self.assertEqual(mapper8.map_program_change(7), Stop())  # offset 7 = ultimo

    def test_tracks_per_group_minimo_invalido(self):
        with self.assertRaises(ValueError):
            Mapper(tracks_per_group=1)


if __name__ == "__main__":
    unittest.main()
