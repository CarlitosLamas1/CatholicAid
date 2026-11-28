#!/usr/bin/env python3
"""El inglés nunca empieza «At that time, “…» sin decir quién habla (28/11/2026: Lucas 21,34-36 y Marcos 13,33-37)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import evangelio as ev  # noqa: E402


class InicioIngles(unittest.TestCase):
    def test_toma_el_inicio_del_espanol(self):
        self.assertEqual(ev.INICIOS_EN["En aquel tiempo, dijo Jesús a sus discípulos:"],
                         "At that time, Jesus said to his disciples:")

    def test_lecturas_que_empiezan_hablando(self):
        for cita in ("Lucas 21, 34-36", "Marcos 13, 33-37"):
            try:
                texto, _ = ev.texto_web(cita)
            except Exception as e:  # sin red no hay World English Bible descargada
                self.skipTest(f"sin texto inglés: {e}")
            self.assertTrue(texto.startswith("At that time, Jesus said to his disciples: “"), texto[:80])

    def test_nombra_a_jesus(self):
        try:
            texto, _ = ev.texto_web("Mateo 4, 18-22")
        except Exception as e:
            self.skipTest(f"sin texto inglés: {e}")
        self.assertIn("Jesus saw two brothers", texto)


if __name__ == "__main__":
    unittest.main()
