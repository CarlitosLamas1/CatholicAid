#!/usr/bin/env python3
"""CatholicAid · Publicar revisado.

Uso: python3 proceso/publicar.py AAAA-MM-DD       (canal en español)
     python3 proceso/publicar.py AAAA-MM-DD-en    (canal en inglés: episodios/…-en.json, revisiones/…-en.json,
                                                  release en-AAAA-MM-DD, permiso secretos/youtube-en.enc, sin TikTok;
                                                  en el estreno se sube en PRIVADO sin programar)

Lee la revisión del día (revisiones/AAAA-MM-DD.json, la escribe la rutina «Revisor diario» o Carlos con 👍):
- OK  -> sube a YouTube el vídeo de la release tiktok-AAAA-MM-DD, programado a la hora_publicacion (Madrid, config), y lo añade
         a la lista del evangelista. TikTok lo publica a esa hora (tiktok-publicar.yml / Reloj) porque hay OK.
- No OK -> la primera vez rehace el vídeo (evangelio-diario) para que el revisor lo vuelva a mirar;
           la segunda, no se publica (no_publicar en el registro, se borra la release) y se avisa a Carlos.
Si el registro tiene «no_publicar» (⛔ o /pausa), no se publica nada aunque haya OK.
Nunca cambia el texto del Evangelio.
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
import evangelio as ev_mod  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
MAX_REHECHOS = 1


def log(*a):
    print(*a, flush=True)


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def guardar(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def sh(*args, check=True):
    return subprocess.run(list(map(str, args)), check=check, capture_output=True, text=True)


def main():
    nombre = sys.argv[1].strip()
    fecha, idioma = avisos.idioma_de(nombre)
    ev_mod.aplicar_idioma(idioma)
    lengua = avisos.etiqueta(idioma)
    release = f"tiktok-{fecha}" if idioma == "es" else f"en-{fecha}"
    flujo = "evangelio-diario.yml" if idioma == "es" else "evangelio-ingles.yml"
    ruta_reg = RAIZ / "episodios" / f"{nombre}.json"
    reg, rev = leer(ruta_reg), leer(RAIZ / "revisiones" / f"{nombre}.json")
    if not reg:
        log(f"No hay registro del {fecha}; nada que publicar.")
        return
    if reg.get("no_publicar"):
        log(f"El {fecha} está marcado para no publicar ({reg['no_publicar']}).")
        return
    if not rev:
        log(f"El {fecha} aún no está revisado.")
        return
    if rev.get("generado") and reg.get("generado") and rev["generado"] != reg["generado"]:
        log(f"La revisión es de otra versión del vídeo ({rev['generado']} ≠ {reg['generado']}); espero a la nueva.")
        return
    cuando = avisos.fecha_txt(fecha)
    motivos = rev.get("motivos") or []

    if not rev.get("ok"):
        n = reg.get("rehechos", 0)
        if n < MAX_REHECHOS:
            reg["rehechos"] = n + 1
            reg["revision"] = "rechazada"
            guardar(ruta_reg, reg)
            sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
            sh("gh", "workflow", "run", flujo, "-f", f"fecha={fecha}", "-f", "modo=diario")
            log(f"Revisión no OK: rehago el vídeo del {nombre}.")
            avisos.enviar(f"🔎 {lengua} · El revisor no ha aprobado el vídeo del <b>{avisos.e(cuando)}</b>:\n"
                          + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\n🔁 Lo rehago solo y el revisor lo vuelve a mirar. No tienes que hacer nada.")
        else:
            reg["revision"] = "rechazada"
            reg["no_publicar"] = "revisor: " + "; ".join(motivos)[:300]
            guardar(ruta_reg, reg)
            sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
            log(f"Revisión no OK por segunda vez: el {nombre} no se publica.")
            avisos.enviar(f"⛔ {lengua} · El vídeo del <b>{avisos.e(cuando)}</b> <b>no se publica</b>: el revisor no lo ha aprobado "
                          "ni después de rehacerlo.\n" + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\nEl gestor lo revisará.")
        return

    reg["revision"] = "ok"
    tmp = Path(tempfile.mkdtemp())
    sh("gh", "release", "download", release, "-D", tmp, "-p", "miniatura.jpg", check=False)
    miniatura = tmp / "miniatura.jpg" if (tmp / "miniatura.jpg").exists() else None
    if reg.get("youtube", {}).get("id"):
        log(f"El {nombre} ya está subido a YouTube ({reg['youtube']['url']}).")
        try:  # completa listas y miniatura si faltaron (p. ej. sin permiso entonces); nunca bloquea
            ev_mod.publicar_extras(ev_mod.token_youtube(idioma), reg["youtube"]["id"], reg,
                                   dt.date.fromisoformat(fecha), miniatura, idioma)
        except Exception as ex:
            log(f"Extras no completados ({ex})")
        guardar(ruta_reg, reg)
        return
    sh("gh", "release", "download", release, "-D", tmp, "-p", "video.mp4")
    video = tmp / "video.mp4"
    ev = {"cita": reg["cita"], "titulo": reg.get("titulo") or reg["fragmentos"][0]["texto"],
          "fuente_texto": reg.get("texto_fuente", "Vatican News"), "reflexion": reg.get("reflexion", ""),
          "frase_clave": reg.get("frase_clave", "")}
    tok = ev_mod.token_youtube(idioma)
    vid, estado = ev_mod.subir_youtube(video, ev, dt.date.fromisoformat(fecha), "diario", tok, idioma)
    reg["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
    guardar(ruta_reg, reg)  # lo subido queda anotado pase lo que pase después
    try:
        ev_mod.publicar_extras(tok, vid, reg, dt.date.fromisoformat(fecha), miniatura, idioma)
    except Exception as ex:
        log(f"Listas/miniatura no completadas ({ex})")
    guardar(ruta_reg, reg)
    log(f"Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
    hora = f"{int(ev_mod.CFG.get('hora_publicacion', 7)):02d}:00"
    cuando_yt = f"programado a las {hora}" if estado.get("publishAt") else f"queda {estado['privacyStatus']}"
    nota = "" if rev.get("por") == "Carlos" else "\n🔎 Revisado por el revisor: todo correcto."
    if idioma == "es":
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a YouTube ({cuando_yt}): "
                      f"{avisos.e(reg['youtube']['url'])}\n🎵 TikTok se publica a las {hora}.{nota}")
    else:
        estreno = "" if estado.get("publishAt") else "\n🔒 Estreno: queda en privado; tú decides cuándo se publica."
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a CatolicAid English "
                      f"({cuando_yt}): {avisos.e(reg['youtube']['url'])}{estreno}{nota}")


if __name__ == "__main__":
    main()
