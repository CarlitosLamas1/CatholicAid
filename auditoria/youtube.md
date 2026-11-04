# Auditoría de la API de YouTube · guía para Carlos

**Objetivo:** que Google permita que los vídeos subidos por la app salgan **públicos** (o programados) sin tener que publicarlos a mano. Se hace **una sola vez**. Google suele tardar entre 1 y 4 semanas en responder.

Web del proyecto (ya publicada):
- Inicio: https://carlitoslamas1.github.io/CatholicAid/
- Privacidad: https://carlitoslamas1.github.io/CatholicAid/privacidad.html
- Condiciones: https://carlitoslamas1.github.io/CatholicAid/condiciones.html

---

## Paso 1 · Completar la pantalla de consentimiento (5 min)
En https://console.cloud.google.com, con **catolicolamas@gmail.com**, en el proyecto de la app **CatolicAidYoutube**:

1. **Google Auth Platform → Branding (Desarrollo de la marca):**
   - Página principal de la aplicación: `https://carlitoslamas1.github.io/CatholicAid/`
   - Política de privacidad: `https://carlitoslamas1.github.io/CatholicAid/privacidad.html`
   - Condiciones del servicio: `https://carlitoslamas1.github.io/CatholicAid/condiciones.html`
   - Dominios autorizados: `carlitoslamas1.github.io`
   - **No subas logotipo** (obligaría a una verificación de marca extra).
   - Guarda.
2. **Google Auth Platform → Público (Audience):** el estado debe ser **«En producción»**. Si pone «Prueba», pulsa **«Publicar app»** y confirma.
3. Apunta el **número de proyecto**: aparece en la página de inicio del proyecto («Número del proyecto», solo dígitos). Lo pide el formulario.

## Paso 2 · Enviar el formulario de auditoría (10 min)
Formulario oficial: **https://support.google.com/youtube/contact/yt_api_form**

Elige **«I would like to request an audit / quota extension»** (auditoría) y rellena con lo siguiente. Puedes copiar y pegar; Google prefiere las respuestas en inglés.

| Campo | Qué poner |
|---|---|
| Name / Email | Carlos Lamas · catolicolamas@gmail.com |
| Organization name | CatolicAid |
| Organization website | https://carlitoslamas1.github.io/CatholicAid/ |
| Organization address / country | (tu dirección) · Spain |
| Google Cloud project number | (el número del paso 1.3) |
| API client name | CatolicAidYoutube |
| Is the API client available to the public? | **No — internal use only** |
| Who uses it? | Only the owner, for the owner's own channel |
| YouTube channel(s) | https://www.youtube.com/channel/UCeQ2e1rojxsa9UyrHWcVEVA |
| Privacy policy URL | https://carlitoslamas1.github.io/CatholicAid/privacidad.html |
| Terms of service URL | https://carlitoslamas1.github.io/CatholicAid/condiciones.html |
| API services / scopes used | YouTube Data API v3 · `youtube.upload`, `youtube.readonly` |
| Quota requested | Current default quota (10,000 units/day) is enough |

**Description of the use case (pégalo tal cual):**

> CatolicAid is a non-profit Catholic project that publishes one short video per day on its own YouTube channel with the Gospel of the day, read with several voices over devotional paintings. CatolicAidYoutube is an internal, server-side tool (a scheduled GitHub Actions job) that prepares each video and uploads it to our own channel using videos.insert, setting status.publishAt to schedule it for 07:00 Europe/Madrid and status.containsSyntheticMedia = true, because voices and some images are AI-generated. It also reads our own channel's basic data (channels.list, mine=true) to confirm the upload. The tool is used only by the channel owner, authorized once via OAuth; it is not offered to other users, does not access any third-party account, and does not store or share any YouTube user data. We request the audit so that uploaded videos are not locked as private, since the project is unverified.

**How do you use YouTube API data?**

> We only use the IDs of the videos we upload and our own channel's ID, title and public statistics, to check that each daily video has been published. No data from other users is accessed, stored, combined or shared.

Si piden capturas o un vídeo de demostración: el gestor puede preparar uno (pídeselo).

## Paso 3 · Esperar
Google responde por correo a catolicolamas@gmail.com. Si hacen preguntas, reenvía el correo al gestor y te prepara la respuesta. Mientras tanto, los vídeos se suben programados pero **privados**: publícalos con un clic en YouTube Studio → Contenido.
