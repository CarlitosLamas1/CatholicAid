#!/usr/bin/env python3
"""CatolicAid · Iconos por idioma: a partir del icono base pintado (Evangelio con las páginas vacías):
- suaviza la saturación (26 % menos, como el icono elegido),
- tiñe nubes y cielo con el color del idioma (es carmín suave, en azul, pt verde; sin colores de bandera: el público es de toda América) sin tocar el oro ni la cruz,
- escribe el código del idioma (E | S, E | N, P | T) en las dos páginas del libro, como tinta sobre papel.
Uso: python3 proceso/icono_idiomas.py base.png salida_dir
Genera salida_dir/{es,en,pt}.png (1024) y los tamaños de cada plataforma en salida_dir/{es,en,pt}/.
"""
import colorsys
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

# matiz inicial, matiz final, ganancia de saturación, ganancia de brillo
COLORES = {"es": (352, 364, 2.0, 1.1), "en": (205, 238, 1.15, 1.0), "pt": (140, 182, 1.15, 1.0)}
LETRAS = {"es": ("E", "S"), "en": ("E", "N"), "pt": ("P", "T")}
FUENTE = "/System/Library/Fonts/Supplemental/Baskerville.ttc"   # capitales clásicas de libro; el aspecto de pincel lo da escribir()
INDICE = 4                                                        # Baskerville Bold
TINTA = (128, 72, 26)
# centro de cada página y giro (grados) en el icono de 1024; ajustar si cambia la composición del libro
PAGINAS = [((345, 760), 4.0), ((680, 754), -2.0)]   # en el dibujo sin reducir


ESCALA = 0.90   # el icono se reduce un poco para que el recorte en círculo no corte las esquinas del libro


def preparar(base):
    """Reduce el dibujo (ESCALA) sobre su propio fondo ampliado y desenfocado, y quita un 26 % de saturación."""
    im = base.convert("RGB")
    fondo = im.filter(ImageFilter.GaussianBlur(45))
    n = int(1024 * ESCALA)
    mascara = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mascara).rectangle((45, 45, n - 45, n - 45), fill=255)
    fondo.paste(im.resize((n, n), Image.LANCZOS), ((1024 - n) // 2, (1024 - n) // 2), mascara.filter(ImageFilter.GaussianBlur(30)))
    return ImageEnhance.Brightness(ImageEnhance.Color(fondo).enhance(0.70)).enhance(1.03)


def tinte(im, lo, hi, gs, gv):
    sm = im.resize((512, 512), Image.LANCZOS)
    out = sm.copy()
    po, px = out.load(), sm.load()
    for y in range(512):
        for x in range(512):
            r, g, b = px[x, y]
            hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            deg = hh * 360
            if s > 0.10 and 185 <= deg <= 360:
                nd = (lo + (deg - 185) / 175 * (hi - lo)) % 360
                r2, g2, b2 = colorsys.hsv_to_rgb(nd / 360, min(1, s * gs), min(1, v * gv))
                po[x, y] = (int(r2 * 255), int(g2 * 255), int(b2 * 255))
    return out.resize((1024, 1024), Image.LANCZOS)


def escribir(im, letras, altura=150):
    """Letras como pintadas con pincel fino en el papel: tinta ámbar translúcida, borde más oscuro donde se seca,
    contorno algo irregular y densidad que sigue al grano del papel (no es texto pegado)."""
    fuente = ImageFont.truetype(FUENTE, int(altura * 1.35), index=INDICE)
    capa = Image.new("L", im.size, 0)
    for letra, (c0, giro) in zip(letras, PAGINAS):
        centro = (int(512 + (c0[0] - 512) * ESCALA), int(512 + (c0[1] - 512) * ESCALA))
        t = Image.new("L", (400, 400), 0)
        d = ImageDraw.Draw(t)
        b = d.textbbox((0, 0), letra, font=fuente)
        d.text((200 - (b[2] - b[0]) // 2 - b[0], 200 - (b[3] - b[1]) // 2 - b[1]), letra, font=fuente, fill=255)
        t = t.rotate(giro, resample=Image.BICUBIC)
        capa.paste(ImageChops.lighter(capa.crop((centro[0] - 200, centro[1] - 200, centro[0] + 200, centro[1] + 200)), t),
                   (centro[0] - 200, centro[1] - 200))
    # contorno irregular: suavizar, sumar ruido de baja frecuencia y volver a cortar
    ruido = Image.effect_noise(im.size, 48).filter(ImageFilter.GaussianBlur(2.0))
    capa = ImageChops.subtract(ImageChops.add(capa.filter(ImageFilter.GaussianBlur(2.2)), ruido, 1.0, -128), Image.new("L", im.size, 0))
    capa = capa.point(lambda v: 255 if v > 118 else (0 if v < 96 else int((v - 96) / 22 * 255))).filter(ImageFilter.GaussianBlur(0.9))
    borde = ImageChops.subtract(capa, capa.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(2.5)))   # donde se seca
    papel = im.convert("L").filter(ImageFilter.GaussianBlur(1.5))
    grano = papel.point(lambda v: max(150, min(255, int(130 + v * 0.5))))                 # el papel más oscuro retiene más tinta
    densidad = ImageChops.multiply(ImageChops.add(capa.point(lambda v: int(v * 0.62)), borde.point(lambda v: int(v * 0.50))), grano)
    densidad = densidad.point(lambda v: min(255, int(v * 255 / 220)))
    sobre = ImageChops.multiply(im, Image.new("RGB", im.size, TINTA))
    out = im.copy()
    out.paste(sobre, (0, 0), densidad)
    return out


def redondo(im):
    """Recorte circular (con borde suave) y esquinas transparentes: el cuadrado de sobra no hace falta."""
    g = 4
    mascara = Image.new("L", (im.width * g, im.height * g), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, im.width * g - 1, im.height * g - 1), fill=255)
    mascara = mascara.resize(im.size, Image.LANCZOS)
    out = im.convert("RGBA")
    out.putalpha(mascara)
    return out


def main():
    base, destino = Image.open(sys.argv[1]), Path(sys.argv[2])
    destino.mkdir(parents=True, exist_ok=True)
    pre = preparar(base)
    neutro = redondo(pre)
    neutro.save(destino / "neutro.png", optimize=True)
    pre.convert("RGB").save(destino / "neutro-cuadrado-1024.jpg", quality=92, optimize=True)   # solo para el portal de TikTok (pide cuadrado)
    for idioma, (lo, hi, gs, gv) in COLORES.items():
        base_color = tinte(pre, lo, hi, gs, gv)
        im = redondo(escribir(base_color, LETRAS[idioma]))
        im.save(destino / f"{idioma}.png", optimize=True)
        carpeta = destino / idioma
        carpeta.mkdir(exist_ok=True)
        im.save(carpeta / "icono-1024.png", optimize=True)
        for nombre, s in (("youtube-800", 800), ("instagram-1080", 1080)):
            im.resize((s, s), Image.LANCZOS).save(carpeta / f"{nombre}.png", optimize=True)


if __name__ == "__main__":
    main()
