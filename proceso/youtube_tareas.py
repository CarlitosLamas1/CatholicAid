#!/usr/bin/env python3
"""CatholicAid · Tareas horarias en YouTube (las lanza el workflow «Comentarios», que el Reloj despierta cada hora).

1. Comentario del canal: cuando el vídeo de hoy ya es público, el canal deja UN comentario con la pregunta de la
   reflexión para animar a comentar («comentario_canal» en el registro; una sola vez). YouTube no deja fijarlo por
   programa: queda como comentario del canal (con su insignia de autor).
2. Música reclamada: si Content ID bloquea o rechaza el vídeo de hoy o de mañana por la música, esa grabación queda
   vetada para siempre (estado/musica.json), se borra el vídeo de YouTube y se rehace con otra pista (el revisor lo
   vuelve a mirar y se publica igual que siempre). Una sola vez por día.
Nada de esto bloquea ni avisa por Telegram. Uso: python3 proceso/youtube_tareas.py
"""
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = ev.RAIZ
YT = ev.YT


def log(*a):
    print(*a, flush=True)


def leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guardar(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def texto_comentario(reg, idioma):
    """La pregunta de la reflexión (si la hay) y una invitación a comentar."""
    reflexion = " ".join((reg.get("reflexion") or "").split())
    preguntas = re.findall(r"¿[^?]*\?" if idioma == "es" else r"[^.!?]*\?", reflexion)
    pregunta = preguntas[-1].strip() if preguntas else ""
    if idioma == "en":
        pregunta = pregunta or "Which word from today’s Gospel will you carry with you?"
        return f"🕊️ {pregunta}\n\nShare it in the comments 👇 And if it helped you, pass it on to someone who needs it today."
    pregunta = pregunta or "¿Qué palabra de este Evangelio te llevas hoy?"
    return f"🕊️ {pregunta}\n\nTe leemos en los comentarios 👇 Y si te ha ayudado, compártelo con quien lo necesite hoy."


def estado_video(tok, vid):
    d = ev.http(YT + f"videos?part=status,contentDetails&id={vid}", headers={"Authorization": f"Bearer {tok}"})
    items = d.get("items") or []
    return items[0] if items else None


def bloqueado(item):
    """Motivo si YouTube ha bloqueado o rechazado el vídeo por derechos (Content ID), o «»."""
    st, cd = item.get("status", {}), item.get("contentDetails", {})
    if st.get("uploadStatus") == "rejected" and st.get("rejectionReason") in ("claim", "copyright", "trademark"):
        return f"rechazado por YouTube ({st['rejectionReason']})"
    rr = cd.get("regionRestriction") or {}
    if rr.get("blocked"):
        return f"bloqueado en {len(rr['blocked'])} países"
    if "allowed" in rr:
        return f"solo permitido en {len(rr['allowed'])} países"
    return ""


def comentario_canal(tok, idioma, hoy):
    nombre = f"{hoy}{ev.SUFIJO[idioma]}"
    ruta = RAIZ / "episodios" / f"{nombre}.json"
    reg = leer(ruta)
    yt = reg.get("youtube", {})
    if not yt.get("id") or reg.get("comentario_canal") or reg.get("no_publicar"):
        return
    item = estado_video(tok, yt["id"])
    if not item or item["status"].get("privacyStatus") != "public":
        log(f"Comentario del canal ({idioma}): el vídeo de hoy aún no es público.")
        return
    texto = texto_comentario(reg, idioma)
    try:
        r = ev.http(YT + "commentThreads?part=snippet", {"snippet": {
            "videoId": yt["id"], "topLevelComment": {"snippet": {"textOriginal": texto}}}},
            {"Authorization": f"Bearer {tok}"}, method="POST")
        reg["comentario_canal"] = {"id": r.get("id"), "texto": texto,
                                   "fecha": dt.datetime.now(ev.MADRID).isoformat(timespec="seconds")}
        log(f"Comentario del canal ({idioma}) publicado: {texto[:80]}")
    except urllib.error.HTTPError as e:
        motivo = e.read().decode(errors="replace")[:300]
        log(f"Comentario del canal ({idioma}) no publicado ({e.code}): {motivo}")
        if e.code in (400, 403):  # comentarios desactivados o sin permiso: no se insiste cada hora
            reg["comentario_canal"] = {"error": f"{e.code}: " + re.sub(r"\s+", " ", motivo)[:200]}
    guardar(ruta, reg)


def musica_reclamada(tok, idioma, fecha):
    nombre = f"{fecha}{ev.SUFIJO[idioma]}"
    ruta = RAIZ / "episodios" / f"{nombre}.json"
    reg = leer(ruta)
    yt = reg.get("youtube", {})
    if not yt.get("id") or reg.get("no_publicar") or reg.get("modo") != "diario":
        return
    item = estado_video(tok, yt["id"])
    if not item:
        return
    motivo = bloqueado(item)
    if not motivo:
        return
    pista = reg.get("musica") or ""
    log(f"Música ({nombre}): vídeo {yt['id']} {motivo}; pista {pista or '?'}")
    if pista:
        ev.vetar_musica(pista, f"{motivo} · vídeo {yt['id']} del {nombre}")
    if reg.get("musica_bloqueada"):  # ya se rehízo una vez: no se insiste (lo verá el gestor)
        log("   Ya se rehízo una vez por la música; no lo vuelvo a rehacer.")
        guardar(ruta, reg)
        return
    try:
        ev.http(YT + f"videos?id={yt['id']}", headers={"Authorization": f"Bearer {tok}"}, method="DELETE", raw=True)
        log("   Vídeo bloqueado borrado de YouTube")
    except Exception as e:
        log(f"   No se pudo borrar el vídeo bloqueado ({e})")
    reg["musica_bloqueada"] = {"video": yt["id"], "pista": pista, "motivo": motivo,
                               "fecha": dt.datetime.now(ev.MADRID).isoformat(timespec="seconds")}
    reg.pop("youtube", None)
    reg.pop("telegram_youtube", None)
    reg["revision"] = "rechazada"
    guardar(ruta, reg)
    subprocess.run(["git", "add", "-A", "episodios/", "estado/"], check=False)
    subprocess.run(["git", "commit", "-q", "-m", f"Música reclamada: rehacer {nombre}"], check=False)
    for _ in range(3):
        if (subprocess.run(["git", "pull", "-q", "--rebase"]).returncode == 0
                and subprocess.run(["git", "push", "-q"]).returncode == 0):
            break
    flujo = "evangelio-diario.yml" if idioma == "es" else "evangelio-ingles.yml"
    release = f"tiktok-{fecha}" if idioma == "es" else f"en-{fecha}"
    subprocess.run(["gh", "release", "delete", release, "--yes", "--cleanup-tag"], check=False)
    subprocess.run(["gh", "workflow", "run", flujo, "--ref", "main", "-f", f"fecha={fecha}", "-f", "modo=diario"], check=False)
    log(f"   Rehago el vídeo del {nombre} con otra música.")


def main():
    hoy = dt.datetime.now(ev.MADRID).date()
    for idioma in ("es", "en"):
        if idioma != "es" and not ev.CFG.get(idioma, {}).get("activo"):
            continue
        try:
            ev.aplicar_idioma(idioma)
            tok = ev.token_youtube(idioma)
        except Exception as e:
            log(f"YouTube ({idioma}): sin permiso ({e})")
            continue
        for tarea, args in ((musica_reclamada, (hoy,)), (musica_reclamada, (hoy + dt.timedelta(days=1),)),
                            (comentario_canal, (hoy,))):
            try:
                tarea(tok, idioma, *args)
            except Exception as e:  # una tarea nunca impide las demás
                log(f"{tarea.__name__} ({idioma}): {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
