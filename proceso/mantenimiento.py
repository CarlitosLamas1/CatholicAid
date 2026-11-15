#!/usr/bin/env python3
"""CatholicAid · Mantenimiento diario (workflow «Mantenimiento», lo lanza el Reloj de madrugada).

1. Borra las releases de vídeos de hace más de 2 días (tiktok-/en-/pt-AAAA-MM-DD): ya se publicaron o ya no sirven.
   El «Evangelio de la semana» usa entonces la copia de 30 días del run.
2. Archiva las imágenes del día con más de 60 días (biblioteca/dias/) en una release mensual «archivo-AAAA-MM»
   y las saca del repositorio, para que no crezca sin fin.
3. Busca en los tres canales de YouTube vídeos que no estén en ningún registro (subidas duplicadas).
4. Los domingos, los números de la semana (proceso/estadisticas.py -> estado/estadisticas.json).
Deja el resultado en estado/mantenimiento.json (lo lee el parte diario). Ningún paso bloquea a los demás.
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
RELEASE_DIA = re.compile(r"^(tiktok|en|pt)-(\d{4}-\d{2}-\d{2})$")
IMAGEN_DIA = re.compile(r"^(\d{4}-\d{2}-\d{2})_e\d+\.(jpg|png)$")
DIAS_RELEASE = 2
DIAS_IMAGEN = 60


def log(*a):
    print(*a, flush=True)


def sh(*args, check=True):
    return subprocess.run(list(map(str, args)), check=check, capture_output=True, text=True)


def releases_viejas(etiquetas, hoy, dias=DIAS_RELEASE):
    """De una lista de etiquetas, las de vídeos diarios de hace más de «dias» días."""
    limite = hoy - dt.timedelta(days=dias)
    return [t for t in etiquetas if (m := RELEASE_DIA.match(t)) and dt.date.fromisoformat(m.group(2)) < limite]


def imagenes_viejas(nombres, hoy, dias=DIAS_IMAGEN):
    """De una lista de nombres de biblioteca/dias/, los de hace más de «dias» días, agrupados por mes."""
    limite = hoy - dt.timedelta(days=dias)
    meses = {}
    for n in sorted(nombres):
        m = IMAGEN_DIA.match(n)
        if m and dt.date.fromisoformat(m.group(1)) < limite:
            meses.setdefault(m.group(1)[:7], []).append(n)
    return meses


def limpiar_releases(hoy):
    d = json.loads(sh("gh", "release", "list", "--limit", "200", "--json", "tagName").stdout)
    borradas = []
    for t in releases_viejas([x["tagName"] for x in d], hoy):
        if sh("gh", "release", "delete", t, "--yes", "--cleanup-tag", check=False).returncode == 0:
            borradas.append(t)
    log(f"Releases borradas: {', '.join(borradas) or 'ninguna'}")
    return borradas


def archivar_imagenes(hoy):
    carpeta = RAIZ / "biblioteca" / "dias"
    archivadas = 0
    for mes, nombres in imagenes_viejas([p.name for p in carpeta.iterdir()], hoy).items():
        etiqueta = f"archivo-{mes}"
        if sh("gh", "release", "view", etiqueta, check=False).returncode != 0:
            sh("gh", "release", "create", etiqueta, "--title", f"Archivo de imágenes {mes}",
               "--notes", "Imágenes del día de ese mes, fuera del repositorio para que no crezca.", "--latest=false")
        rutas = [carpeta / n for n in nombres]
        if sh("gh", "release", "upload", etiqueta, *rutas, "--clobber", check=False).returncode != 0:
            log(f"No se pudo archivar {mes}; se deja para mañana.")
            continue
        subidos = {a["name"] for a in json.loads(sh("gh", "release", "view", etiqueta, "--json", "assets").stdout)["assets"]}
        for r in rutas:  # solo se quita del repositorio lo que consta subido
            if r.name in subidos:
                r.unlink()
                archivadas += 1
    log(f"Imágenes archivadas: {archivadas}")
    return archivadas


def buscar_sobrantes():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import duplicados
    ids, sobran = duplicados.conocidos(), []
    for idioma in ("es", "en", "pt"):
        try:
            sobran += [{"idioma": idioma, **v} for v in duplicados.sobrantes(idioma, ids)]
        except Exception as ex:
            log(f"Duplicados [{idioma}]: no se pudo comprobar ({ex})")
    log(f"Vídeos sin registro: {len(sobran)}")
    return sobran


def main():
    hoy = dt.datetime.now(MADRID).date()
    estado = {"fecha": str(hoy)}
    for clave, paso in (("releases_borradas", lambda: limpiar_releases(hoy)),
                        ("imagenes_archivadas", lambda: archivar_imagenes(hoy)),
                        ("sobrantes", buscar_sobrantes)):
        try:
            estado[clave] = paso()
        except Exception as ex:
            log(f"{clave}: falló ({ex})")
            estado.setdefault("errores", []).append(f"{clave}: {str(ex)[:150]}")
    if hoy.isoweekday() == 7 or "--estadisticas" in sys.argv:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import estadisticas
            estadisticas.main()
        except Exception as ex:
            log(f"estadísticas: falló ({ex})")
            estado.setdefault("errores", []).append(f"estadisticas: {str(ex)[:150]}")
    (RAIZ / "estado" / "mantenimiento.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")


if __name__ == "__main__":
    main()
