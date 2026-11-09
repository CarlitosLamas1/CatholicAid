#!/usr/bin/env python3
"""CatholicAid · TikTok (Content Posting API, publicación directa).

El permiso (refresh token) se guarda CIFRADO en secretos/tiktok.enc con la clave TIKTOK_CLIENT_SECRET,
para que los procesos de GitHub puedan renovarlo solos sin que nadie lo vea.

Uso:
  python3 proceso/tiktok.py url                 -> muestra el enlace para autorizar la cuenta
  python3 proceso/tiktok.py canjear <código>    -> canjea el código y guarda el permiso cifrado
  python3 proceso/tiktok.py comprobar           -> renueva el permiso y muestra la cuenta conectada
  python3 proceso/tiktok.py subir <video.mp4> "<texto>"
Cuenta: TIKTOK_CUENTA=es (por defecto, @catolicaid, secretos/tiktok.enc) o en (@catolicaid_en, secretos/tiktok-en.enc).
Las dos usan la misma app de TikTok (mismas claves).
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
CUENTA = os.environ.get("TIKTOK_CUENTA", "es").strip() or "es"
FICHERO = RAIZ / "secretos" / ("tiktok.enc" if CUENTA == "es" else f"tiktok-{CUENTA}.enc")
PERFILES = {"es": "https://www.tiktok.com/@catolicaid", "en": "https://www.tiktok.com/@catolicaid_en"}


def usar(cuenta):
    """Cambia la cuenta con la que se trabaja (es / en)."""
    global CUENTA, FICHERO
    CUENTA = cuenta
    FICHERO = RAIZ / "secretos" / ("tiktok.enc" if cuenta == "es" else f"tiktok-{cuenta}.enc")
REDIRECT = "https://carlitoslamas1.github.io/CatholicAid/tiktok.html"
ALCANCES = "user.info.basic,video.upload,video.publish"
API = "https://open.tiktokapis.com/v2/"


def _clave():
    return os.environ["TIKTOK_CLIENT_KEY"].strip()


def _secreto():
    return os.environ["TIKTOK_CLIENT_SECRET"].strip()


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
    return FICHERO.exists() and bool(os.environ.get("TIKTOK_CLIENT_SECRET", "").strip())


def _token(campos):
    datos = urllib.parse.urlencode({"client_key": _clave(), "client_secret": _secreto(), **campos}).encode()
    req = urllib.request.Request(f"{API}oauth/token/", data=datos,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        res = {"error": e.code, "error_description": e.read().decode(errors="replace")[:300]}
    if "access_token" not in res:
        raise RuntimeError(f"TikTok no da acceso: {res.get('error')} {res.get('error_description')}")
    return res


def url_autorizacion():
    return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": _clave(), "scope": ALCANCES, "response_type": "code",
        "redirect_uri": REDIRECT, "state": "catolicaid" if CUENTA == "es" else f"catolicaid-{CUENTA}",
        "disable_auto_auth": "1"})


def canjear(codigo):
    res = _token({"code": urllib.parse.unquote(codigo.strip()), "grant_type": "authorization_code",
                  "redirect_uri": REDIRECT})
    guardar({"refresh_token": res["refresh_token"], "open_id": res.get("open_id"), "scope": res.get("scope")})
    return res


def acceso():
    """Renueva el permiso (TikTok puede devolver uno nuevo) y devuelve un access token válido."""
    datos = leer()
    res = _token({"grant_type": "refresh_token", "refresh_token": datos["refresh_token"]})
    if res.get("refresh_token") and res["refresh_token"] != datos["refresh_token"]:
        datos["refresh_token"] = res["refresh_token"]
        guardar(datos)
    return res["access_token"]


def _api(ruta, token, cuerpo=None):
    req = urllib.request.Request(f"{API}{ruta}", data=json.dumps(cuerpo or {}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        res = json.loads(e.read() or b"{}")
    err = res.get("error", {})
    if err.get("code") not in (None, "", "ok"):
        raise RuntimeError(f"TikTok {ruta}: {err.get('code')} {err.get('message')}")
    return res.get("data", {})


def cuenta(token):
    req = urllib.request.Request(f"{API}user/info/?fields=open_id,display_name,avatar_url",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("data", {}).get("user", {})


def subir(video, texto, privacidad="PUBLIC_TO_EVERYONE"):
    """Publica directamente el vídeo. Si la privacidad pedida no está permitida (app sin aprobar o cuenta
    privada), usa la más restrictiva disponible. Devuelve (publish_id, estado, privacidad usada)."""
    token = acceso()
    info = _api("post/publish/creator_info/query/", token)
    opciones = info.get("privacy_level_options", [])
    if privacidad not in opciones:
        privacidad = "SELF_ONLY" if "SELF_ONLY" in opciones else (opciones[0] if opciones else "SELF_ONLY")
    contenido = Path(video).read_bytes()
    tam = len(contenido)
    # TikTok: un solo envío solo hasta 64 MB; si no, trozos de 10 MB (el último se queda con el resto).
    trozo = tam if tam <= 60_000_000 else 10_000_000
    n = max(1, tam // trozo)
    datos = _api("post/publish/video/init/", token, {
        "post_info": {"title": texto[:2200], "privacy_level": privacidad, "disable_duet": False,
                      "disable_stitch": False, "disable_comment": False, "video_cover_timestamp_ms": 3000,
                      "is_aigc": True},
        "source_info": {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": trozo, "total_chunk_count": n}})
    for i in range(n):
        ini = i * trozo
        fin = tam if i == n - 1 else ini + trozo
        req = urllib.request.Request(datos["upload_url"], data=contenido[ini:fin], method="PUT",
                                     headers={"Content-Type": "video/mp4", "Content-Length": str(fin - ini),
                                              "Content-Range": f"bytes {ini}-{fin - 1}/{tam}"})
        with urllib.request.urlopen(req, timeout=600):
            pass
    estado = "PROCESSING"
    for _ in range(30):
        time.sleep(10)
        estado = _api("post/publish/status/fetch/", token, {"publish_id": datos["publish_id"]}).get("status", estado)
        if estado in ("PUBLISH_COMPLETE", "FAILED", "SEND_TO_USER_INBOX"):
            break
    return datos["publish_id"], estado, privacidad


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "url":
        print(url_autorizacion())
    elif orden == "canjear":
        r = canjear(sys.argv[2])
        print("TikTok conectado. Permisos:", r.get("scope"))
    elif orden == "comprobar":
        print("Cuenta conectada:", cuenta(acceso()).get("display_name"))
    elif orden == "subir":
        print(subir(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
