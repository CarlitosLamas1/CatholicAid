# Revisión del vídeo en INGLÉS (canal CatolicAid English)

Mismo criterio que el español, con estas diferencias. El revisor escribe `revisiones/AAAA-MM-DD-en.json`
(ese push lanza «Publicar revisado» con `AAAA-MM-DD-en`). Sin OK no se publica el inglés; el español no se ve afectado.

## Qué leer
- Registro: `episodios/AAAA-MM-DD-en.json` (campos iguales al español + `idioma: "en"`, `libro`, `cita_es`).
- Vídeo: release `en-AAAA-MM-DD` (no `tiktok-…`). No hay TikTok en inglés.
- Si el registro tiene `"estado": "fallido"` (p. ej. sin cupo de Gemini), NO hay vídeo: no escribas revisión.

## Puntos
1. **fidelidad**: `texto_evangelio` = texto de `biblia/web/revisada/<libro>.json` si el versículo está, si no
   `biblia/web/<libro>.json` (World English Bible, Catholic), versículos de `cita_es` (la MISMA cita que el
   español del día, `biblia/citas.json`). Solo pueden variar: la introducción (`_inicios`, por defecto
   «At that time,»), la primera letra en minúscula tras ella, las comillas “ ” equilibradas y los versículos que la
   WEB no trae (p. ej. Lucas 17,36). La unión de los fragmentos debe ser idéntica al texto (sin comillas ni espacios).
2. **voces**: palabras de Jesús en `jesus`, narración en `narrador`, etc. Comillas ‘ ’ dentro de un discurso:
   sigue el mismo personaje. Los apóstrofos (don’t, Father’s) NO son comillas.
3. **frase_clave**: literal, de Jesús, en inglés, 3–12 palabras.
4. **reflexion**: en inglés americano, 1–2 frases (≤ 35 palabras) o una pregunta, de tú (you), fiel a la doctrina,
   sin comillas, sin política. No es parte del Evangelio.
5. **tecnica**: duración ≤ 180 s, `lufs` entre -15 y -13. Audio: 10–20 caracteres por segundo por fragmento
   (el inglés es algo más rápido que el español; < 8 o > 22 es anómalo).
6. **imagenes**: las del día del español (`dias/AAAA-MM-DD_eN.jpg`) o de la biblioteca; nunca imágenes nuevas.
7. **metadatos**: título «“Frase” | Gospel of the day, Nov 8 (Luke 16:1-8)» (≤ 100 caracteres), cita en formato
   inglés, todo en inglés, `gancho_segundos` 1,5 o 2,8, `subtitulos_karaoke: true`.

## JSON (igual que en español)
```json
{"fecha": "AAAA-MM-DD", "idioma": "en", "ok": true, "por": "revisor", "generado": "<el del registro -en>",
 "revisado": "<ahora>", "motivos": [], "avisos": [], "puntos": {"fidelidad": "✅ …", "voces": "✅ …", "frase_clave": "✅ …",
 "reflexion": "✅ …", "tecnica": "✅ …", "audio": "✅ …", "imagenes": "✅ …", "metadatos": "✅ …"}}
```

## Qué añadir a la rutina «CatholicAid · Revisor diario» (lo edita Carlos en claude.ai)
Añadir al final del paso de revisión:
> Después del español, revisa también el vídeo en inglés de mañana si existe `episodios/AAAA-MM-DD-en.json` con
> `"revision": "pendiente"` y no hay `revisiones/AAAA-MM-DD-en.json` con el mismo `generado`. Sigue
> `proceso/criterio-revision-en.md` y escribe `revisiones/AAAA-MM-DD-en.json`. Revisa siempre primero el español:
> el inglés nunca debe retrasarlo.
