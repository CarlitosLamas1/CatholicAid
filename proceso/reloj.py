#!/usr/bin/env python3
"""CatholicAid · Reloj.

Los horarios de GitHub (cron) pueden llegar horas tarde o no llegar. Este script se ejecuta cada hora
(«Reloj», lo despierta la rutina del revisor en la nube, que sí es puntual) y lanza lo que falte:
1. Vídeo de mañana (16:00–23:59 Madrid): si no hay registro diario hecho, o el último intento falló o fue rechazado.
2. «Publicar revisado»: si hay veredicto del revisor que aún no se ha aplicado.
3. TikTok e Instagram (desde hora_publicacion de config, durante 12 h): si el vídeo de hoy tiene el OK, sigue preparado
   y aún no está publicado en esa red. La release se borra cuando ya está en las dos.
4. «Comentarios» cada hora (responde como mucho uno, con ritmo humano).
5. Canal en inglés (config «en».activo), siempre DESPUÉS de lo del español y sin bloquearlo: su vídeo de mañana
   (17:00–23:59 Madrid, cuando el español ya está hecho, o desde las 23:00 sin él) y su «Publicar revisado».
6. «Evangelio de la semana» los domingos de 17:00 a 23:59 (Madrid), si el cron de las 15 UTC no llegó.
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

    # 2b. Veredictos sin aplicar del inglés (revisiones/AAAA-MM-DD-en.json)
    for f in (hoy, manana):
        reg, rev = leer(f"episodios/{f}-en.json"), leer(f"revisiones/{f}-en.json")
        if not rev or reg.get("no_publicar") or reg.get("modo") != "diario":
            continue
        misma = not rev.get("generado") or rev.get("generado") == reg.get("generado")
        pendiente = misma and (reg.get("revision") == "pendiente" or (rev.get("ok") and not reg.get("youtube")))
        if pendiente and not reciente(runs, "Publicar revisado", 30):
            lanzar("publicar-revisado.yml", fecha=f"{f}-en")

    # 3. TikTok de hoy
    hora = int(json.loads(open('config/personajes.json', encoding='utf-8').read()).get('hora_publicacion', 7))
    if hora <= ahora.hour < hora + 12:
        reg, rev = leer(f"episodios/{hoy}.json"), leer(f"revisiones/{hoy}.json")
        preparado = subprocess.run(["gh", "release", "view", f"tiktok-{hoy}"], capture_output=True).returncode == 0
        falta_tt = preparado and rev.get("ok") and not reg.get("no_publicar") and not reg.get("tiktok")
        # TikTok en inglés (@catolicaid_en), si está conectado: misma tirada
        tt_en = subprocess.run(["git", "cat-file", "-e", "origin/main:secretos/tiktok-en.enc"]).returncode == 0
        if tt_en and not falta_tt:
            reg_en_tt, rev_en_tt = leer(f"episodios/{hoy}-en.json"), leer(f"revisiones/{hoy}-en.json")
            prep_en_tt = subprocess.run(["gh", "release", "view", f"en-{hoy}"], capture_output=True).returncode == 0
            falta_tt = (prep_en_tt and rev_en_tt.get("ok") and not reg_en_tt.get("no_publicar")
                        and not reg_en_tt.get("tiktok"))
        if falta_tt:
            if reciente(runs, "Publicar en TikTok", 30):
                log("TikTok: en marcha o reciente; espero.")
            else:
                lanzar("tiktok-publicar.yml", fecha=str(hoy))
        else:
            log(f"TikTok: nada que hacer (preparado={preparado}, ok={bool(rev.get('ok'))}).")
        # 3b. Instagram de hoy, español (mismo vídeo que TikTok) e inglés (release en-), con OK y sin publicar aún
        ig_conectado = subprocess.run(["git", "cat-file", "-e", "origin/main:secretos/instagram.enc"]).returncode == 0
        falta = []
        if ig_conectado and preparado and rev.get("ok") and not reg.get("no_publicar") and not reg.get("instagram"):
            falta.append("es")
        cfg_ig = json.loads(open("config/personajes.json", encoding="utf-8").read()).get("instagram", {})
        reg_en, rev_en = leer(f"episodios/{hoy}-en.json"), leer(f"revisiones/{hoy}-en.json")
        prep_en = subprocess.run(["gh", "release", "view", f"en-{hoy}"], capture_output=True).returncode == 0
        if (ig_conectado and cfg_ig.get("en") and prep_en and rev_en.get("ok") and not reg_en.get("no_publicar")
                and not reg_en.get("instagram")):
            falta.append("en")
        if falta:
            if reciente(runs, "Publicar en Instagram", 30):
                log("Instagram: en marcha o reciente; espero.")
            else:
                lanzar("instagram-publicar.yml", fecha=str(hoy), idioma=" ".join(falta) if len(falta) == 1 else "")
        else:
            log(f"Instagram: nada que hacer (conectado={ig_conectado}).")

    try:  # 6. Evangelio de la semana (domingo por la tarde), si el cron no llegó
        semana(runs, ahora)
    except Exception as e:
        log(f"Semana: no se pudo lanzar ({e})")

    try:  # el inglés, lo último: si falla, lo del español ya está hecho
        ingles(runs, ahora, manana)
    except Exception as e:
        log(f"Inglés: no se pudo lanzar ({e})")


def ingles(runs, ahora, manana):
    """5. Vídeo en inglés de mañana. Nunca antes que el español, y nunca si ya está hecho o en marcha."""
    cfg = json.loads(open("config/personajes.json", encoding="utf-8").read())
    if not cfg.get("en", {}).get("activo"):
        return
    es, en = leer(f"episodios/{manana}.json"), leer(f"episodios/{manana}-en.json")
    es_hecho = es.get("modo") == "diario" and (
        es.get("youtube") or es.get("revision") in ("pendiente", "ok", "rechazada") or es.get("no_publicar"))
    en_hecho = en.get("modo") == "diario" and (
        en.get("youtube") or en.get("revision") in ("pendiente", "ok") or en.get("no_publicar"))
    if en_hecho or not 17 <= ahora.hour <= 23:
        log(f"Inglés: {'hecho' if en_hecho else 'aún no toca'}.")
        return
    if en.get("estado") == "fallido" and en.get("cupo_agotado"):
        log("Inglés: sin cupo gratuito de Gemini hasta mañana; no se reintenta.")
        return
    if not es_hecho and ahora.hour < 23:
        log("Inglés: espero a que esté el vídeo en español.")
        return
    if reciente(runs, "Evangelio diario (inglés)", 100):
        log("Inglés: hay una tirada en marcha o reciente; espero.")
        return
    lanzar("evangelio-ingles.yml", modo="diario", fecha=str(manana))


def semana(runs, ahora):
    """6. Resumen semanal: domingo de 17:00 a 23:59 (Madrid), si aún no hay registro de ese domingo."""
    cfg = json.loads(open("config/personajes.json", encoding="utf-8").read()).get("resumen_semanal", {})
    if not cfg.get("activo") or ahora.weekday() != 6 or not 17 <= ahora.hour <= 23:
        return
    if leer(f"resumenes/{ahora.date()}.json"):
        log("Semana: hecho.")
    elif reciente(runs, "Evangelio de la semana", 120):
        log("Semana: en marcha o reciente; espero.")
    else:
        lanzar("resumen-semanal.yml")


def comentarios(runs):
    """4. Respuestas a comentarios: una pasada cada hora (el propio script decide si toca responder)."""
    if not reciente(runs, "Comentarios", 40):
        lanzar("comentarios.yml")


if __name__ == "__main__":
    main()
