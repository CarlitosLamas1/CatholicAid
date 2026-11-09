# Canal en portugués (Brasil) · preparado, sin activar

Brasil es el país con más católicos del mundo. El canal en portugués seguiría el mismo modelo que el inglés:
mismo vídeo cada día, mismas imágenes (no se pinta nada nuevo), mismas voces por personaje con acento brasileño
y su propio cupo gratuito de voz.

## Ya preparado (09/11/2026)
- Textos del vídeo en portugués (`TXT["pt"]` en `proceso/evangelio.py`): «Palavra da Salvação», el cierre
  «Siga-nos para ouvir o Evangelho todos os dias» y las instrucciones de lectura para las voces.
- Ajustes en `config/personajes.json` → `pt` (con `"activo": false`): acento, página del Evangelio del día de
  Vatican News en portugués, nombres de las listas, hashtags, cuenta de Instagram prevista y reflexión de reserva.
- Sufijo de archivos `-pt` (episodios/AAAA-MM-DD-pt.json, revisiones/…-pt.json, release `pt-AAAA-MM-DD`).

## Lo que tiene que hacer Carlos (una sola vez)
1. **YouTube**: crear el canal «CatolicAid Português» con la misma cuenta (catolicolamas@gmail.com), igual que el
   inglés (youtube.com → foto → «Crear un canal» / cuenta de marca).
2. **Instagram**: crear @catolicaid_pt_official como cuenta profesional (Creador) y vincularla a una página de
   Facebook nueva «CatolicAid Português». Después, una autorización en `docs/instagram.html` guarda todas las cuentas.
3. Avisar al gestor. El gestor conecta YouTube (workflow «Conectar YouTube» con `CANAL=pt`) y hace el resto.

## Decisión pendiente: qué Biblia usar
En español usamos Torres Amat (1836) y en inglés la World English Bible: dos textos **de dominio público**.
En portugués:
- **Padre Antônio Pereira de Figueiredo** (1778–1790): católica y de dominio público, pero no hay una edición
  digital limpia (solo escaneos antiguos de 1802–1821). Habría que pasarla a texto (los 4 evangelios, con OCR y
  revisión), como se hizo con el Torres Amat, y actualizar la ortografía.
- **Matos Soares** (1932, la católica clásica): aún con derechos.
- Las traducciones litúrgicas actuales (CNBB, Ave-Maria, la de Vatican News): con derechos; no se pueden usar.
- Traducciones libres modernas de eBible.org (p. ej. `porbr2018`): hay que confirmar licencia y que el texto de los
  evangelios sea aceptable para un público católico.
Recomendación del gestor: Figueiredo con ortografía actual (fiel y católica, como Torres Amat). Se puede preparar
en paralelo mientras se crean las cuentas.

## Trabajo de código que falta al activarlo
- `--idioma pt` en `evangelio.py` (texto, cita del día de Vatican News PT, títulos y descripción en portugués).
- `publicar.py`, `reloj.py`, `avisos.py`, `youtube_tareas.py`, `instagram.py`, `resumen_semanal.py`:
  hoy recorren «es» y «en»; añadir «pt» con las mismas reglas que el inglés.
- Workflow «Evangelio diario (portugués)» copiado del inglés y criterio del revisor `proceso/criterio-revision-pt.md`
  (PASO 4c de la rutina «Revisor diario»).
- Primera semana: publicar en privado y revisar a mano antes de programar (como el inglés).
