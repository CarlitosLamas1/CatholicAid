"""Rosario v2 (26/11/2026): monta un rosario completo en 1920x1080, en la nube.

Uso: python3 rosario/v2/montar.py <clave> <carpeta_oraciones> <carpeta_lecturas> <salida.mp4> [fotos t1,t2,...]
- Oraciones: las tiradas aprobadas por Carlos (H_* hombre, M_* mujer; cada una grabada de una vez).
- Lecturas: <clave>_anuncioN y <clave>_lecturaN, con la voz del evangelista del rosario.
Reglas de Carlos: misterios impares empieza él y termina ella; pares al revés. Tras el Gloria, «María, Madre de
gracia…». Padrenuestro sin «Amén». Sin letanías. Al final: Salve (él), «Ruega por nosotros…» (él/ella) y la cruz.
Mismo diseño que la versión 1: pintura a la izquierda con zoom lento, texto a la derecha, cuentas que se encienden.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = pathlib.Path(__file__).resolve().parents[2]
CLAVE = sys.argv[1]
ORACIONES, LECTURAS = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
SALIDA = pathlib.Path(sys.argv[4])
FOTOS = sys.argv[5] if len(sys.argv) > 5 else ""
TMP = pathlib.Path(os.environ.get("TMP_ROSARIO", "/tmp/rosario_v2")) / CLAVE
TMP.mkdir(parents=True, exist_ok=True)
try:
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FF = "ffmpeg"
W, H, FPS, HZ = 1920, 1080, 25, 48000
ORO, AZUL = (245, 197, 66), (200, 225, 255)
TEMPO = {"rezo": 1.08, "lectura": 1.2}  # aprobado por Carlos en las catas
LIMPIAR = ("silenceremove=start_periods=1:start_threshold=-42dB,afade=t=in:d=0.015,areverse,"
           "silenceremove=start_periods=1:start_threshold=-42dB,afade=t=in:d=0.015,areverse,"
           "silenceremove=stop_periods=-1:stop_duration=0.45:stop_threshold=-40dB:stop_silence=0.35")
FUENTES = pathlib.Path(os.environ.get("FUENTES", "/tmp/fuentes"))
GUION = json.loads((REPO / "rosario" / "v2" / "guion.json").read_text(encoding="utf-8"))
ROS = GUION["rosarios"][CLAVE]
MIS = ROS["misterios"]
ORD = ["Primer", "Segundo", "Tercer", "Cuarto", "Quinto"]
EVANG = ROS["evangelista"]
MUSICA = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
          "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
          "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._55.ogg",
          "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg",
          "Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg"]
TXT = {}
for l in json.loads((REPO / "rosario" / "v2" / "lotes.json").read_text(encoding="utf-8"))["lotes"]:
    for x in l["lineas"]:
        TXT[x["id"]] = x["texto"]
for p in GUION["piezas"]:
    TXT.setdefault(p["id"], p["texto"])


def run(*a):
    subprocess.run([str(x) for x in a], check=True, capture_output=True)


def dur(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


PIEZA = {}


def pieza(ident):
    if ident in PIEZA:
        return PIEZA[ident]
    es_lectura = ident.startswith(CLAVE + "_")
    origen = (LECTURAS if es_lectura else ORACIONES) / f"{ident}.wav"
    destino = TMP / f"{ident}.wav"
    tempo = TEMPO["lectura" if es_lectura else "rezo"]
    run(FF, "-y", "-loglevel", "error", "-i", origen, "-af", f"{LIMPIAR},atempo={tempo},loudnorm=I=-18:TP=-2:LRA=11",
        "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", destino)
    PIEZA[ident] = destino
    return destino


# ---------- Guion del montaje ----------
P = REPO / "rosario" / "pinturas"
IMG = {f"{m}{c}": P / f"{CLAVE}_{m}{c}.jpg" for m in range(1, 6) for c in "abcL"}
IMG["maria"] = REPO / "personajes" / "maria.png"
pasos = []  # (pieza o None/"CAP", pausa, imagen, texto, color, cuentas, tipo, cabecera)
COLOR = {"H": "blanco", "M": "azul"}


def dos(a, b, base, img, cuentas, cab, tipo="", pausa_fin=0.6):
    pasos.append((f"{a}_{base}_a", 0.3, img, TXT[f"{a}_{base}_a"], COLOR[a], cuentas, tipo, cab))
    pasos.append((f"{b}_{base}_b", pausa_fin, img, TXT[f"{b}_{base}_b"], COLOR[b], cuentas, tipo, cab))


capitulos = [(0.0, "Inicio")]
CAB0 = "Oraciones iniciales"
pasos.append((None, 4.0, ROS["intro"], None, None, None, "intro", None))
pasos.append(("H_cruz", 1.0, ROS["intro"], TXT["H_cruz"], "blanco", None, "", CAB0))
pasos.append(("H_credo", 0.3, ROS["intro"], TXT["H_credo"], "blanco", None, "", CAB0))
pasos.append(("M_credo", 1.0, ROS["intro"], TXT["M_credo"], "azul", None, "", CAB0))
dos("H", "M", "pn", "maria", None, CAB0, pausa_fin=0.8)
for k in range(3):
    dos("H", "M", "av", "maria", (3, k + 1), CAB0)
dos("H", "M", "gl", "maria", (3, 4), CAB0, "gloria", 1.2)

for n, m in enumerate(MIS):
    i = n + 1
    a, b = ("H", "M") if i % 2 else ("M", "H")
    cab = f"{ORD[n]} misterio · {m['corto']}"
    pasos.append(("CAP", 0, None, f"{ORD[n]} misterio: {m['nombre'][0].lower() + m['nombre'][1:] if not m['nombre'].startswith('Jesús') else m['nombre']}", None, None, None, None))
    img_lect = f"{i}{m.get('imagen_lectura', 'a')}"
    if not IMG.get(img_lect, pathlib.Path("-")).exists():
        img_lect = f"{i}a"
    pasos.append((f"{CLAVE}_anuncio{i}", 1.6, img_lect, ("anuncio", n), None, None, "anuncio", cab))
    pasos.append((f"{CLAVE}_lectura{i}", 2.0, img_lect, ("lectura", n, m["lectura"]), "blanco", None, "lectura", cab))
    dos(a, b, "pn", f"{i}a", (10, 0), cab, pausa_fin=0.8)
    for k in range(10):
        dos(a, b, "av", f"{i}{'abc'[0 if k < 3 else 1 if k < 7 else 2]}", (10, k + 1), cab)
    dos(a, b, "gl", f"{i}c", (10, 11), cab, "gloria", 0.5)
    dos(a, b, "jac", f"{i}c", (10, 11), cab, "jac", 2.0)
pasos.append(("CAP", 0, None, "Salve y oración final", None, None, None, None))
pasos.append(("H_salve", 1.0, "maria", TXT["H_salve"], "blanco", None, "", "Salve"))
pasos.append(("H_ruega", 0.3, "maria", TXT["H_ruega"], "blanco", None, "", "Oración final"))
pasos.append(("M_ruega", 1.0, "maria", TXT["M_ruega"], "azul", None, "", "Oración final"))
pasos.append(("H_cruzfin", 1.5, ROS["intro"], TXT["H_cruzfin"], "blanco", None, "", "Oración final"))
pasos.append((None, 7.0, ROS["intro"], None, None, None, "fin", None))


def pantallas_lectura(texto):
    frases = re.findall(r"[^.:;?!”]+(?:[.:;?!”]+[”]?)?", texto)
    out, actual = [], ""
    for f in (x.strip() for x in frases if x.strip()):
        if actual and len(actual) + len(f) > 160:
            out.append(actual)
            actual = f
        else:
            actual = (actual + " " + f).strip()
    if actual:
        out.append(actual)
    return [re.sub(r"\s+([,;:.!?”])", r"\1", p) for p in out]


t = 0.0
voz_eventos, pantallas = [], []
for k, pausa, img, texto, color, cuentas, tipo, cab in pasos:
    if k == "CAP":
        capitulos.append((t, texto))
        continue
    if k is None:
        pantallas.append((t, t + pausa, img, None, None, None, tipo, cab))
        t += pausa
        continue
    ruta = pieza(k)
    d = dur(ruta)
    voz_eventos.append((t, ruta))
    if tipo == "lectura":
        trozos = pantallas_lectura(texto[2])
        letras = sum(len(x) for x in trozos)
        u = t
        for j, x in enumerate(trozos):
            fin = u + d * len(x) / letras
            pantallas.append((u, fin + (pausa if j == len(trozos) - 1 else 0), img, x, color, None, "lectura", cab))
            u = fin
    else:
        pantallas.append((t, t + d + pausa, img, texto, color, cuentas, tipo, cab))
    t += d + pausa
TOTAL = t
print(f"{CLAVE}: {TOTAL / 60:.1f} min", flush=True)
CAPS = "\n".join(f"{int(s // 60):02d}:{int(s % 60):02d} {n}" for s, n in capitulos)
print(CAPS, flush=True)
SALIDA.with_suffix(".capitulos.txt").write_text(CAPS, encoding="utf-8")

# ---------- Audio ----------
mezcla = TMP / "mezcla.wav"
if not FOTOS:
    voz = TMP / "voz.wav"
    datos = bytearray(int(TOTAL * HZ) * 2)
    for inicio, ruta in voz_eventos:
        with wave.open(str(ruta)) as w:
            b = w.readframes(w.getnframes())
        i = int(inicio * HZ) * 2
        datos[i:i + len(b)] = b[:len(datos) - i]
    with wave.open(str(voz), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(HZ)
        w.writeframes(bytes(datos))
    entradas, filtro = [], ""
    for j, nombre in enumerate(MUSICA):
        entradas += ["-i", str(REPO / "musica" / nombre)]
        filtro += f"[{j + 1}:a]aformat=sample_rates={HZ}:channel_layouts=stereo[m{j}];"
    for j in range(1, len(MUSICA)):
        filtro += f"[{'m0' if j == 1 else f'x{j - 1}'}][m{j}]acrossfade=d=5:c1=tri:c2=tri[x{j}];"
    run(FF, "-y", "-loglevel", "error", "-i", voz, *entradas, "-filter_complex",
        filtro + f"[x{len(MUSICA) - 1}]atrim=0:{TOTAL:.2f},asetpts=PTS-STARTPTS,volume=0.28,afade=t=in:d=3,"
        f"afade=t=out:st={TOTAL - 6:.2f}:d=6[m];"
        f"[0:a]aformat=sample_rates={HZ}:channel_layouts=stereo,asplit[v][sc];"
        "[m][sc]sidechaincompress=threshold=0.015:ratio=5:attack=250:release=1200:makeup=1[md];"
        "[v][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
        "-map", "[a]", "-ar", HZ, mezcla)

# ---------- Imagen ----------
PW, PH = 560, 1000
PX, PY = 170, 40
RX, RW = 860, 920


def fuente(estilo, t):
    """Gelasio (libre, OFL, hecha con las medidas de Georgia); si no está, DejaVu Serif."""
    nombre = {"normal": "Gelasio[wght].ttf", "cursiva": "Gelasio-Italic[wght].ttf", "negrita": "Gelasio[wght].ttf"}[estilo]
    try:
        f = ImageFont.truetype(str(FUENTES / nombre), t)
        try:
            f.set_variation_by_name("Bold" if estilo == "negrita" else "Regular")
        except Exception:
            pass
        return f
    except OSError:
        return ImageFont.truetype("DejaVuSerif-Bold.ttf" if estilo == "negrita" else "DejaVuSerif.ttf", t)


F_CAB = fuente("normal", 26)
F_TIT = fuente("cursiva", 36)
F_TXT = fuente("normal", 50)
F_TXT2 = fuente("normal", 42)
F_GRANDE = fuente("negrita", 64)
F_SUB = fuente("cursiva", 46)
F_MARCA = fuente("cursiva", 30)
cache = {}


def preparar(nombre):
    if nombre in cache:
        return cache[nombre]
    im = Image.open(IMG[nombre]).convert("RGB")
    fondo = im.resize((W, int(W * im.height / im.width)), Image.LANCZOS)
    y = (fondo.height - H) // 2
    fondo = fondo.crop((0, y, W, y + H)).filter(ImageFilter.GaussianBlur(40))
    fondo = Image.eval(fondo, lambda v: int(v * 0.30))
    sombra = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sombra).rectangle((PX - 6, PY - 6, PX + PW + 6, PY + PH + 6), fill=170)
    sombra = sombra.filter(ImageFilter.GaussianBlur(22))
    fondo = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), fondo, sombra)
    ImageDraw.Draw(fondo).rectangle((PX - 4, PY - 4, PX + PW + 3, PY + PH + 3), outline=(200, 170, 90), width=2)
    src = im.resize((int(PW * 1.07), int(PW * 1.07 * im.height / im.width)), Image.LANCZOS)
    cache[nombre] = (fondo, src)
    return cache[nombre]


def pintura(nombre, avance, sentido):
    fondo, src = preparar(nombre)
    avance = max(0.0, min(1.0, avance))
    avance = avance * avance * (3 - 2 * avance) * 0.5 + avance * 0.5
    a = 1.0 / (1.0 + 0.07 * (avance if sentido else 1 - avance))
    escala = (src.width / 1.07 / PW) * a
    c = src.width / 2 - escala * PW / 2
    f = max(0.0, min(src.height - escala * PH, src.height / 2 - escala * PH / 2))
    cuadro = src.transform((PW, PH), Image.AFFINE, (escala, 0, c, 0, escala, f), resample=Image.BICUBIC)
    lienzo = fondo.copy()
    lienzo.paste(cuadro, (PX, PY))
    return lienzo


def envolver(texto, f, ancho):
    lineas, l = [], ""
    for p in texto.split():
        prueba = (l + " " + p).strip()
        if f.getlength(prueba) > ancho and l:
            lineas.append(l)
            l = p
        else:
            l = prueba
    return lineas + ([l] if l else [])


capas = {}


def capa(p):
    _, _, _, texto, color, cuentas, tipo, cab = p
    clave = (str(texto), color, cuentas, tipo, cab)
    if clave in capas:
        return capas[clave]
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    cx = RX + RW // 2
    if tipo in ("intro", "fin"):
        d.text((cx, 400), "Santo Rosario", font=F_GRANDE, fill=(255, 255, 255, 255), anchor="mm")
        d.text((cx, 490), ROS["titulo"], font=F_SUB, fill=ORO + (255,), anchor="mm")
        d.text((cx, 565), ROS["dias"], font=F_MARCA, fill=(255, 255, 255, 200), anchor="mm")
        if tipo == "fin":
            d.text((cx, 700), "Síguenos para rezar cada día", font=F_MARCA, fill=(255, 255, 255, 200), anchor="mm")
        d.text((cx, 980), "CatolicAid", font=F_MARCA, fill=(255, 255, 255, 170), anchor="mm")
        capas[clave] = c
        return c
    d.text((cx, 95), "SANTO ROSARIO  ·  " + ROS["titulo"].upper(), font=F_CAB, fill=ORO + (235,), anchor="mm")
    d.text((cx, 148), cab, font=F_TIT, fill=(255, 255, 255, 215), anchor="mm")
    d.line((cx - 60, 188, cx + 60, 188), fill=ORO + (160,), width=2)
    if tipo == "anuncio":
        m = MIS[texto[1]]
        d.text((cx, 400), f"{ORD[texto[1]]} misterio", font=F_GRANDE, fill=(255, 255, 255, 255), anchor="mm")
        for j, l in enumerate(envolver(m["nombre"], F_SUB, RW - 80)):
            d.text((cx, 500 + j * 62), l, font=F_SUB, fill=ORO + (255,), anchor="mm")
        d.text((cx, 700), f"Fruto del misterio: {m['fruto']}", font=F_MARCA, fill=(255, 255, 255, 210), anchor="mm")
    elif texto:
        f = F_TXT
        lineas = envolver(texto, f, RW - 60)
        if len(lineas) > 7:
            f = F_TXT2
            lineas = envolver(texto, f, RW - 50)
        alto = int(f.size * 1.32)
        y0 = 520 - alto * len(lineas) / 2
        rgb = AZUL if color == "azul" else (255, 255, 255)
        if tipo == "lectura":
            cita = next(m["cita"] for m in MIS if m["corto"] in cab)
            d.text((cx, 250), f"Lee san {EVANG} · {cita}", font=F_MARCA, fill=(255, 255, 255, 170), anchor="mm")
        for j, l in enumerate(lineas):
            d.text((cx, y0 + j * alto), l, font=f, fill=rgb + (255,), anchor="mm", stroke_width=2,
                   stroke_fill=(0, 0, 0, 120))
    if cuentas is not None:
        total, actual = cuentas
        paso, r, y = 76, 15, 900
        x0 = cx - (total - 1) * paso / 2
        for i in range(total):
            x = x0 + i * paso
            if i + 1 < actual:
                d.ellipse((x - r, y - r, x + r, y + r), fill=ORO + (255,))
            elif i + 1 == actual:
                d.ellipse((x - r - 7, y - r - 7, x + r + 7, y + r + 7), fill=ORO + (70,))
                d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 236, 170, 255))
            else:
                d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, 150), width=3)
        etiqueta = {"gloria": "Gloria", "jac": "María, Madre de gracia"}.get(tipo) or (
            "Padre nuestro" if actual == 0 else f"Avemaría {actual} de {total}")
        d.text((cx, 960), etiqueta, font=F_MARCA, fill=(255, 255, 255, 190), anchor="mm")
    capas[clave] = c
    return c


def desvanecer(c, f):
    if f >= 1:
        return c
    c = c.copy()
    c.putalpha(c.getchannel("A").point(lambda a: int(a * f)))
    return c


tramos = []
for p in pantallas:
    if tramos and tramos[-1][2] == p[2]:
        tramos[-1][1] = p[1]
    else:
        tramos.append([p[0], p[1], p[2]])
FUNDIDO = 1.5
ti_, pi_ = [0], [0]


def cuadro(t):
    while ti_[0] + 1 < len(tramos) and t >= tramos[ti_[0]][1]:
        ti_[0] += 1
    while pi_[0] + 1 < len(pantallas) and t >= pantallas[pi_[0]][1]:
        pi_[0] += 1
    ti = ti_[0]
    a, b, nombre = tramos[ti]
    marco = pintura(nombre, (t - a) / max(b - a, 0.1), ti % 2 == 0)
    if ti > 0 and t - a < FUNDIDO:
        marco = Image.blend(pintura(tramos[ti - 1][2], 1.0, (ti - 1) % 2 == 0), marco, (t - a) / FUNDIDO)
    marco = marco.convert("RGBA")
    p = pantallas[pi_[0]]
    f = min(1.0, (t - p[0]) / 0.35, (p[1] - t) / 0.25)
    suave = p[6] in ("intro", "fin", "anuncio")
    marco.alpha_composite(desvanecer(capa(p), max(0.0, f) if suave else max(f, 0.55)))
    return marco.convert("RGB")


if FOTOS:
    for x in FOTOS.split(","):
        ti_[0] = pi_[0] = 0
        cuadro(float(x)).save(SALIDA.parent / f"foto_{CLAVE}_{x}.jpg", quality=85)
    sys.exit()

proc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-i", str(mezcla), "-map", "0:v", "-map", "1:a",
                         "-vf", f"fade=t=in:d=1.5,fade=t=out:st={TOTAL - 2.5:.2f}:d=2.5",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(SALIDA)],
                        stdin=subprocess.PIPE)
for k in range(int(TOTAL * FPS)):
    proc.stdin.write(cuadro(k / FPS).tobytes())
    if k % (FPS * 120) == 0:
        print(f"  {k / FPS / 60:.0f} min", flush=True)
proc.stdin.close()
if proc.wait():
    raise SystemExit("FFmpeg falló")
print("Hecho:", SALIDA)
