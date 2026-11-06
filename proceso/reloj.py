#!/usr/bin/env python3
"""CatholicAid · Reloj.

Los horarios de GitHub (cron) pueden llegar horas tarde o no llegar. Este script se ejecuta cada hora
(«Reloj», lo despierta la rutina del revisor en la nube, que sí es puntual) y lanza lo que falte:
1. Vídeo de mañana (16:00–23:59 Madrid): si no hay registro diario hecho, o el último intento falló o fue rechazado.
2. «Publicar revisado»: si hay veredicto del revisor que aún no se ha aplicado.
3. TikTok (desde hora_publicacion de config, durante 12 h): si el vídeo de hoy tiene el OK y sigue preparado sin publicar.
4. «Comentarios» cada hora (responde como mucho uno, con ritmo humano).
Nunca duplica: no lanza nada que esté en marcha o se haya lanzado hace poco. Necesita GH_TOKEN.
"""
import datetime as dt
import json
import subprocess
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def log(*a):
    print(*a, flush=True)


def sh(*args, check=True):
    return subprocess.run(list(args), check=check, capture_output=True, text=True).stdout


def leer(ruta):
    try:
        return json.loads(sh("git", "show", f"origin/main:{ruta}"))
    except Exception:
        return {}


def reciente(runs, nombre, minutos):
    ahora = dt.datetime.now(dt.timezone.utc)
    for r in runs:
        if r["workflowName"] != nombre:
            continue
        if r["status"] != "completed":
            return True
        if ahora - dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) < dt.timedelta(minutes=minutos):
            return True
    return False


def lanzar(archivo, **campos):
    args = ["gh", "workflow", "run", archivo, "--ref", "main"]
    for k, v in campos.items():
        args += ["-f", f"{k}={v}"]
    sh(*args)
    log(f"→ Lanzado {archivo} {campos}")


def main():
    sh("git", "fetch", "-q", "origin", "main")
    runs = json.loads(sh("gh", "run", "list", "-L", "60", "--json", "workflowName,status,createdAt"))
    ahora = dt.datetime.now(MADRID)
    hoy, manana = ahora.date(), ahora.date() + dt.timedelta(days=1)
    log(f"Reloj: {ahora:%Y-%m-%d %H:%M} (Madrid)")
    try:
        comentarios(runs)
    except Exception as e:  # nunca impide lo demás
        log(f"Comentarios: no se pudo lanzar ({e})")

    # 1. Vídeo de mañana
    reg = leer(f"episodios/{manana}.json")
    hecho = reg.get("modo") == "diario" and (
        reg.get("youtube") or reg.get("revision") in ("pendiente", "ok") or reg.get("no_publicar"))
    if 16 <= ahora.hour <= 23 and not hecho:
        if reciente(runs, "Evangelio diario", 45):
            log("Vídeo de mañana: hay una tirada en marcha o reciente; espero.")
        else:
            lanzar("evangelio-diario.yml", modo="diario", fecha=str(manana))
    else:
        log(f"Vídeo de mañana: {'hecho' if hecho else 'aún no toca'} ({reg.get('revision') or reg.get('modo') or 'sin registro'}).")

    # 2. Veredictos sin aplicar
    for f in (hoy, manana):
        reg, rev = leer(f"episodios/{f}.json"), leer(f"revisiones/{f}.json")
        if not rev or reg.get("no_publicar") or reg.get("modo") != "diario":
            continue
        misma = not rev.get("generado") or rev.get("generado") == reg.get("generado")
        pendiente = misma and (reg.get("revision") == "pendiente" or (rev.get("ok") and not reg.get("youtube")))
        if pendiente and not reciente(runs, "Publicar revisado", 30):
            lanzar("publicar-revisado.yml", fecha=str(f))

    # 3. TikTok de hoy
    hora = int(json.loads(open('config/personajes.json', encoding='utf-8').read()).get('hora_publicacion', 7))
    if hora <= ahora.hour < hora + 12:
        reg, rev = leer(f"episodios/{hoy}.json"), leer(f"revisiones/{hoy}.json")
        preparado = subprocess.run(["gh", "release", "view", f"tiktok-{hoy}"], capture_output=True).returncode == 0
        if preparado and rev.get("ok") and not reg.get("no_publicar"):
            if reciente(runs, "Publicar en TikTok", 30):
                log("TikTok: en marcha o reciente; espero.")
            else:
                lanzar("tiktok-publicar.yml", fecha=str(hoy))
        else:
            log(f"TikTok: nada que hacer (preparado={preparado}, ok={bool(rev.get('ok'))}).")


def comentarios(runs):
    """4. Respuestas a comentarios: una pasada cada hora (el propio script decide si toca responder)."""
    if not reciente(runs, "Comentarios", 40):
        lanzar("comentarios.yml")


if __name__ == "__main__":
    main()
