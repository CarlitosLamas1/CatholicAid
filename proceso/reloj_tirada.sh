#!/usr/bin/env bash
# Una tirada del Reloj: 4 pasadas cada 10 minutos (una sola si la arranca el cron de respaldo).
# Vive aquí, en main, para que la rama «reloj» (cuyo workflow es el que arranca la marca horaria de la rutina) no
# tenga copia propia de la lógica: el 17/11/2026 se vio que esa rama llevaba un reloj.yml antiguo de UNA pasada por hora
# (no las 4 documentadas) y el inglés y el portugués perdieron una ventana por llegar 15 s antes del OK del español.
# Uso: bash proceso/reloj_tirada.sh <evento de GitHub>
EVENTO="${1:-push}"
PASADAS=4
[ "$EVENTO" = "schedule" ] && PASADAS=1
for N in $(seq 1 $PASADAS); do
  git fetch -q origin main && git reset -q --hard origin/main || true
  echo "::group::Pasada $N de $PASADAS · $(TZ=Europe/Madrid date '+%d/%m %H:%M')"
  timeout 300 python3 proceso/reloj.py || echo "La pasada falló; sigo con la siguiente."
  echo "::endgroup::"
  [ "$N" -lt "$PASADAS" ] && sleep 600
done
exit 0
