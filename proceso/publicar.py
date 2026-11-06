#!/usr/bin/env python3
"""CatholicAid · Publicar revisado.

Uso: python3 proceso/publicar.py AAAA-MM-DD

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
    fecha = sys.argv[1].strip()
    ruta_reg = RAIZ / "episodios" / f"{fecha}.json"
    reg, rev = leer(ruta_reg), leer(RAIZ / "revisiones" / f"{fecha}.json")
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
            sh("gh", "release", "delete", f"tiktok-{fecha}", "--yes", "--cleanup-tag", check=False)
            sh("gh", "workflow", "run", "evangelio-diario.yml", "-f", f"fecha={fecha}", "-f", "modo=diario")
            log(f"Revisión no OK: rehago el vídeo del {fecha}.")
            avisos.enviar(f"🔎 El revisor no ha aprobado el vídeo del <b>{avisos.e(cuando)}</b>:\n"
                          + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\n🔁 Lo rehago solo y el revisor lo vuelve a mirar. No tienes que hacer nada.")
        else:
            reg["revision"] = "rechazada"
            reg["no_publicar"] = "revisor: " + "; ".join(motivos)[:300]
            guardar(ruta_reg, reg)
            sh("gh", "release", "delete", f"tiktok-{fecha}", "--yes", "--cleanup-tag", check=False)
            log(f"Revisión no OK por segunda vez: el {fecha} no se publica.")
            avisos.enviar(f"⛔ El vídeo del <b>{avisos.e(cuando)}</b> <b>no se publica</b>: el revisor no lo ha aprobado "
                          "ni después de rehacerlo.\n" + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\nEl gestor lo revisará.")
        return

    reg["revision"] = "ok"
    if reg.get("youtube", {}).get("id"):
        log(f"El {fecha} ya está subido a YouTube ({reg['youtube']['url']}).")
        if not reg["youtube"].get("lista", {}).get("id"):  # completa la lista si faltó (p. ej. sin permiso entonces)
            lista = ev_mod.lista_evangelista(ev_mod.token_youtube(), reg["cita"].split()[0], reg["youtube"]["id"])
            if lista:
                reg["youtube"]["lista"] = lista
        guardar(ruta_reg, reg)
        return
    tmp = Path(tempfile.mkdtemp())
    sh("gh", "release", "download", f"tiktok-{fecha}", "-D", tmp, "-p", "video.mp4")
    video = tmp / "video.mp4"
    ev = {"cita": reg["cita"], "titulo": reg.get("titulo") or reg["fragmentos"][0]["texto"],
          "fuente_texto": reg.get("texto_fuente", "Vatican News"), "reflexion": reg.get("reflexion", ""),
          "frase_clave": reg.get("frase_clave", "")}
    tok = ev_mod.token_youtube()
    vid, estado = ev_mod.subir_youtube(video, ev, dt.date.fromisoformat(fecha), "diario", tok)
    reg["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
    lista = ev_mod.lista_evangelista(tok, reg["cita"].split()[0], vid)
    if lista:
        reg["youtube"]["lista"] = lista
    guardar(ruta_reg, reg)
    log(f"Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
    hora = f"{int(ev_mod.CFG.get('hora_publicacion', 7)):02d}:00"
    cuando_yt = f"programado a las {hora}" if estado.get("publishAt") else f"queda {estado['privacyStatus']}"
    nota = "" if rev.get("por") == "Carlos" else "\n🔎 Revisado por el revisor: todo correcto."
    avisos.enviar(f"✅ Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a YouTube ({cuando_yt}): "
                  f"{avisos.e(reg['youtube']['url'])}\n🎵 TikTok se publica a las {hora}.{nota}")


if __name__ == "__main__":
    main()
