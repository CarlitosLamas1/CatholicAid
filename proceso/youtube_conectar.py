#!/usr/bin/env python3
"""CatholicAid · Reconectar YouTube con el permiso para gestionar el canal (listas y responder comentarios).

El permiso nuevo (refresh token) se guarda CIFRADO en secretos/youtube.enc con la clave YT_CLIENT_SECRET;
evangelio.py lo usa si existe (si no, el secreto YT_REFRESH_TOKEN de siempre).

Uso (en GitHub, workflow «Conectar YouTube»):
  python3 proceso/youtube_conectar.py url               -> enlace para autorizar (escribe youtube-url.txt)
  python3 proceso/youtube_conectar.py canjear <código>  -> canjea el código y guarda el permiso cifrado
  python3 proceso/youtube_conectar.py comprobar         -> muestra el canal y los permisos
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHERO = RAIZ / "secretos" / "youtube.enc"
REDIRECT = "http://localhost"
ALCANCES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl"]


def _openssl(args, entrada):
    env = {**os.environ, "CLAVE_CIFRADO": os.environ["YT_CLIENT_SECRET"].strip()}
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-a", "-A", *args, "-pass", "env:CLAVE_CIFRADO"],
                       input=entrada, capture_output=True, env=env, check=True)
    return r.stdout


def guardado():
    """Refresh token guardado (cifrado), o None."""
    if not FICHERO.exists() or not os.environ.get("YT_CLIENT_SECRET", "").strip():
        return None
    try:
        return json.loads(_openssl(["-d"], FICHERO.read_bytes())).get("refresh_token")
    except Exception:
        return None


def _token(campos):
    datos = urllib.parse.urlencode({"client_id": os.environ["YT_CLIENT_ID"].strip(),
                                    "client_secret": os.environ["YT_CLIENT_SECRET"].strip(), **campos}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=datos),
                                    timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Google no da acceso: {e.code} {e.read().decode(errors='replace')[:300]}")


def url():
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(), "redirect_uri": REDIRECT, "response_type": "code",
        "scope": " ".join(ALCANCES), "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true"})  # sin login_hint: se elige la cuenta que gestiona el canal


def canjear(codigo):
    codigo = codigo.strip()
    if "code=" in codigo:  # han pegado la dirección entera
        codigo = urllib.parse.parse_qs(urllib.parse.urlparse(codigo).query).get("code", [""])[0]
    res = _token({"code": urllib.parse.unquote(codigo), "grant_type": "authorization_code", "redirect_uri": REDIRECT})
    if "refresh_token" not in res:
        raise SystemExit(f"Google no ha dado un permiso duradero: {res}")
    FICHERO.parent.mkdir(exist_ok=True)
    FICHERO.write_bytes(_openssl(["-salt"], json.dumps({"refresh_token": res["refresh_token"],
                                                        "scope": res.get("scope")}).encode()))
    print("Permisos concedidos:", res.get("scope"))


def comprobar():
    tok = _token({"refresh_token": guardado() or os.environ["YT_REFRESH_TOKEN"].strip(), "grant_type": "refresh_token"})
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                 headers={"Authorization": f"Bearer {tok['access_token']}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        canal = json.loads(r.read())["items"][0]["snippet"]["title"]
    print(f"Canal: {canal} · permisos: {tok.get('scope')}")
    if "force-ssl" not in tok.get("scope", ""):
        raise SystemExit("Falta el permiso para gestionar el canal (force-ssl)")


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "url":
        enlace = url()
        Path("youtube-url.txt").write_text(enlace + "\n")
        print("Enlace guardado en youtube-url.txt (artefacto del workflow)")
    elif orden == "canjear":
        canjear(sys.argv[2])
    elif orden == "comprobar":
        comprobar()
    elif orden == "estado":  # estado real de los últimos vídeos subidos (público, privado, bloqueado...)
        tok = _token({"refresh_token": guardado() or os.environ["YT_REFRESH_TOKEN"].strip(), "grant_type": "refresh_token"})
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        ids = []
        for ruta in sorted((RAIZ / "episodios").glob("*.json"))[-8:]:
            vid = json.loads(ruta.read_text(encoding="utf-8")).get("youtube", {}).get("id")
            if vid:
                ids.append((ruta.stem, vid))
        q = urllib.parse.urlencode({"part": "status,snippet", "id": ",".join(v for _, v in ids)})
        with urllib.request.urlopen(urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?" + q, headers=h)) as r:
            datos = {i["id"]: i for i in json.loads(r.read())["items"]}
        for fecha, vid in ids:
            st = datos.get(vid, {}).get("status", {})
            print(fecha, vid, json.dumps(st, ensure_ascii=False))
    else:
        print(__doc__)
