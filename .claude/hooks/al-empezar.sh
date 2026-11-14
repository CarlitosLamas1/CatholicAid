#!/bin/bash
# Al empezar una conversación: trae lo último de GitHub (los robots lo actualizan cada hora).
# Nunca bloquea: si no puede (sin red, cambios locales), sigue igual.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
if out=$(GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=15 GIT_TERMINAL_PROMPT=0 git pull --ff-only -q 2>&1); then
  echo "Repositorio al día ($(git log -1 --format='%h %s' | cut -c1-80))."
else
  echo "Aviso: no se pudo traer lo último de GitHub ($(echo "$out" | tail -1 | cut -c1-120)). Haz git pull antes de fiarte de los registros."
fi
exit 0
