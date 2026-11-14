#!/usr/bin/env python3
"""Antes de editar: protege el texto del Evangelio y los secretos (solo en el Mac de Carlos).

- Originales (Torres Amat, WEB, Figueiredo) y secretos/: bloqueado.
- Textos revisados (biblia/revisada, biblia/*/revisada): pide confirmación a Carlos.
Nunca falla: ante cualquier error, deja pasar.
"""
import json
import os
import re
import sys

BLOQUEADO = "bloqueado"
PREGUNTAR = "preguntar"


def clase(ruta):
    r = ruta.replace("\\", "/")
    if re.search(r"(^|/)secretos/", r):
        return BLOQUEADO
    if re.search(r"(^|/)biblia/(revisada|[^/]+/revisada)/", r):
        return PREGUNTAR
    if re.search(r"(^|/)biblia/(torres-amat|web|figueiredo)/", r):
        return BLOQUEADO
    return None


def responder(decision, motivo):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": motivo,
    }}, ensure_ascii=False))
    sys.exit(0)


def main():
    datos = json.load(sys.stdin)
    herramienta = datos.get("tool_name", "")
    entrada = datos.get("tool_input", {}) or {}
    clases = []
    if herramienta in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        ruta = entrada.get("file_path") or entrada.get("notebook_path") or ""
        clases.append(clase(os.path.relpath(ruta, os.environ.get("CLAUDE_PROJECT_DIR", "."))
                           if os.path.isabs(ruta) else ruta))
    elif herramienta == "Bash":
        orden = entrada.get("command", "")
        escribe = re.search(r"(>|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\btee\b|\btruncate\b|"
                            r"git\s+(checkout|restore)\b|open\(.*['\"][wa])", orden)
        if escribe:
            for m in re.finditer(r"[\w./-]*(secretos|biblia)/[\w./-]*", orden):
                clases.append(clase(m.group(0)))
    if BLOQUEADO in clases:
        responder("deny", "Protegido: el texto original del Evangelio y los secretos no se tocan "
                          "(CLAUDE.md: «Nunca cambies el texto del Evangelio»).")
    if PREGUNTAR in clases:
        responder("ask", "Vas a cambiar un texto revisado del Evangelio. ¿Lo apruebas?")


try:
    main()
except SystemExit:
    raise
except Exception:
    sys.exit(0)
