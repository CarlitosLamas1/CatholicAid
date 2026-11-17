#!/usr/bin/env python3
"""Reloj: el workflow de main y el envoltorio de la rama «reloj» usan el mismo script de tirada (4 pasadas)."""
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class RelojTirada(unittest.TestCase):
    def test_script_existe_y_hace_cuatro_pasadas(self):
        s = (RAIZ / "proceso" / "reloj_tirada.sh").read_text(encoding="utf-8")
        self.assertIn("PASADAS=4", s)
        self.assertIn("schedule", s)               # el cron de respaldo hace una sola
        self.assertIn("proceso/reloj.py", s)
        self.assertEqual(subprocess.run(["bash", "-n", str(RAIZ / "proceso" / "reloj_tirada.sh")]).returncode, 0)

    def test_workflow_de_main_usa_el_script(self):
        y = (RAIZ / ".github" / "workflows" / "reloj.yml").read_text(encoding="utf-8")
        self.assertIn("proceso/reloj_tirada.sh", y)
        self.assertIn("branches: [reloj]", y)       # la marca horaria sigue siendo un push a esa rama


if __name__ == "__main__":
    unittest.main()
