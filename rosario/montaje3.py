"""Monta el Santo Rosario (misterios dolorosos) completo en 1920x1080.

Uso: python3 montaje2.py <carpeta_piezas> <salida.mp4> [fotos t1,t2,...]
La carpeta tiene un WAV por pieza (credo_a.wav, lectura1.wav, av_b3.wav…), ya cada uno en su propia grabación.
"""
import json
import pathlib
import re
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = pathlib.Path("/Users/carloslamasalvarez/code/CatholicAid")
AQUI = pathlib.Path(__file__).resolve().parent
CLAVE = sys.argv[1]
PIEZAS = pathlib.Path(sys.argv[2])  # oraciones comunes (las del doloroso)
NUEVAS = pathlib.Path(sys.argv[3])  # anuncios y lecturas de este rosario
SALIDA = pathlib.Path(sys.argv[4])
sys.argv = [sys.argv[0], "", ""] + sys.argv[5:]  # deja fotos en argv[3] como en montaje2
TMP = AQUI / f"tmp_{CLAVE}"
TMP.mkdir(exist_ok=True)
W, H, FPS, HZ = 1920, 1080, 25, 48000
ORO = (245, 197, 66)
AZUL = (200, 225, 255)
LIMPIAR = ("silenceremove=start_periods=1:start_threshold=-42dB,afade=t=in:d=0.015,areverse,"
           "silenceremove=start_periods=1:start_threshold=-42dB,afade=t=in:d=0.015,areverse,"
           "silenceremove=stop_periods=-1:stop_duration=0.45:stop_threshold=-40dB:stop_silence=0.35,"
           "atempo=1.15,loudnorm=I=-18:TP=-2:LRA=11")
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SERIF_I = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"
SERIF_B = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"

GUION = json.loads((PIEZAS / "guion_dolorosos.json").read_text(encoding="utf-8"))
TXT = {p["id"]: p["texto"] for p in GUION["piezas"]}
TRES = json.loads((NUEVAS / "guion.json").read_text(encoding="utf-8"))
ROS = TRES["rosarios"][CLAVE]
TXT.update({
    "cruz": "Por la señal de la Santa Cruz, de nuestros enemigos líbranos, Señor, Dios nuestro. En el nombre del Padre, "
            "y del Hijo, y del Espíritu Santo. Amén.",
    "pn_a": "Padre nuestro, que estás en el cielo, santificado sea tu Nombre; venga a nosotros tu reino; hágase tu "
            "voluntad en la tierra como en el cielo.",
    "gl_a": "Gloria al Padre, y al Hijo, y al Espíritu Santo.",
    "oj": "Oh, Jesús mío, perdona nuestros pecados, líbranos del fuego del infierno, lleva al cielo a todas las almas, "
          "especialmente a las más necesitadas de tu misericordia. Amén.",
})
for k in range(1, 11):
    TXT.setdefault(f"av_a{k}", TXT["av_a6"])
    TXT.setdefault(f"av_b{k}", TXT["av_b2"])
TXT.setdefault("pn_b", TXT["pn_b1"])


def run(*a):
    subprocess.run([str(x) for x in a], check=True, capture_output=True)


