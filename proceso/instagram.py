#!/usr/bin/env python3
"""CatholicAid · Instagram (Reels vía Instagram Graph API, con la página de Facebook vinculada).

El permiso (token de la página, que no caduca al salir de un token largo) se guarda CIFRADO en
secretos/instagram.enc con la clave META_APP_SECRET, igual que TikTok y YouTube.

Uso:
  python3 proceso/instagram.py url                 -> enlace para autorizar
  python3 proceso/instagram.py canjear <código>    -> canjea el código y guarda el permiso cifrado
  python3 proceso/instagram.py comprobar           -> muestra la cuenta de Instagram conectada
  python3 proceso/instagram.py subir <video.mp4> "<texto>"  -> publica el vídeo como Reel
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHERO = RAIZ / "secretos" / "instagram.enc"
REDIRECT = "https://carlitoslamas1.github.io/CatholicAid/instagram.html"
ALCANCES = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management"
VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{VERSION}/"


def _id():
    return os.environ["META_APP_ID"].strip()


def _secreto():
    return os.environ["META_APP_SECRET"].strip()


def _openssl(args, entrada):
    env = {**os.environ, "CLAVE_CIFRADO": _secreto()}
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-a", "-A", *args, "-pass", "env:CLAVE_CIFRADO"],
                       input=entrada, capture_output=True, env=env, check=True)
    return r.stdout


def guardar(datos):
    FICHERO.parent.mkdir(exist_ok=True)
    FICHERO.write_bytes(_openssl(["-salt"], json.dumps(datos).encode()))


def leer():
    return json.loads(_openssl(["-d"], FICHERO.read_bytes()))


def conectado():
    return FICHERO.exists() and bool(os.environ.get("META_APP_SECRET", "").strip())


def _get(ruta, **params):
    url = GRAPH + ruta + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta rechaza la petición ({e.code}): {e.read().decode(errors='replace')[:300]}")


def url_autorizacion():
    return "https://www.facebook.com/" + VERSION + "/dialog/oauth?" + urllib.parse.urlencode({
        "client_id": _id(), "redirect_uri": REDIRECT, "scope": ALCANCES, "response_type": "code",
        "state": "catolicaid"})


def canjear(codigo):
    corto = _get("oauth/access_token", client_id=_id(), client_secret=_secreto(), redirect_uri=REDIRECT,
                 code=urllib.parse.unquote(codigo.strip()))["access_token"]
    largo = _get("oauth/access_token", grant_type="fb_exchange_token", client_id=_id(), client_secret=_secreto(),
                 fb_exchange_token=corto)["access_token"]
    paginas = _get("me/accounts", access_token=largo, fields="id,name,access_token,instagram_business_account",
                   limit=100).get("data", [])
    for p in paginas:
        ig = p.get("instagram_business_account")
        if ig:
            datos = {"pagina_id": p["id"], "pagina": p["name"], "token": p["access_token"], "ig_id": ig["id"]}
            guardar(datos)
            return datos
    nombres = ", ".join(p["name"] for p in paginas) or "ninguna"
    raise RuntimeError(f"Ninguna de tus páginas ({nombres}) tiene una cuenta de Instagram profesional vinculada.")


def _post(url, datos=None, cuerpo=None, cabeceras=None):
    req = urllib.request.Request(url, data=cuerpo if cuerpo is not None else urllib.parse.urlencode(datos or {}).encode(),
                                 method="POST", headers=cabeceras or {})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta rechaza la petición ({e.code}): {e.read().decode(errors='replace')[:400]}")


def _contenedor(tok, ig, campos, video, url):
    if url:
        cont = _post(GRAPH + f"{ig}/media", {**campos, "video_url": url})
    else:
        cont = _post(GRAPH + f"{ig}/media", {**campos, "upload_type": "resumable"})
        datos = Path(video).read_bytes()
        _post(f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{cont['id']}", cuerpo=datos,
              cabeceras={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(datos)),
                         "Content-Type": "application/octet-stream"})
    estado = {}
    for _ in range(60):  # hasta 10 min procesando
        time.sleep(10)
        estado = _get(cont["id"], fields="status_code,status", access_token=tok)
        if estado.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            break
    if estado.get("status_code") != "FINISHED":
        raise RuntimeError(f"Instagram no procesó el vídeo ({'enlace' if url else 'archivo'}): {estado}")
    return cont["id"]


def subir(video, texto, url=None, portada=None):
    """Publica el vídeo como Reel. Primero con `url` (enlace público al .mp4, Instagram lo descarga); si falla
    o no hay enlace, enviando el archivo (subida reanudable). Devuelve (id, enlace)."""
    d = leer()
    tok, ig = d["token"], d["ig_id"]
    campos = {"media_type": "REELS", "caption": texto[:2200], "share_to_feed": "true", "access_token": tok}
    # Portada: la miniatura vertical con la frase clave; si no hay, un fotograma ya visible (el vídeo empieza en negro).
    campos.update({"cover_url": portada} if portada else {"thumb_offset": "1500"})
    intentos = ([url] if url else []) + [None]
    for i, u in enumerate(intentos):
        try:
            cid = _contenedor(tok, ig, campos, video, u)
            break
        except RuntimeError as e:
            print(e, flush=True)
            if i == len(intentos) - 1:
                raise
    pub = _post(GRAPH + f"{ig}/media_publish", {"creation_id": cid, "access_token": tok})
    enlace = _get(pub["id"], fields="permalink", access_token=tok).get("permalink", "")
    return pub["id"], enlace


def cuenta():
    d = leer()
    return _get(d["ig_id"], access_token=d["token"], fields="username,followers_count,media_count")


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "url":
        print(url_autorizacion())
    elif orden == "canjear":
        d = canjear(sys.argv[2])
        print(f"Instagram conectado a través de la página «{d['pagina']}».")
    elif orden == "comprobar":
        c = cuenta()
        print("Cuenta conectada: @" + c.get("username", "?"), "· publicaciones:", c.get("media_count"))
    elif orden == "subir":
        print(subir(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None))
    else:
        print(__doc__)
