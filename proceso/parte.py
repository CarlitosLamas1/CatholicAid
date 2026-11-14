#!/usr/bin/env python3
"""CatholicAid · Parte diario por Telegram (pedido por Carlos el 14/11/2026).

Un solo mensaje al día (hacia las 21:00 de Madrid, lo lanza el Reloj), claro y visual:
  · semáforo arriba: 🟢 todo en orden / 🟡 algo se está arreglando solo / 🟠 te necesito,
  · HOY: dónde ha salido el vídeo de cada idioma (YouTube, TikTok, Instagram) y sus visitas,
  · MAÑANA y PASADO MAÑANA: en qué punto está cada vídeo (creándose, revisión, aprobado y programado…),
  · lo que necesita a Carlos (si hay algo), con el enlace directo.
Mientras tanto, el Reloj arregla solo lo que falte; el parte solo cuenta cómo ha quedado.

Uso: python3 proceso/parte.py [--forzar]   (sin --forzar, una sola vez al día: estado/parte.json)
Necesita TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID y, para las visitas, YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
from avisos import MADRID, RAIZ, e, enviar, fecha_txt  # noqa: E402

BANDERAS = {"es": "🇪🇸", "en": "🇬🇧", "pt": "🇧🇷"}
NOMBRES = {"es": "Español", "en": "Inglés", "pt": "Portugués"}


def leer(ruta):
    p = RAIZ / ruta
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def idiomas():
    cfg = avisos.config()
    return ["es"] + [x for x in ("en", "pt") if cfg.get(x, {}).get("activo")]


def nombre(fecha, idioma):
    return f"{fecha}" + ("" if idioma == "es" else f"-{idioma}")


# ---------- YouTube: visitas ----------

_TOKENS = {}


def token_youtube(idioma):
    if idioma in _TOKENS:
        return _TOKENS[idioma]
    if idioma == "es":
        refresh = os.environ.get("YT_REFRESH_TOKEN", "").strip()
        try:
            import youtube_conectar
            refresh = youtube_conectar.guardado("es") or refresh
        except Exception:
            pass
    else:
        import youtube_conectar
        refresh = youtube_conectar.guardado(idioma)
    datos = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(), "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=datos), timeout=30) as r:
        _TOKENS[idioma] = json.loads(r.read())["access_token"]
    return _TOKENS[idioma]


def datos_youtube(idioma, video_id):
    """(visitas, me gusta, comentarios, privacidad) del vídeo, o None si no se puede consultar."""
    try:
        req = urllib.request.Request(
            f"https://www.googleapis.com/youtube/v3/videos?part=statistics,status&id={video_id}",
            headers={"Authorization": f"Bearer {token_youtube(idioma)}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.loads(r.read()).get("items", [])
        if not items:
            return None
        st, es = items[0].get("statistics", {}), items[0].get("status", {})
        return (int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), int(st.get("commentCount", 0)),
                es.get("privacyStatus", ""))
    except Exception as ex:
        avisos.log(f"visitas de YouTube ({idioma}) no disponibles: {ex}")
        return None


# ---------- Estado de cada vídeo ----------

def estado_futuro(fecha, idioma):
    """(icono, texto, necesita_a_carlos) del vídeo de una fecha que aún no se ha publicado."""
    reg, rev = leer(f"episodios/{nombre(fecha, idioma)}.json"), leer(f"revisiones/{nombre(fecha, idioma)}.json")
    hora = avisos.hora_publicacion(idioma)
    if not reg or reg.get("modo") != "diario":
        return "⏳", "aún sin crear (se hace solo)", False
    if reg.get("no_publicar"):
        motivo = (rev.get("motivos") or [""])[0]
        return "⛔", "NO se publicará" + (f": {e(motivo[:120])}" if motivo else ""), True
    if reg.get("estado") == "fallido":
        return "🔁", "falló al crearse; el reloj lo reintenta solo", False
    yt = reg.get("youtube") or {}
    if yt.get("id"):
        return "✅", f"aprobado y programado a las {hora}", False
    if rev.get("ok") and (not rev.get("generado") or rev.get("generado") == reg.get("generado")):
        return "✅", "aprobado; subiéndose a YouTube", False
    if reg.get("revision") == "pendiente":
        return "🕐", "hecho; esperando al revisor", False
    if reg.get("revision") == "rechazada":
        return "🔁", "el revisor lo rechazó; se está rehaciendo", False
    return "🕐", e(reg.get("revision") or "en marcha"), False


def marca(ok, pendiente=False):
    return "✅" if ok else ("🕐" if pendiente else "❌")


def linea_hoy(fecha, idioma, ahora, necesita):
    """Una línea por idioma con YouTube, TikTok e Instagram del vídeo publicado hoy."""
    cfg = avisos.config()
    reg = leer(f"episodios/{nombre(fecha, idioma)}.json")
    if not reg or reg.get("modo") != "diario":
        return f"{BANDERAS[idioma]} <b>{NOMBRES[idioma]}</b> · ❌ hoy no hubo vídeo"
    if reg.get("no_publicar"):
        return f"{BANDERAS[idioma]} <b>{NOMBRES[idioma]}</b> · ⛔ no se publicó (el revisor no lo aprobó)"
    yt = reg.get("youtube") or {}
    datos = datos_youtube(idioma, yt["id"]) if yt.get("id") else None
    publico = datos and datos[3] == "public"
    yt_txt = (f"<a href=\"{e(yt.get('url', ''))}\">📺</a>{marca(bool(yt.get('id')))}"
              + (" 🔒privado" if datos and not publico else ""))
    if datos and not publico:
        necesita.append(f"📺 El vídeo de hoy en {NOMBRES[idioma].lower()} sigue <b>privado</b> en YouTube: "
                        f"publícalo en YouTube Studio (<a href=\"{e(yt.get('url', ''))}\">abrir</a>).")
    partes = [yt_txt]
    tiktok_ok = (reg.get("tiktok") or {}).get("estado") == "PUBLISH_COMPLETE"
    if (RAIZ / "secretos" / ("tiktok.enc" if idioma == "es" else f"tiktok-{idioma}.enc")).exists():
        priv = (reg.get("tiktok") or {}).get("privacidad") == "SELF_ONLY"
        partes.append(f"🎵{marca(tiktok_ok)}" + ("🔒" if tiktok_ok and priv else ""))
    if (RAIZ / "secretos" / "instagram.enc").exists() and (idioma == "es" or cfg.get("instagram", {}).get(idioma)):
        ig = reg.get("instagram") or {}
        partes.append(f"<a href=\"{e(ig.get('enlace', 'https://www.instagram.com/'))}\">📸</a>{marca(bool(ig))}")
        if reg.get("instagram_duplicado"):
            necesita.append(f"📸 Instagram ({NOMBRES[idioma].lower()}) salió <b>dos veces</b>: borra el duplicado "
                            f"(<a href=\"{e(reg['instagram_duplicado'])}\">este</a>).")
    vis = f" · 👀 {datos[0]}" + (f" ❤️ {datos[1]}" if datos[1] else "") + (f" 💬 {datos[2]}" if datos[2] else "") \
        if datos else ""
    return f"{BANDERAS[idioma]} <b>{NOMBRES[idioma]}</b> · " + " ".join(partes) + vis


def visitas_ayer(ayer):
    """👀 visitas acumuladas del vídeo de ayer en cada canal (para ver cómo va)."""
    trozos = []
    for idioma in idiomas():
        yt = (leer(f"episodios/{nombre(ayer, idioma)}.json").get("youtube") or {})
        d = datos_youtube(idioma, yt["id"]) if yt.get("id") else None
        if d:
            trozos.append(f"{BANDERAS[idioma]} {d[0]}")
    return " · ".join(trozos)


# ---------- Mensaje ----------

def componer(ahora):
    hoy = ahora.date()
    manana, pasado, ayer = hoy + dt.timedelta(days=1), hoy + dt.timedelta(days=2), hoy - dt.timedelta(days=1)
    necesita, arreglando = [], []
    lineas_hoy = [linea_hoy(hoy, x, ahora, necesita) for x in idiomas()]
    for linea in lineas_hoy:
        if "❌" in linea:
            arreglando.append("algo de hoy no se publicó; el reloj lo reintenta durante 12 h")
            break

    bloques_futuro = []
    for fecha, titulo in ((manana, "MAÑANA"), (pasado, "PASADO MAÑANA")):
        es = leer(f"episodios/{fecha}.json")
        cab = f"📅 <b>{titulo}</b> · {e(fecha_txt(fecha))}"
        if es.get("cita"):
            cab += f"\n📖 {e(es['cita'])}"
        if es.get("frase_clave"):
            cab += f"\n💬 <i>«{e(es['frase_clave'])}»</i>"
        filas = []
        for idioma in idiomas():
            icono, texto, carlos = estado_futuro(fecha, idioma)
            filas.append(f"{BANDERAS[idioma]} {icono} {texto}")
            if carlos:
                necesita.append(f"{BANDERAS[idioma]} El vídeo de {titulo.lower()} en {NOMBRES[idioma].lower()} "
                                f"no se publicará: {texto.split(': ', 1)[-1]}. Dime si lo rehago.")
            elif icono in ("🔁",) or (icono in ("⏳", "🕐") and fecha == manana and ahora.hour >= 21):
                arreglando.append(f"{NOMBRES[idioma].lower()} de {titulo.lower()}")
        bloques_futuro.append(cab + "\n" + "\n".join(filas))

    pago = [f"{NOMBRES[x].lower()}" for f in (manana, pasado) for x in idiomas()
            if leer(f"episodios/{nombre(f, x)}.json").get("reserva_pago")]

    if necesita:
        semaforo = f"🟠 <b>Te necesito en {len(necesita)} cosa{'s' if len(necesita) > 1 else ''}</b>"
    elif arreglando:
        semaforo = "🟡 <b>Casi todo bien</b> · algo se está arreglando solo"
    else:
        semaforo = "🟢 <b>Todo en orden</b> · no tienes que hacer nada"

    msg = [f"🛡️ <b>PARTE DIARIO</b> · {e(fecha_txt(hoy))}", "━━━━━━━━━━━━━━━━━━", semaforo, ""]
    if necesita:
        msg += ["👉 <b>LO QUE TE TOCA</b>"] + [f"• {x}" for x in necesita] + [""]
    msg += [f"📣 <b>HOY</b> · publicado a las {avisos.hora_publicacion()}", *lineas_hoy,
            "<i>📺 YouTube · 🎵 TikTok · 📸 Instagram · 🔒 solo visible para ti</i>", ""]
    msg += [b + "\n" for b in bloques_futuro]
    if arreglando:
        msg += ["🔧 <b>ARREGLÁNDOSE SOLO</b>", "• " + "\n• ".join(dict.fromkeys(arreglando)), ""]
    vis = visitas_ayer(ayer)
    if vis:
        msg += [f"📊 <b>Visitas del vídeo de ayer</b> · {vis}", ""]
    if pago:
        msg += [f"💶 Hoy se usó la reserva de pago (cupo gratis agotado): {', '.join(dict.fromkeys(pago))}. Céntimos.", ""]
    msg += ["<i>Próximo parte: mañana a las 21:00.</i>"]
    return "\n".join(msg).strip()


def main():
    forzar = "--forzar" in sys.argv
    ahora = dt.datetime.now(MADRID)
    ruta = RAIZ / "estado" / "parte.json"
    hecho = leer("estado/parte.json")
    if hecho.get("fecha") == str(ahora.date()) and not forzar:
        avisos.log("el parte de hoy ya está enviado")
        return
    try:
        texto = componer(ahora)
    except Exception as ex:  # nunca se queda Carlos sin parte: uno mínimo
        texto = f"🛡️ <b>PARTE DIARIO</b> · {e(fecha_txt(ahora.date()))}\n⚠️ No pude preparar el parte completo ({e(ex)})."
    print(texto)
    if enviar(texto):
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_text(json.dumps({"fecha": str(ahora.date()), "enviado": ahora.isoformat(timespec="seconds")},
                                   ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # nunca bloquear
        avisos.log(f"parte no enviado ({type(ex).__name__}: {ex})")