def dur(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


T = {}
for f in sorted(PIEZAS.glob("*.wav")) + sorted(NUEVAS.glob(f"{CLAVE}_*.wav")):
    dest = TMP / f.name
    if not dest.exists():
        run("ffmpeg", "-y", "-i", f, "-af", LIMPIAR, "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", dest)
    T[f.stem] = dest
faltan = [k for k in TXT if k not in T and not re.match(r"av_[ab]\d+$|pn_b$", k)]
print("Piezas:", len(T), "· faltan:", faltan)

# ---------- Guion del montaje ----------
P = AQUI / "pinturas2"
IMG = {f"{m}{c}": P / f"{CLAVE}_{m}{c}.jpg" for m in range(1, 6) for c in "abc"}
IMG["maria"] = REPO / "personajes" / "maria.png"
CORTO = [m["corto"] for m in ROS["misterios"]]
INTRO = {"gozosos": "3b", "gloriosos": "5b", "luminosos": "4a"}[CLAVE]
ORD = ["Primer", "Segundo", "Tercer", "Cuarto", "Quinto"]
MIS = ROS["misterios"]

pasos = []  # (pieza o None, pausa después, imagen, texto, color, cuentas, tipo, cabecera)
ia = [0]
ib = [0]
a_disp = [f"av_a{k}" for k in range(1, 11) if f"av_a{k}" in T]
b_disp = [f"av_b{k}" for k in range(1, 10) if f"av_b{k}" in T]
pn_b = [k for k in ("pn_b1", "pn_b2") if k in T]
gl_b = [k for k in ("gl_b1", "gl_b2") if k in T]


def ave(img, cuentas, cab):
    a = a_disp[ia[0] % len(a_disp)]
    b = b_disp[(ib[0] * 3 + 1) % len(b_disp)]  # otro orden que las del guía, para que no se repitan las parejas
    ia[0] += 1
    ib[0] += 1
    pasos.append((a, 0.35, img, TXT["av_a1"], "blanco", cuentas, "", cab))
    pasos.append((b, 0.75, img, TXT["av_b2"], "azul", cuentas, "", cab))


def padrenuestro(img, cuentas, cab, n):
    pasos.append(("pn_a", 0.35, img, TXT["pn_a"], "blanco", cuentas, "", cab))
    pasos.append((pn_b[n % len(pn_b)], 1.0, img, TXT["pn_b1"], "azul", cuentas, "", cab))


def gloria(img, cuentas, cab, n, oj=True):
    pasos.append(("gl_a", 0.35, img, TXT["gl_a"], "blanco", cuentas, "gloria", cab))
    pasos.append((gl_b[n % len(gl_b)], 0.9 if oj else 2.0, img, TXT["gl_b1"], "azul", cuentas, "gloria", cab))
    if oj:
        pasos.append(("oj", 2.5, img, TXT["oj"], "blanco", cuentas, "oj", cab))


capitulos = [(0.0, "Inicio")]
CAB0 = "Oraciones iniciales"
pasos.append((None, 4.0, INTRO, None, None, None, "intro", None))
pasos.append(("cruz", 1.2, INTRO, TXT["cruz"], "blanco", None, "", CAB0))
pasos.append(("credo_a", 0.35, INTRO, TXT["credo_a"], "blanco", None, "", CAB0))
pasos.append(("credo_b", 1.0, INTRO, TXT["credo_b"], "azul", None, "", CAB0))
padrenuestro("maria", None, CAB0, 0)
for k in range(3):
    ave("maria", (3, k + 1), CAB0)
gloria("maria", (3, 3), CAB0, 0, oj=False)

for n, m in enumerate(MIS):
    i = n + 1
    cab = f"{ORD[n]} misterio · {CORTO[n]}"
    pasos.append(("CAP", 0, None, f"{ORD[n]} misterio: {m['nombre'][0].lower() + m['nombre'][1:] if not m['nombre'].startswith('Jesús') else m['nombre']}", None, None, None, None))
    pasos.append((f"{CLAVE}_anuncio{i}", 2.2, f"{i}a", ("anuncio", n), None, None, "anuncio", cab))
    partes = m["lectura"]
    for k, (vozp, textop) in enumerate(partes, 1):
        ultima = k == len(partes)
        pasos.append((f"{CLAVE}_lectura{i}_{k}", 2.5 if ultima else 0.3, f"{i}a", ("lectura", n, textop),
                      "blanco" if vozp == "Enceladus" else "azul", None, "lectura", cab))
    padrenuestro(f"{i}a", (10, 0), cab, n)
    for k in range(10):
        ave(f"{i}{'abc'[0 if k < 3 else 1 if k < 7 else 2]}", (10, k + 1), cab)
    gloria(f"{i}c", (10, 11), cab, n)
pasos.append(("CAP", 0, None, "Salve y oración final", None, None, None, None))
CABF = "Salve"
pasos.append(("salve_a", 1.2, "maria", TXT["salve_a"], "blanco", None, "", CABF))
pasos.append(("ruega_a", 0.35, "maria", TXT["ruega_a"], "blanco", None, "", CABF))
pasos.append(("ruega_b", 1.2, "maria", TXT["ruega_b"], "azul", None, "", CABF))
pasos.append(("cruz_fin", 1.5, INTRO, TXT["cruz_fin"], "blanco", None, "", CABF))
pasos.append((None, 7.0, INTRO, None, None, None, "fin", None))


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
lect_idx = {}
voz_eventos, pantallas = [], []  # (inicio, wav) · (inicio, fin, imagen, texto, color, cuentas, tipo, cabecera)
for k, pausa, img, texto, color, cuentas, tipo, cab in pasos:
    if k == "CAP":
        capitulos.append((t, texto))
        continue
    if k is None:
        pantallas.append((t, t + pausa, img, None, None, None, tipo, cab))
        t += pausa
        continue
    d = dur(T[k])
    voz_eventos.append((t, T[k]))
    if tipo == "lectura":
        n = texto[1]
        trozos = pantallas_lectura(texto[2])
        letras = sum(len(x) for x in trozos)
        u = t
        lect_idx[n] = lect_idx.get(n, 0)
        for j, x in enumerate(trozos):
            fin = u + d * len(x) / letras
            im = f"{n + 1}a" if lect_idx[n] < 2 else f"{n + 1}b"
            lect_idx[n] += 1
            pantallas.append((u, fin + (pausa if j == len(trozos) - 1 else 0), im, x, color, None, "lectura", cab))
            u = fin
    else:
        pantallas.append((t, t + d + pausa, img, texto, color, cuentas, tipo, cab))
    t += d + pausa
TOTAL = t
print(f"Duración: {TOTAL / 60:.1f} min")
for s, nombre in capitulos:
    print(f"{int(s // 60):02d}:{int(s % 60):02d} {nombre}")
(AQUI / f"capitulos_{CLAVE}.txt").write_text("\n".join(f"{int(s // 60):02d}:{int(s % 60):02d} {n}" for s, n in capitulos),
                                    encoding="utf-8")

# ---------- Audio ----------
mezcla = TMP / "mezcla.wav"
if len(sys.argv) <= 3:
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
    lista = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
             "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
             "Clair_de_lune_(Claude_Debussy)_Suite_bergamasque.ogg",
             "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg"]
    entradas, filtro, prev = [], "", None
    for j, nombre in enumerate(lista):
        entradas += ["-i", str(REPO / "musica" / nombre)]
        filtro += f"[{j + 1}:a]aformat=sample_rates={HZ}:channel_layouts=stereo[m{j}];"
    for j in range(1, len(lista)):
        a = "m0" if j == 1 else f"x{j - 1}"
        filtro += f"[{a}][m{j}]acrossfade=d=5:c1=tri:c2=tri[x{j}];"
    ultima = f"x{len(lista) - 1}"
    run("ffmpeg", "-y", "-i", voz, *entradas, "-filter_complex",
        filtro + f"[{ultima}]atrim=0:{TOTAL:.2f},asetpts=PTS-STARTPTS,volume=0.28,afade=t=in:d=3,"
        f"afade=t=out:st={TOTAL - 6:.2f}:d=6[m];"
        f"[0:a]aformat=sample_rates={HZ}:channel_layouts=stereo,asplit[v][sc];"
        "[m][sc]sidechaincompress=threshold=0.015:ratio=5:attack=250:release=1200:makeup=1[md];"
        "[v][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
        "-map", "[a]", "-ar", HZ, mezcla)

