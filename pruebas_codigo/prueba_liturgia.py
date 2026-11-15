#!/usr/bin/env python3
"""Calendario litúrgico: fechas conocidas de 2026 y 2027."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import liturgia as lt  # noqa: E402

D = dt.date


class Liturgia(unittest.TestCase):
    def test_pascua_y_adviento(self):
        self.assertEqual(lt.pascua(2026), D(2026, 4, 5))
        self.assertEqual(lt.pascua(2027), D(2027, 3, 28))
        self.assertEqual(lt.inicio_adviento(2026), D(2026, 11, 29))
        self.assertEqual(lt.inicio_adviento(2027), D(2027, 11, 28))

    def test_tiempos(self):
        casos = {D(2026, 11, 28): "ordinario", D(2026, 11, 29): "adviento", D(2026, 12, 24): "adviento",
                 D(2026, 12, 25): "navidad", D(2027, 1, 10): "navidad", D(2027, 1, 11): "ordinario",
                 D(2027, 2, 10): "cuaresma", D(2027, 3, 28): "pascua", D(2027, 5, 16): "pascua",
                 D(2027, 5, 17): "ordinario"}
        for fecha, tiempo in casos.items():
            self.assertEqual(lt.tiempo_liturgico(fecha), tiempo, fecha)

    def test_domingos(self):
        casos = {D(2026, 11, 15): "Domingo XXXIII del Tiempo Ordinario",
                 D(2026, 11, 22): "Jesucristo, Rey del Universo",
                 D(2026, 11, 29): "Domingo I de Adviento",
                 D(2026, 12, 20): "Domingo IV de Adviento",
                 D(2026, 12, 27): "Sagrada Familia: Jesús, María y José",
                 D(2027, 1, 10): "Bautismo del Señor",
                 D(2027, 1, 17): "Domingo II del Tiempo Ordinario",
                 D(2027, 2, 7): "Domingo V del Tiempo Ordinario",
                 D(2027, 2, 14): "Domingo I de Cuaresma",
                 D(2027, 3, 21): "Domingo de Ramos en la Pasión del Señor",
                 D(2027, 4, 4): "Domingo II de Pascua",
                 D(2027, 5, 16): "Domingo de Pentecostés",
                 D(2027, 5, 23): "Santísima Trinidad",
                 D(2027, 6, 6): "Domingo X del Tiempo Ordinario"}
        for fecha, nombre in casos.items():
            self.assertEqual(lt.dia_liturgico(fecha), nombre, fecha)

    def test_otros_idiomas(self):
        self.assertEqual(lt.dia_liturgico(D(2026, 11, 15), "en"), "33rd Sunday in Ordinary Time")
        self.assertEqual(lt.dia_liturgico(D(2026, 11, 29), "en"), "First Sunday of Advent")
        self.assertEqual(lt.dia_liturgico(D(2026, 11, 15), "pt"), "33º Domingo do Tempo Comum")
        self.assertEqual(lt.dia_liturgico(D(2027, 1, 24), "en"), "3rd Sunday in Ordinary Time")

    def test_fiestas_y_dias_corrientes(self):
        self.assertEqual(lt.dia_liturgico(D(2026, 12, 8)), "Inmaculada Concepción de la Virgen María")
        self.assertEqual(lt.dia_liturgico(D(2026, 12, 25)), "Natividad del Señor")
        self.assertEqual(lt.dia_liturgico(D(2027, 2, 10)), "Miércoles de Ceniza")
        self.assertEqual(lt.dia_liturgico(D(2026, 11, 17)), "")  # martes corriente

    def test_ante_la_duda_calla(self):
        self.assertEqual(lt.dia_liturgico(D(2027, 5, 6)), "")   # Ascensión (jueves) según el país
        self.assertEqual(lt.dia_liturgico(D(2027, 5, 9)), "")   # Ascensión (domingo) o VII de Pascua
        self.assertEqual(lt.dia_liturgico(D(2027, 5, 30)), "")  # Corpus (domingo) según el país
        self.assertEqual(lt.dia_liturgico(D(2027, 3, 25)), "Jueves Santo")  # la Anunciación se traslada
        self.assertEqual(lt.dia_liturgico(D(2026, 11, 1)), "")  # Todos los Santos en domingo: no se arriesga

    def test_adviento(self):
        self.assertEqual(lt.dias_para_navidad(D(2026, 11, 29)), 26)
        self.assertIsNone(lt.dias_para_navidad(D(2026, 11, 28)))
        self.assertEqual(lt.color_tiempo(D(2026, 12, 1)), "C9A6F0")
        self.assertEqual(lt.color_tiempo(D(2026, 11, 20)), "F5C542")
        self.assertEqual(lt.etiqueta_tiempo(D(2026, 12, 1), "pt"), "Advento")
        self.assertEqual(lt.etiqueta_tiempo(D(2026, 11, 20)), "")


if __name__ == "__main__":
    unittest.main()
