#!/usr/bin/env python3
"""Guardado seguro (proceso/guardar.py): dos procesos escriben a la vez en el mismo registro y no se pisan."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARDAR = Path(__file__).resolve().parent.parent / "proceso" / "guardar.py"


def git(carpeta, *args):
    return subprocess.run(["git", *args], cwd=carpeta, capture_output=True, text=True, check=True).stdout


def clonar(origen, destino):
    subprocess.run(["git", "clone", "-q", str(origen), str(destino)], check=True)
    git(destino, "config", "user.name", "prueba")
    git(destino, "config", "user.email", "prueba@example.invalid")
    return destino


def guardar(carpeta, mensaje, *rutas):
    return subprocess.run([sys.executable, str(GUARDAR), mensaje, *rutas], cwd=carpeta, capture_output=True, text=True)


class Guardar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origen = self.tmp / "origen.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origen)], check=True)
        a = clonar(self.origen, self.tmp / "inicio")
        (a / "episodios").mkdir()
        (a / "episodios" / "dia.json").write_text(json.dumps({"fecha": "2026-01-01", "revision": "pendiente"}))
        git(a, "add", "-A")
        git(a, "commit", "-q", "-m", "inicio")
        git(a, "push", "-q", "origin", "HEAD:main")

    def registro(self):
        c = clonar(self.origen, self.tmp / f"ver{len(list(self.tmp.iterdir()))}")
        return json.loads((c / "episodios" / "dia.json").read_text())

    def test_dos_escritores_no_se_pisan(self):
        a = clonar(self.origen, self.tmp / "a")
        b = clonar(self.origen, self.tmp / "b")
        for carpeta, clave in ((a, "tiktok"), (b, "instagram")):
            reg = json.loads((carpeta / "episodios" / "dia.json").read_text())
            reg[clave] = {"id": clave}
            (carpeta / "episodios" / "dia.json").write_text(json.dumps(reg))
        self.assertEqual(guardar(a, "a", "episodios/").returncode, 0)
        self.assertEqual(guardar(b, "b", "episodios/").returncode, 0)  # antes: «rejected (fetch first)»
        reg = self.registro()
        self.assertEqual(reg["tiktok"], {"id": "tiktok"})
        self.assertEqual(reg["instagram"], {"id": "instagram"})
        self.assertEqual(reg["revision"], "pendiente")

    def test_archivo_nuevo_y_borrado(self):
        a = clonar(self.origen, self.tmp / "a")
        b = clonar(self.origen, self.tmp / "b")
        (a / "episodios" / "otro.json").write_text(json.dumps({"x": 1}))
        self.assertEqual(guardar(a, "nuevo", "episodios/").returncode, 0)
        reg = json.loads((b / "episodios" / "dia.json").read_text())
        del reg["revision"]
        (b / "episodios" / "dia.json").write_text(json.dumps(reg))
        self.assertEqual(guardar(b, "sin clave", "episodios/").returncode, 0)
        c = clonar(self.origen, self.tmp / "c")
        self.assertTrue((c / "episodios" / "otro.json").exists())
        self.assertNotIn("revision", json.loads((c / "episodios" / "dia.json").read_text()))

    def test_nada_que_guardar(self):
        a = clonar(self.origen, self.tmp / "a")
        r = guardar(a, "nada", "episodios/", "no-existe/")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nada que guardar", r.stdout)


if __name__ == "__main__":
    unittest.main()