# ---------- Imagen ----------
PW, PH = 560, 1000
PX, PY = 170, 40
RX, RW = 860, 920


def fuente(ruta, t):
    return ImageFont.truetype(ruta, t)


F_CAB = fuente(SERIF, 26)
F_TIT = fuente(SERIF_I, 36)
F_TXT = fuente(SERIF, 50)
F_GRANDE = fuente(SERIF_B, 64)
F_SUB = fuente(SERIF_I, 46)
F_MARCA = fuente(SERIF_I, 30)
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
        n = texto[1]
        m = MIS[n]
        d.text((cx, 400), f"{ORD[n]} misterio", font=F_GRANDE, fill=(255, 255, 255, 255), anchor="mm")
        for j, l in enumerate(envolver(m["nombre"], F_SUB, RW - 80)):
            d.text((cx, 500 + j * 62), l, font=F_SUB, fill=ORO + (255,), anchor="mm")
        d.text((cx, 700), f"Fruto del misterio: {m['fruto']}", font=F_MARCA, fill=(255, 255, 255, 210), anchor="mm")
    elif texto:
        f = F_TXT
        lineas = envolver(texto, f, RW - 60)
        if len(lineas) > 7:
            f = fuente(SERIF, 42)
            lineas = envolver(texto, f, RW - 50)
        alto = int(f.size * 1.32)
        y0 = 520 - alto * len(lineas) / 2
        rgb = AZUL if color == "azul" else (255, 255, 255)
        if tipo == "lectura":
            cita = next(m["cita"] for m in MIS if CORTO[MIS.index(m)] in cab)
            d.text((cx, 250), cita, font=F_MARCA, fill=(255, 255, 255, 160), anchor="mm")
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
        if tipo == "gloria":
            etiqueta = "Gloria"
        elif tipo == "oj":
            etiqueta = "Oh, Jesús mío"
        elif actual == 0:
            etiqueta = "Padre nuestro"
        else:
            etiqueta = f"Avemaría {actual} de {total}"
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
ti_ = [0]
pi_ = [0]


