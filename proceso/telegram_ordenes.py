#!/usr/bin/env python3
"""CatholicAid · Órdenes de Carlos por Telegram (botones y comandos).

Lo lanza «Telegram: órdenes» cada 5 minutos. Lee los mensajes nuevos del bot (getUpdates), los confirma
uno a uno ANTES de actuar (así nada se ejecuta dos veces) y solo obedece al chat de Carlos.

Botones del aviso ✅ (dato «acción|AAAA-MM-DD»):
  ok   -> nada que hacer, sale a su hora          no   -> no publicar ese día
  img  -> rehacer con imágenes nuevas             voz  -> rehacer la lectura (voces y guion)
Comandos: /estado · /reintentar · /pausa N · /seguir · /ver D · /ayuda
"""
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
from avisos import MADRID, RAIZ, e, enviar, episodio, fecha_txt, log  # noqa: E402

ESTADO = RAIZ / "estado" / "telegram.json"
AYUDA = ("🤖 <b>Lo que puedes pedirme</b>\n"
         "/estado: qué hay preparado y cómo fue el último vídeo\n"
         "/reintentar: vuelve a generar el vídeo de mañana\n"
         "/pausa 3: no publica durante 3 días (desde mañana)\n"
         "/seguir: quita la pausa\n"
         "/ver 12: te mando el vídeo del día 12 (o /ver mañana)\n"
         "En el aviso ✅ tienes botones para publicar, no publicar o rehacerlo.\n"
         "⏱️ Leo tus mensajes cada 5–15 minutos.")


def hoy():
    return dt.datetime.now(MADRID).date()


def sh(*args, check=True):
    return subprocess.run(list(args), capture_output=True, text=True, timeout=300, check=check).stdout


def guardar_git(mensaje, *rutas):
    sh("git", "config", "user.name", "gestor-catholicaid")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", "-A", *rutas)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    sh("git", "commit", "-q", "-m", mensaje)
    for _ in range(3):
        if subprocess.run(["git", "pull", "-q", "--rebase"]).returncode == 0 and \
           subprocess.run(["git", "push", "-q"]).returncode == 0:
            return
    raise RuntimeError("no pude guardar el cambio en GitHub")


