# Prueba A/B del gancho (frase inicial)

Desde que se active (config `gancho_ab`), la frase clave del principio dura distinto según el día:

| Día del mes | Duración del gancho |
|---|---|
| par (2, 4, 6…) | 2,8 s |
| impar (1, 3, 5…) | 1,5 s |

Cada episodio lo anota en su registro: `"gancho_segundos"` en `episodios/AAAA-MM-DD.json` (y `-en.json`).

## Cómo compararlo en YouTube Studio (unos 10 minutos, tras 2–3 semanas)

1. YouTube Studio → **Contenido** → pestaña **Shorts**.
2. Abre cada Short → **Estadísticas** → **Interacción**. Apunta dos datos de los primeros 7 días:
   - **«Se quedaron viendo» / «Vistos (frente a deslizados)»**: el % de gente que no pasa de largo al principio.
     Es el dato que mide el gancho.
   - **Duración media vista** (o % medio visto).
3. Separa los vídeos en dos grupos por la fecha (par / impar) y calcula la media de cada grupo.
   Compara solo vídeos de días parecidos (mismo tipo de lectura y misma hora de publicación).
4. Con al menos 8–10 vídeos por grupo: si un grupo gana por más de 3–4 puntos en «se quedaron viendo» sin perder
   duración media, se fija esa duración (`gancho_segundos` en la config y se quita `gancho_ab`).
   Si la diferencia es menor, no es significativa: se deja 2,8 s.
