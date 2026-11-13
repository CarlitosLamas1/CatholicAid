#!/usr/bin/env python3
"""CatholicAid · Publicar revisado.

Uso: python3 proceso/publicar.py AAAA-MM-DD       (canal en español)
     python3 proceso/publicar.py AAAA-MM-DD-pt    (canal en portugués: igual que el inglés, release pt-AAAA-MM-DD)
     python3 proceso/publicar.py AAAA-MM-DD-en    (canal en inglés: episodios/…-en.json, revisiones/…-en.json,
                                                  release en-AAAA-MM-DD, permiso secretos/youtube-en.enc, sin TikTok;
                                                  en el estreno se sube en PRIVADO sin programar)

Lee la revisión del día (revisiones/AAAA-MM-DD.json, la escribe la rutina «Revisor diario» o Carlos con 👍):
- OK  -> sube a YouTube el vídeo de la release tiktok-AAAA-MM-DD, programado a la hora_publicacion (Madrid, config), y lo añade
         a la lista del evangelista. TikTok lo publica a esa hora (tiktok-publicar.yml / Reloj) porque hay OK.
- No OK -> la primera vez rehace el vídeo (evangelio-diario) para que el revisor lo vuelva a mirar;
           la segunda, no se publica (no_publicar en el registro, se borra la release) y se avisa a Carlos.
Si el registro tiene «no_publicar» (⛔ o /pausa), no se publica nada aunque haya OK.
Si el revisor pide «repintar» escenas (imágenes mejorables), se borran, se rehace el vídeo una vez y se revisa de nuevo.
Nunca cambia el texto del Evangelio.
"""
import datetime as dt
import json
import re
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


