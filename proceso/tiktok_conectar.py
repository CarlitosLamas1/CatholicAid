#!/usr/bin/env python3
"""Conecta la cuenta de TikTok de CatolicAid una sola vez.

Uso (en el Terminal, dentro de la carpeta del proyecto):  python3 proceso/tiktok_conectar.py
Pide la Client Key y el Client Secret de la app de TikTok (no se muestran en pantalla), abre el
navegador para autorizar, pide el código que aparece en la página de retorno y guarda en los secretos
de GitHub TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET y TIKTOK_REFRESH_TOKEN. Las claves no se muestran ni
se guardan en ningún archivo.
"""
import getpass
import json
import subprocess
import urllib.parse
import urllib.request
import webbrowser

REDIRECT = "https://carlitoslamas1.github.io/CatholicAid/tiktok.html"
ALCANCES = "user.info.basic,video.publish,video.upload"
REPO = "CarlitosLamas1/CatholicAid"


def guardar_secreto(nombre, valor):
    subprocess.run(["gh", "secret", "set", nombre, "--repo", REPO], input=valor.encode(), check=True,
                   stdout=subprocess.DEVNULL)


clave = getpass.getpass("Client Key de la app de TikTok (no se verá al escribir/pegar): ").strip()
secreto = getpass.getpass("Client Secret de la app de TikTok (no se verá al escribir/pegar): ").strip()
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": clave, "scope": ALCANCES, "response_type": "code", "redirect_uri": REDIRECT,
    "state": "catolicaid"})
print("\nSe abrirá TikTok en el navegador. Entra con la cuenta de CatolicAid y pulsa «Autorizar».")
print("Si no se abre solo, copia esta dirección en el navegador:\n" + url + "\n")
webbrowser.open(url)
codigo = input("Pega aquí el código que muestra la página de CatolicAid y pulsa Enter: ").strip()

datos = urllib.parse.urlencode({"client_key": clave, "client_secret": secreto, "code": codigo,
                                "grant_type": "authorization_code", "redirect_uri": REDIRECT}).encode()
req = urllib.request.Request("https://open.tiktokapis.com/v2/oauth/token/", data=datos,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
except urllib.error.HTTPError as e:
    res = {"error": e.code, "error_description": e.read().decode(errors="replace")[:300]}
if "refresh_token" not in res:
    print("\nTikTok no ha dado acceso:", res.get("error"), res.get("error_description"))
    raise SystemExit(1)

guardar_secreto("TIKTOK_CLIENT_KEY", clave)
guardar_secreto("TIKTOK_CLIENT_SECRET", secreto)
guardar_secreto("TIKTOK_REFRESH_TOKEN", res["refresh_token"])
print(f"\n✅ TikTok conectado y guardado en GitHub. Permisos: {res.get('scope')}. "
      f"El acceso dura {int(res.get('refresh_expires_in', 0)) // 86400} días y se renueva solo con el uso.")
