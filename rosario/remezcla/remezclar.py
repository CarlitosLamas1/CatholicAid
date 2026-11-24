"""Rehace el audio de los cuatro rosarios sin «Clair de lune» (reclamación de Content ID del 24/11/2026).

La imagen no cambia: se copia tal cual (-c:v copy). Voz: la pista de voz original de cada rosario (voz-<clave>.flac);
música: las piezas ya publicadas sin problemas, con la misma mezcla que el montaje (la voz baja la música).
Entrada y salida en rosario/subir/archivos/ (release rosario-videos)."""
import pathlib
import subprocess

import imageio_ffmpeg

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ARCH = RAIZ / "rosario" / "subir" / "archivos"
FF = imageio_ffmpeg.get_ffmpeg_exe()
HZ = 48000
LISTA = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
         "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
         "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._55.ogg",
         "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg",
         "Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg"]


def duracion(ruta):
    r = subprocess.run([FF, "-i", str(ruta)], capture_output=True, text=True)
    h, m, s = r.stderr.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


for clave in ("gloriosos", "luminosos", "dolorosos", "gozosos"):
    video, voz = ARCH / f"rosario-{clave}.mp4", ARCH / f"voz-{clave}.flac"
    total = duracion(video)
    entradas, filtro = [], ""
    for j, nombre in enumerate(LISTA):
        entradas += ["-i", str(RAIZ / "musica" / nombre)]
        filtro += f"[{j + 2}:a]aformat=sample_rates={HZ}:channel_layouts=stereo[m{j}];"
    for j in range(1, len(LISTA)):
        filtro += f"[{'m0' if j == 1 else f'x{j - 1}'}][m{j}]acrossfade=d=5:c1=tri:c2=tri[x{j}];"
    filtro += (f"[x{len(LISTA) - 1}]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,volume=0.28,afade=t=in:d=3,"
               f"afade=t=out:st={total - 6:.2f}:d=6[m];"
               f"[1:a]aformat=sample_rates={HZ}:channel_layouts=stereo,asplit[v][sc];"
               "[m][sc]sidechaincompress=threshold=0.015:ratio=5:attack=250:release=1200:makeup=1[md];"
               "[v][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    salida = ARCH / f"nuevo-{clave}.mp4"
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(video), "-i", str(voz), *entradas,
                    "-filter_complex", filtro, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", str(HZ), "-t", f"{total:.3f}", "-movflags", "+faststart", str(salida)],
                   check=True)
    r = subprocess.run([FF, "-i", str(salida), "-af", "ebur128", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    lufs = r.stderr.rsplit("I:", 1)[1].split("LUFS")[0].strip()
    print(f"{clave}: {duracion(salida):.1f} s (original {total:.1f} s) · {lufs} LUFS · {salida.stat().st_size / 1e6:.0f} MB",
          flush=True)