def cuadro(t):
    while ti_[0] + 1 < len(tramos) and t >= tramos[ti_[0]][1]:
        ti_[0] += 1
    while pi_[0] + 1 < len(pantallas) and t >= pantallas[pi_[0]][1]:
        pi_[0] += 1
    ti = ti_[0]
    a, b, nombre = tramos[ti]
    marco = pintura(nombre, (t - a) / max(b - a, 0.1), ti % 2 == 0)
    if ti > 0 and t - a < FUNDIDO:
        ant = pintura(tramos[ti - 1][2], 1.0, (ti - 1) % 2 == 0)
        marco = Image.blend(ant, marco, (t - a) / FUNDIDO)
    marco = marco.convert("RGBA")
    p = pantallas[pi_[0]]
    f = min(1.0, (t - p[0]) / 0.35, (p[1] - t) / 0.25)
    suave = p[6] in ("intro", "fin", "anuncio")
    marco.alpha_composite(desvanecer(capa(p), max(0.0, f) if suave else max(f, 0.55)))
    return marco.convert("RGB")


if len(sys.argv) > 3:
    for x in sys.argv[3].split(","):
        ti_[0] = pi_[0] = 0
        cuadro(float(x)).save(TMP / f"foto_{x}.jpg", quality=85)
    sys.exit()

proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-i", str(mezcla), "-map", "0:v", "-map", "1:a",
                         "-vf", f"fade=t=in:d=1.5,fade=t=out:st={TOTAL - 2.5:.2f}:d=2.5",
                         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(SALIDA)],
                        stdin=subprocess.PIPE)
for k in range(int(TOTAL * FPS)):
    proc.stdin.write(cuadro(k / FPS).tobytes())
    if k % (FPS * 60) == 0:
        print(f"  {k / FPS / 60:.0f} min", flush=True)
proc.stdin.close()
proc.wait()
print("Hecho:", SALIDA)
