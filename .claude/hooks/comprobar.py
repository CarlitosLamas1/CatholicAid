#!/usr/bin/env python3
"""Después de editar: comprueba que el archivo sigue siendo válido.

- .py: que Python lo entienda (sin ejecutarlo).
- .json (config, registros, biblia…): que sea JSON válido.
- .yml de .github/workflows: que se pueda leer (si hay PyYAML) y no tenga tabuladores.
Si algo falla, se lo dice a Claude (código 2) para que lo arregle en el momento.
"""
import json
import os
import sys


def main():
    datos = json.load(sys.stdin)
    entrada = datos.get("tool_input", {}) or {}
    ruta = entrada.get("file_path") or ""
    if not ruta or not os.path.isfile(ruta):
        return
    error = None
    if ruta.endswith(".py"):
        try:
            with open(ruta, encoding="utf-8") as f:
                compile(f.read(), ruta, "exec")
        except SyntaxError as e:
            error = f"error de Python en la línea {e.lineno}: {e.msg}"
    elif ruta.endswith(".json"):
        try:
            with open(ruta, encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            error = f"JSON no válido: {e}"
    elif ruta.endswith((".yml", ".yaml")):
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
        if "\t" in texto:
            error = "El YAML tiene tabuladores (GitHub no lo acepta)."
        else:
            try:
                import yaml
                yaml.safe_load(texto)
            except ImportError:
                pass
            except Exception as e:
                error = f"YAML no válido: {e}"
    if error:
        print(f"{os.path.basename(ruta)} ha quedado roto: {error}", file=sys.stderr)
        sys.exit(2)


try:
    main()
except SystemExit:
    raise
except Exception:
    sys.exit(0)
