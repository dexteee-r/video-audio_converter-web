# ytconverter — version web

Télécharge une vidéo (MP4/WEBM/MKV) ou un audio (MP3/M4A/FLAC/WAV/OGG) depuis YouTube,
TikTok, Instagram, Vimeo et 1000+ sites, depuis le navigateur. Même moteur que
l'[app desktop](../video-audio_converter) (yt-dlp + FFmpeg), servi par une API FastAPI.

## Fonctionnalités

- **Plusieurs liens à la fois** : on colle un ou plusieurs liens (ou on partage depuis une autre app),
  chacun devient une ligne ; « Tout télécharger » les traite un par un.
- **Options globales** : Vidéo/Audio, qualité, format, débit ; **sous-titres** (SRT) et **miniature** (JPG)
  en option — avec extras, le fichier livré est un **ZIP**.
- **Extrait début/fin** par ligne (ex. `1:20` → `2:45`), précis à l'image près.
- **Préférences mémorisées** dans le navigateur (qualité, format, options, langue).
- **Interface FR / EN** (langue du navigateur par défaut, bouton FR/EN).
- **Installable (PWA)** + **partage mobile** : « Partager vers ytconverter » depuis YouTube sur Android
  (Chrome, une fois le site installé). iOS : installable, mais Safari ne gère pas le partage vers une PWA.
- **Site public sans compte** : limitation par IP, quotas, en-têtes de sécurité (voir plus bas).

Pas d'historique ni de playlists pour l'instant (choix volontaire).

## Lancer en local

Prérequis : Python 3.9+ et **FFmpeg dans le PATH**.

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m uvicorn server.main:app --reload
```

Ouvrir http://localhost:8000. Docs interactives de l'API : lancer avec `YTC_ENABLE_DOCS=1`
puis http://localhost:8000/api/docs (désactivées par défaut).

Tests : `venv\Scripts\python.exe -m pytest` (39 tests, hors réseau).
Icônes PWA : `python tools/make_icons.py` (nécessite Pillow ; régénère `web/icons/`).

## Architecture

```
server/
  main.py        routes FastAPI, en-têtes de sécurité, sert web/ en statique
  downloader.py  wrapper yt-dlp (fetch_info, download, extrait, extras, ZIP) — aucune logique web
  jobs.py        file de jobs en mémoire, pool de threads, nettoyage TTL, plafond par IP
  ratelimit.py   limiteur à fenêtre glissante par IP
  security.py    validation d'URL (anti-SSRF)
  config.py      réglages via variables d'environnement
web/
  index.html  style.css  app.js  i18n.js     frontend vanilla, sans build
  manifest.webmanifest  sw.js  icons/        PWA
tools/make_icons.py   génère les icônes
tests/                pytest (faux téléchargeur, pas de réseau)
```

Flux : `POST /api/info` (aperçu) → `POST /api/jobs` → `GET /api/jobs/{id}` (progression, polling)
→ `GET /api/jobs/{id}/file`. Le front enchaîne les lignes **une par une**. Chaque job a son dossier
temporaire, supprimé après le TTL.

## API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health` | version yt-dlp, FFmpeg présent, options disponibles |
| POST | `/api/info` `{url}` | titre, miniature, durée, qualités |
| POST | `/api/jobs` | crée un téléchargement (202) |
| GET | `/api/jobs/{id}` | état : `queued` `downloading` `processing` `done` `error` |
| DELETE | `/api/jobs/{id}` | annule |
| GET | `/api/jobs/{id}/file` | télécharge le fichier terminé (média, ou ZIP si extras) |

Corps de `POST /api/jobs` : `url`, `kind` (`video`/`audio`), `quality` (hauteur max, 0 = max),
`format`, `bitrate`, `clip_start`/`clip_end` (secondes), `subtitles`, `sub_langs` (≤ 3 codes), `thumbnail`.

Les erreurs ont toujours la forme `{"detail": {"code": "..."}}` ; le front traduit les codes.
Codes `429` : `rate_limited` (avec `Retry-After`), `too_many_active`, `busy`.

## Configuration (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `YTC_DOWNLOAD_DIR` | `<tmp>/ytc-web` | dossier des fichiers générés |
| `YTC_JOB_TTL_SECONDS` | `1800` | durée de vie d'un fichier prêt |
| `YTC_MAX_CONCURRENT_JOBS` | `2` | téléchargements simultanés (global) |
| `YTC_MAX_QUEUED_JOBS` | `10` | jobs en attente avant de répondre 429 `busy` |
| `YTC_MAX_DURATION_SECONDS` | `10800` | durée max d'un média (0 = illimité) |
| `YTC_MAX_FILESIZE_MB` | `1024` | taille max d'un fichier (0 = illimité) |
| `YTC_RATE_INFO_PER_MIN` | `60` | analyses de lien par IP et par minute |
| `YTC_RATE_JOBS_PER_HOUR` | `60` | téléchargements créés par IP et par heure |
| `YTC_MAX_ACTIVE_PER_IP` | `2` | jobs en cours/en attente par IP |
| `YTC_ENABLE_DOCS` | *(vide)* | `1` = expose `/api/docs` |
| `YTC_COOKIES_FILE` | *(vide)* | fichier cookies Netscape pour yt-dlp |

## Avant la mise en production (site public)

**Protections déjà en place** : anti-SSRF (localhost, réseaux privés, metadata cloud refusés),
limitation par IP (analyses, créations, jobs actifs), plafonds durée/taille, nettoyage des fichiers,
CSP stricte + `nosniff` + `X-Frame-Options: DENY`, docs API désactivées.

**À faire / décider côté déploiement :**
- **IP réelle du visiteur** : derrière un reverse proxy, lancer uvicorn avec
  `--proxy-headers --forwarded-allow-ips=<ip du proxy>`, sinon toutes les requêtes ont l'IP du proxy
  et partagent le même quota (ou, pire, l'IP est falsifiable si on fait confiance à tout le monde).
- **HTTPS obligatoire** (le service worker, l'installation PWA et le partage mobile l'exigent) ;
  ajouter `Strict-Transport-Security` au niveau du proxy.
- **YouTube bloque souvent les IP de datacenter** (« Sign in to confirm you're not a bot »). Sur un site
  public, des cookies de **ton** compte (`YTC_COOKIES_FILE`) l'exposent à un bannissement : privilégier un
  proxy/IP résidentielle ou accepter que YouTube échoue parfois. À tester sur l'hébergeur choisi *avant*
  de s'engager sur lui.
- **Anti-bot** : le rate limiting limite les dégâts, pas les robots. Si le site est découvert, prévoir un
  CAPTCHA (ex. Cloudflare Turnstile) devant `/api/jobs`.
- **yt-dlp doit rester à jour** (sinon YouTube bride en 360p / casse) : rebuild régulier de l'image ou
  `pip install -U yt-dlp` planifié. **FFmpeg** doit être sur l'image/serveur.
- **Disque** : prévoir de la place pour `YTC_MAX_CONCURRENT_JOBS × YTC_MAX_FILESIZE_MB` + les fichiers
  gardés `YTC_JOB_TTL_SECONDS`.
- État des jobs et des quotas **en mémoire** : un seul process/instance. Pour plusieurs instances,
  passer à Redis (jobs + limiteur) ou limiter au niveau du proxy.
- **Juridique** : un site public de téléchargement expose son exploitant (droit d'auteur, CGU des
  plateformes). Les mentions légales / une politique de retrait sont à ta charge.