def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def escribir_estado(d):
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def guardar_episodio(fecha, reg):
    (RAIZ / "episodios" / f"{fecha}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def quitar_tiktok(fecha):
    return subprocess.run(["gh", "release", "delete", f"tiktok-{fecha}", "--yes", "--cleanup-tag"],
                          capture_output=True).returncode == 0


def desprogramar_youtube(vid):
    """Deja el vídeo en privado sin fecha de publicación. Devuelve True si YouTube lo aceptó."""
    try:
        tok = avisos.token_youtube()
        cuerpo = json.dumps({"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                                                   "containsSyntheticMedia": True}}).encode()
        req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?part=status", data=cuerpo,
                                     method="PUT", headers={"Authorization": f"Bearer {tok}",
                                                            "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).close()
        return True
    except Exception as ex:
        log(f"YouTube no deja desprogramar {vid} ({ex})")
        return False


def nota_youtube(ok, vid):
    if ok:
        return "En YouTube lo he dejado en privado, sin programar."
    return ("En YouTube no tengo permiso para quitar la programación (mientras no aprueben la auditoría "
            f"se queda privado igualmente). Si quieres, bórralo en Studio: https://studio.youtube.com/video/{vid}/edit")


# ---------- Acciones ----------

def no_publicar(fecha, motivo="Carlos pidió no publicarlo"):
    reg = episodio(fecha)
    tk = quitar_tiktok(fecha)
    partes = [f"⛔ <b>{e(fecha_txt(fecha))}</b>: no se publica."]
    partes.append("TikTok: cancelado." if tk else "TikTok: no había nada preparado.")
    if reg.get("youtube", {}).get("id"):
        partes.append(nota_youtube(desprogramar_youtube(reg["youtube"]["id"]), reg["youtube"]["id"]))
    if reg:
        reg["no_publicar"] = motivo
        guardar_episodio(fecha, reg)
    return "\n".join(partes)


def rehacer(fecha, imagenes):
    if dt.date.fromisoformat(str(fecha)) <= hoy():
        return f"Ese vídeo ({e(fecha_txt(fecha))}) ya está publicado o publicándose; no lo rehago."
    reg = episodio(fecha)
    extra = ""
    if reg.get("youtube", {}).get("id"):
        vid = reg["youtube"]["id"]
        ok = desprogramar_youtube(vid)
        if not ok:
            extra = (f"\nEl anterior se queda privado en YouTube (https://youtu.be/{vid}); "
                     "si lo publicas a mano, publica solo el nuevo.")
        reg.setdefault("descartados", []).append({**reg.pop("youtube"), "motivo": "otras imágenes" if imagenes else "otra lectura"})
        reg.pop("no_publicar", None)
        guardar_episodio(fecha, reg)
    quitar_tiktok(fecha)
    rutas = ["episodios/"]
    if imagenes:
        for p in (RAIZ / "biblioteca" / "dias").glob(f"{fecha}_e*.png"):
            p.unlink()
        rutas.append("biblioteca/dias/")
    guardar_git(f"Telegram: rehacer el {fecha}", *rutas)
    sh("gh", "workflow", "run", "evangelio-diario.yml", "-f", f"fecha={fecha}", "-f", "modo=diario")
    que = "con imágenes nuevas" if imagenes else "con otra lectura"
    return (f"🔁 Rehaciendo el vídeo del {e(fecha_txt(fecha))} {que}. "
            f"Te aviso cuando esté (unos 15 minutos).{e(extra)}")


def pausa(dias):
    hasta = hoy() + dt.timedelta(days=dias)
    est = leer_estado()
    est["pausa_hasta"] = str(hasta)
    escribir_estado(est)
    notas = []
    for i in range(1, dias + 1):
        f = hoy() + dt.timedelta(days=i)
        if episodio(f).get("youtube") or subprocess.run(["gh", "release", "view", f"tiktok-{f}"],
                                                         capture_output=True).returncode == 0:
            notas.append(no_publicar(f, "pausa"))
    guardar_git("Telegram: pausa", "estado/", "episodios/")
    texto = f"⏸️ En pausa hasta el {e(fecha_txt(hasta))} incluido: no se genera ni se publica nada. /seguir para quitarla."
    return "\n\n".join([texto, *notas])


def seguir():
    est = leer_estado()
    est.pop("pausa_hasta", None)
    escribir_estado(est)
    guardar_git("Telegram: fin de la pausa", "estado/")
    return "▶️ Pausa quitada. El vídeo de mañana se genera esta tarde como siempre (o usa /reintentar)."


def estado():
    lineas = [avisos.proximos_dias(hoy())]
    try:
        r = json.loads(sh("gh", "run", "list", "-w", "evangelio-diario.yml", "-L", "1", "--json",
                          "status,conclusion,createdAt,url"))[0]
        txt = {"success": "✅ bien", "failure": "❌ falló", "cancelled": "⚪ cancelado"}.get(
            r["conclusion"], "⏳ en marcha" if r["status"] != "completed" else r["conclusion"])
        cuando = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")).astimezone(MADRID)
        lineas.append(f"\n🛠️ Último proceso: {txt} ({cuando:%d/%m %H:%M})")
    except Exception as ex:
        log(f"sin estado de procesos ({ex})")
    if avisos.pausa_hasta() >= str(hoy()):
        lineas.append(f"⏸️ En pausa hasta el {e(fecha_txt(avisos.pausa_hasta()))}.")
    return "\n".join(lineas)


def reintentar():
    f = hoy() + dt.timedelta(days=1)
    if avisos.pausa_hasta() >= str(f):
        return "Mañana está en pausa. Usa /seguir primero."
    if episodio(f).get("youtube"):
        return rehacer(f, imagenes=False)
    sh("gh", "workflow", "run", "evangelio-diario.yml", "-f", f"fecha={f}", "-f", "modo=diario")
    return f"🔁 Generando el vídeo del {e(fecha_txt(f))}. Te aviso cuando esté (unos 15 minutos)."


def interpretar_dia(txt):
    txt = txt.strip().lower()
    if txt in ("", "hoy"):
        return hoy()
    if txt in ("mañana", "manana"):
        return hoy() + dt.timedelta(days=1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        return dt.date.fromisoformat(txt)
    m = re.fullmatch(r"(\d{1,2})(?:[/-](\d{1,2}))?", txt)
    if not m:
        return None
    d, mes = int(m.group(1)), int(m.group(2) or hoy().month)
    f = dt.date(hoy().year, mes, d)
    if f < hoy() - dt.timedelta(days=200):
        f = f.replace(year=f.year + 1)
    return f


def ver(arg):
    f = interpretar_dia(arg)
    if not f:
        return "No entiendo el día. Prueba /ver 12, /ver 12/11 o /ver mañana."
    reg = episodio(f)
    carpeta = Path(tempfile.mkdtemp())
    if subprocess.run(["gh", "release", "download", f"tiktok-{f}", "-D", str(carpeta), "-p", "video.mp4"],
                      capture_output=True).returncode == 0:
        try:
            avisos._api("sendVideo", {"chat_id": avisos.chat_id(), "caption": f"🎬 {fecha_txt(f)} · {reg.get('cita', '')}",
                                      "supports_streaming": "true"}, ("video", carpeta / "video.mp4"))
            return None
        except Exception as ex:
            log(f"no pude mandar el vídeo ({ex})")
    if reg.get("youtube", {}).get("url"):
        return (f"🎬 {e(fecha_txt(f))} · {e(reg.get('cita', ''))}\n▶️ {e(reg['youtube']['url'])}"
                "\n(Si es privado, ábrelo con la sesión de YouTube del canal.)")
    return f"No hay vídeo del {e(fecha_txt(f))} todavía."


# ---------- Bucle ----------

def responder_boton(cb):
    dato = cb.get("data", "")
    try:
        avisos._api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Recibido"})
    except Exception:
        pass  # si han pasado unos minutos, Telegram ya no lo acepta; no importa
    msg = cb.get("message", {})
    try:
        avisos._api("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                               "reply_markup": json.dumps({"inline_keyboard": []})})
    except Exception:
        pass
    accion, _, fecha = dato.partition("|")
    if accion == "prueba":
        return f"✅ Botón «{e(fecha)}» recibido: los botones funcionan. (Era una prueba: no he cambiado nada.)"
    if accion == "ok":
        return f"👍 Perfecto: el vídeo del {e(fecha_txt(fecha))} sale a las 7:00."
    if accion == "no":
        r = no_publicar(fecha)
        guardar_git(f"Telegram: no publicar el {fecha}", "episodios/")
        return r
    if accion in ("img", "voz"):
        return rehacer(fecha, imagenes=accion == "img")
    return "No reconozco ese botón."


def responder_texto(texto):
    orden, _, arg = texto.strip().partition(" ")
    orden = orden.lower().split("@")[0]
    if orden == "/estado":
        return estado()
    if orden == "/reintentar":
        return reintentar()
    if orden == "/pausa":
        n = int(arg) if arg.strip().isdigit() else 1
        return pausa(max(1, min(n, 30)))
    if orden in ("/seguir", "/reanudar"):
        return seguir()
    if orden == "/ver":
        return ver(arg)
    return AYUDA


def main():
    yo = avisos.chat_id()
    updates = avisos._api("getUpdates", {"timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])})
    if not updates:
        log("sin mensajes nuevos")
        return
    for u in updates:
        avisos._api("getUpdates", {"offset": u["update_id"] + 1, "timeout": 0})  # confirmar antes de actuar
        cb, msg = u.get("callback_query"), u.get("message")
        chat = str((cb or {}).get("message", {}).get("chat", {}).get("id") or (msg or {}).get("chat", {}).get("id"))
        if chat != yo:
            log(f"ignoro un mensaje de otro chat ({chat})")
            continue
        entrada = cb.get("data") if cb else (msg or {}).get("text", "")
        log(f"orden: {entrada}")
        try:
            r = responder_boton(cb) if cb else responder_texto(entrada or "")
        except Exception as ex:
            log(f"falló «{entrada}»: {ex}")
            r = f"⚠️ No he podido hacer «{e(entrada)}»: {e(str(ex)[:200])}. El gestor lo revisará."
        if r:
            enviar(r)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # nunca bloquear nada
        log(f"órdenes no procesadas ({type(ex).__name__}: {ex})")