def guardar_en_main(mensaje):
    """Sube ya el registro (y las imágenes borradas) ANTES de relanzar el vídeo: la nueva tirada lo lee de main."""
    sh("git", "config", "user.name", "gestor-catholicaid")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", "-A", "episodios/", "biblioteca/dias/")
    if sh("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    sh("git", "commit", "-q", "-m", mensaje)
    for _ in range(3):
        if sh("git", "pull", "-q", "--rebase", check=False).returncode == 0 and sh("git", "push", "-q", check=False).returncode == 0:
            return
    log("Aviso: no se pudo subir el registro antes de relanzar (lo intenta el paso «Guardar registro»).")


IMAGEN = re.compile(r"\b(imagen|im[aá]genes|plano|cuadro|pintura)\b", re.I)
ESCENA = re.compile(r"\b(?:escena\s*|e)(\d)\b", re.I)
SIN_ARREGLO = re.compile(r"\bPNG\b|biblioteca/|evangelistas/|reutiliza", re.I)


def repintar_de_avisos(rev, fecha):
    """Avisos del revisor sobre una imagen pintada del día («La imagen de la escena 2 muestra a Jesús…», «firma en la
    esquina de e1») -> [{"escena": n, "corregir": aviso}]. Solo escenas cuya imagen del día existe."""
    pedidas = {}
    for aviso in rev.get("avisos") or []:
        if not IMAGEN.search(aviso) or SIN_ARREGLO.search(aviso):
            continue
        for n in {int(m) for m in ESCENA.findall(aviso)}:
            if any((RAIZ / "biblioteca" / "dias" / f"{fecha}_e{n}.{ext}").exists() for ext in ("jpg", "png")):
                pedidas.setdefault(n, []).append(aviso)
    return [{"escena": n, "corregir": "Fix the problem the reviewer found in the previous version (in Spanish): "
             + " ".join(t)} for n, t in sorted(pedidas.items())]


def pedir_repintar(fecha, idioma, reg, rev):
    """El revisor pide repintar escenas (rev["repintar"] = [{"escena": n, "corregir": "..."}]): se borran esas imágenes
    del día y la nueva tirada las pinta otra vez con la corrección. Una sola vez por día, solo en español (el inglés
    reutiliza las imágenes) y solo si da tiempo a revisarlo antes de publicar. Devuelve True si hay que rehacer."""
    pedidas = [x for x in rev.get("repintar") or [] if isinstance(x, dict) and str(x.get("escena", "")).isdigit()]
    if not pedidas:  # el revisor no lo pide de forma explícita: se sacan de sus avisos sobre imágenes del día
        pedidas = repintar_de_avisos(rev, fecha)
    if idioma != "es" or not pedidas or reg.get("repintados", 0) >= 1:
        return False
    publicar = dt.datetime.combine(dt.date.fromisoformat(fecha), ev_mod.hora_pub(),
                                   ev_mod.MADRID)
    if dt.datetime.now(ev_mod.MADRID) > publicar - dt.timedelta(hours=3):
        log("Repintar: ya no da tiempo antes de publicar; se deja como está.")
        return False
    borradas = []
    for x in pedidas:
        for ext in ("jpg", "png"):
            ruta = RAIZ / "biblioteca" / "dias" / f"{fecha}_e{int(x['escena'])}.{ext}"
            if ruta.exists():
                ruta.unlink()
                borradas.append(ruta.name)
    if not borradas:
        return False
    reg["repintar"] = [{"escena": int(x["escena"]), "corregir": str(x.get("corregir", ""))[:400]} for x in pedidas]
    reg["repintados"] = reg.get("repintados", 0) + 1
    log(f"Repintar: borradas {', '.join(borradas)}; el vídeo se rehace con las imágenes corregidas.")
    return True


def main():
    nombre = sys.argv[1].strip()
    fecha, idioma = avisos.idioma_de(nombre)
    ev_mod.aplicar_idioma(idioma)
    lengua = avisos.etiqueta(idioma)
    release = f"tiktok-{fecha}" if idioma == "es" else f"{idioma}-{fecha}"
    flujo = {"es": "evangelio-diario.yml", "en": "evangelio-ingles.yml", "pt": "evangelio-portugues.yml"}[idioma]
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

    sinc = reg.get("sincronia") or {}
    if rev.get("ok") and sinc and not sinc.get("ok") and reg.get("rehechos", 0) < MAX_REHECHOS:
        # Subtítulos que pueden ir desfasados (grabación cortada sin poder escucharla, o varias frases sin reconocer):
        # se rehace una vez aunque el revisor diera el OK.
        rev = {**rev, "ok": False, "motivos": (rev.get("motivos") or []) + [
            "Los subtítulos podrían no ir sincronizados con la voz; lo rehago para dejarlos perfectos."]}
    if rev.get("ok") and reg.get("revision") == "rechazada" and reg.get("repintar"):
        log(f"El {nombre} se está rehaciendo con imágenes repintadas; espero a la nueva versión.")
        return
    repintar = (rev.get("ok") or reg.get("rehechos", 0) < MAX_REHECHOS) and pedir_repintar(fecha, idioma, reg, rev)
    if rev.get("ok") and repintar:  # aprobado, pero con imágenes que se pueden arreglar: se repintan y se revisa otra vez
        reg["revision"] = "rechazada"
        guardar(ruta_reg, reg)
        guardar_en_main(f"Repintar imágenes: {nombre}")
        sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
        sh("gh", "workflow", "run", flujo, "-f", f"fecha={fecha}", "-f", "modo=diario")
        log(f"Revisión OK con imágenes a repintar: rehago el vídeo del {nombre}.")
        return

    if not rev.get("ok"):
        n = reg.get("rehechos", 0)
        if n < MAX_REHECHOS:
            reg["rehechos"] = n + 1
            reg["revision"] = "rechazada"
            guardar(ruta_reg, reg)
            guardar_en_main(f"Revisión no OK: rehacer {nombre}")
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
          "frase_clave": reg.get("frase_clave", ""), "musica": reg.get("musica", "")}
    tok = ev_mod.token_youtube(idioma)
    vid, estado = ev_mod.subir_youtube(video, ev, dt.date.fromisoformat(fecha), "diario", tok, idioma)
    reg["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
    guardar(ruta_reg, reg)  # lo subido queda anotado pase lo que pase después
    viejo = reg.get("reemplaza")
    if viejo and viejo != vid:  # versión anterior ya subida (vídeo rehecho): se borra para que no salgan dos
        try:
            ev_mod.http(ev_mod.YT + f"videos?id={viejo}", headers={"Authorization": f"Bearer {tok}"},
                        method="DELETE", raw=True)
            log(f"Borrada de YouTube la versión anterior ({viejo})")
            reg["reemplazado"] = reg.pop("reemplaza")
        except Exception as ex:
            log(f"No se pudo borrar la versión anterior {viejo} ({ex})")
        guardar(ruta_reg, reg)
    try:
        ev_mod.publicar_extras(tok, vid, reg, dt.date.fromisoformat(fecha), miniatura, idioma)
    except Exception as ex:
        log(f"Listas/miniatura no completadas ({ex})")
    guardar(ruta_reg, reg)
    log(f"Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
    hora = ev_mod.hora_pub(idioma).strftime("%H:%M")
    cuando_yt = f"programado a las {hora}" if estado.get("publishAt") else f"queda {estado['privacyStatus']}"
    nota = "" if rev.get("por") == "Carlos" else "\n🔎 Revisado por el revisor: todo correcto."
    if idioma == "es":
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a YouTube ({cuando_yt}): "
                      f"{avisos.e(reg['youtube']['url'])}\n🎵📸 TikTok e Instagram se publican a las {hora}.{nota}")
    else:
        estreno = "" if estado.get("publishAt") else "\n🔒 Estreno: queda en privado; tú decides cuándo se publica."
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a {avisos.CANALES[idioma]} "
                      f"({cuando_yt}): {avisos.e(reg['youtube']['url'])}{estreno}{nota}")


if __name__ == "__main__":
    main()
