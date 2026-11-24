"use strict";

/* Tiny i18n: French + English. Language = saved choice, else the browser's.
 * Static text uses data-i18n / data-i18n-ph / data-i18n-title / data-i18n-aria;
 * dynamic text calls I18n.t(key, {vars}). */
(function () {
  const dict = {
    fr: {
      "meta.title": "ytconverter — télécharge vidéo et audio, sans pub",
      "meta.desc": "Colle un ou plusieurs liens YouTube, TikTok, Instagram, Vimeo… et récupère la vidéo (MP4) ou l'audio (MP3). Sans pub, sans compte.",

      "hero.l1": "Colle un lien.",
      "hero.l2": "Récupère le fichier",
      "hero.sub": "YouTube, TikTok, Instagram, Vimeo et 1000+ sites. Vidéo en MP4, audio en MP3 — sans pub, sans compte. Tu peux coller plusieurs liens d'un coup.",

      "paste.label": "Lien du média (un ou plusieurs)",
      "paste.ph": "https://www.youtube.com/watch?v=…",
      "paste.paste": "Coller",
      "paste.paste_title": "Coller depuis le presse-papiers",
      "paste.add": "Ajouter",

      "status.connecting": "connexion…",
      "status.down": "serveur injoignable",
      "status.ok": "yt-dlp {v} · ffmpeg ok",
      "status.noffmpeg": "yt-dlp {v} · ffmpeg absent",
      "pwa.install": "Installer",

      "opt.type": "Type de fichier",
      "opt.video": "Vidéo",
      "opt.audio": "Audio",
      "opt.quality": "Qualité",
      "opt.quality_max": "Maximale",
      "opt.format": "Format",
      "opt.bitrate": "Débit",
      "opt.subs": "Sous-titres",
      "opt.thumb": "Miniature",

      "item.analyzing": "Analyse du lien…",
      "item.queued": "En attente",
      "item.downloading": "Téléchargement",
      "item.processing": "Finalisation (fusion / conversion)…",
      "item.done": "Prêt · {size} · disponible {min} min",
      "item.remove": "Retirer",
      "item.clip": "Extrait début/fin",
      "item.save": "Enregistrer le fichier",
      "item.retry": "Réessayer",
      "item.redo": "Télécharger à nouveau (autres options)",
      "item.clip_summary": "extrait {range}",
      "item.eta": "reste {eta}",

      "clip.start": "Début",
      "clip.end": "Fin",
      "clip.hint": "Format 1:20 ou 1:02:03. Laisse vide pour garder le début ou la fin.",
      "clip.err_format": "Temps invalide (ex. 1:20).",
      "clip.err_order": "La fin doit être après le début.",
      "clip.err_range": "Le début dépasse la durée du média.",
      "clip.fix": "Corrige les extraits signalés avant de lancer.",

      "run.one": "Télécharger",
      "run.many": "Tout télécharger ({n})",
      "run.running": "Téléchargement {i}/{n}",
      "run.analyzing": "Analyse en cours…",
      "run.done": "Terminé",
      "run.stop": "Arrêter",
      "run.clear": "Vider",
      "run.multi_hint": "Les fichiers s'enregistrent un par un. Si le navigateur le demande, autorise les téléchargements multiples.",

      "feat.1.t": "Sans pub",
      "feat.1.d": "Pas de pop-up, pas de redirection.",
      "feat.2.t": "Qualité d'origine",
      "feat.2.d": "Jusqu'à la 4K quand la source le permet.",
      "feat.3.t": "1000+ sites",
      "feat.3.d": "Propulsé par yt-dlp et FFmpeg.",
      "foot.legal": "Respecte le droit d'auteur et les conditions des plateformes : télécharge uniquement ce que tu as le droit de copier.",

      "err.too_many_items": "Maximum {max} liens à la fois.",
      "err.no_url": "Aucun lien valide trouvé.",
      "err.invalid_url": "Ce lien n'est pas valide.",
      "err.forbidden_host": "Cette adresse n'est pas autorisée.",
      "err.unresolvable_host": "Impossible de joindre ce site.",
      "err.unsupported_url": "Ce site ou ce lien n'est pas pris en charge.",
      "err.too_long": "Ce média est trop long pour être traité.",
      "err.too_large": "Ce fichier est trop volumineux.",
      "err.no_media": "Aucun média trouvé sur cette page.",
      "err.auth_required": "Le site demande une connexion ou bloque le serveur. Réessaie plus tard.",
      "err.private_media": "Ce média est privé ou réservé à certains comptes.",
      "err.unavailable": "Ce média n'est plus disponible.",
      "err.extract_failed": "Impossible d'analyser ce lien.",
      "err.ffmpeg_missing": "La conversion est indisponible sur le serveur (FFmpeg manquant).",
      "err.busy": "Le serveur est occupé. Réessaie dans un instant.",
      "err.rate_limited": "Trop de requêtes. Patiente un peu avant de réessayer.",
      "err.too_many_active": "Tu as déjà des téléchargements en cours. Attends qu'ils finissent.",
      "err.cancelled": "Téléchargement annulé.",
      "err.internal_error": "Erreur interne. Réessaie.",
      "err.invalid_option": "Option invalide.",
      "err.job_not_found": "Ce téléchargement a expiré. Relance-le.",
      "err.not_ready": "Le fichier n'est pas encore prêt.",
      "err.network": "Connexion au serveur impossible.",
      "err.unknown": "Une erreur est survenue.",
    },

    en: {
      "meta.title": "ytconverter — download video and audio, no ads",
      "meta.desc": "Paste one or more YouTube, TikTok, Instagram, Vimeo… links and get the video (MP4) or audio (MP3). No ads, no account.",

      "hero.l1": "Paste a link.",
      "hero.l2": "Get the file",
      "hero.sub": "YouTube, TikTok, Instagram, Vimeo and 1000+ sites. Video as MP4, audio as MP3 — no ads, no account. You can paste several links at once.",

      "paste.label": "Media link (one or several)",
      "paste.ph": "https://www.youtube.com/watch?v=…",
      "paste.paste": "Paste",
      "paste.paste_title": "Paste from clipboard",
      "paste.add": "Add",

      "status.connecting": "connecting…",
      "status.down": "server unreachable",
      "status.ok": "yt-dlp {v} · ffmpeg ok",
      "status.noffmpeg": "yt-dlp {v} · ffmpeg missing",
      "pwa.install": "Install",

      "opt.type": "File type",
      "opt.video": "Video",
      "opt.audio": "Audio",
      "opt.quality": "Quality",
      "opt.quality_max": "Maximum",
      "opt.format": "Format",
      "opt.bitrate": "Bitrate",
      "opt.subs": "Subtitles",
      "opt.thumb": "Thumbnail",

      "item.analyzing": "Analyzing link…",
      "item.queued": "Waiting",
      "item.downloading": "Downloading",
      "item.processing": "Finishing (merging / converting)…",
      "item.done": "Ready · {size} · available {min} min",
      "item.remove": "Remove",
      "item.clip": "Trim start/end",
      "item.save": "Save file",
      "item.retry": "Retry",
      "item.redo": "Download again (other options)",
      "item.clip_summary": "clip {range}",
      "item.eta": "{eta} left",

      "clip.start": "Start",
      "clip.end": "End",
      "clip.hint": "Format 1:20 or 1:02:03. Leave empty to keep the start or the end.",
      "clip.err_format": "Invalid time (e.g. 1:20).",
      "clip.err_order": "End must be after start.",
      "clip.err_range": "Start is beyond the media length.",
      "clip.fix": "Fix the flagged clips before starting.",

      "run.one": "Download",
      "run.many": "Download all ({n})",
      "run.running": "Downloading {i}/{n}",
      "run.analyzing": "Analyzing…",
      "run.done": "Done",
      "run.stop": "Stop",
      "run.clear": "Clear",
      "run.multi_hint": "Files are saved one by one. If your browser asks, allow multiple downloads.",

      "feat.1.t": "No ads",
      "feat.1.d": "No pop-ups, no redirects.",
      "feat.2.t": "Original quality",
      "feat.2.d": "Up to 4K when the source allows it.",
      "feat.3.t": "1000+ sites",
      "feat.3.d": "Powered by yt-dlp and FFmpeg.",
      "foot.legal": "Respect copyright and each platform's terms: only download what you are allowed to copy.",

      "err.too_many_items": "Maximum {max} links at once.",
      "err.no_url": "No valid link found.",
      "err.invalid_url": "This link is not valid.",
      "err.forbidden_host": "This address is not allowed.",
      "err.unresolvable_host": "Cannot reach this site.",
      "err.unsupported_url": "This site or link is not supported.",
      "err.too_long": "This media is too long to process.",
      "err.too_large": "This file is too large.",
      "err.no_media": "No media found on this page.",
      "err.auth_required": "The site requires a login or is blocking the server. Try again later.",
      "err.private_media": "This media is private or restricted.",
      "err.unavailable": "This media is no longer available.",
      "err.extract_failed": "Could not analyze this link.",
      "err.ffmpeg_missing": "Conversion is unavailable on the server (FFmpeg missing).",
      "err.busy": "The server is busy. Try again in a moment.",
      "err.rate_limited": "Too many requests. Wait a little before retrying.",
      "err.too_many_active": "You already have downloads in progress. Wait for them to finish.",
      "err.cancelled": "Download cancelled.",
      "err.internal_error": "Internal error. Try again.",
      "err.invalid_option": "Invalid option.",
      "err.job_not_found": "This download has expired. Start it again.",
      "err.not_ready": "The file is not ready yet.",
      "err.network": "Cannot reach the server.",
      "err.unknown": "Something went wrong.",
    },
  };

  const STORAGE_KEY = "ytc.lang";
  let lang = detect();

  function detect() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && dict[saved]) return saved;
    } catch { /* storage blocked: fall through */ }
    return (navigator.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
  }

  function t(key, vars) {
    let s = (dict[lang] && dict[lang][key]) ?? dict.en[key] ?? key;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    return s;
  }

  function apply(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
    root.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
    root.querySelectorAll("[data-i18n-title]").forEach((n) => { n.title = t(n.dataset.i18nTitle); });
    root.querySelectorAll("[data-i18n-aria]").forEach((n) => { n.setAttribute("aria-label", t(n.dataset.i18nAria)); });
    if (root === document) {
      document.documentElement.lang = lang;
      document.title = t("meta.title");
      const meta = document.querySelector('meta[name="description"]');
      if (meta) meta.content = t("meta.desc");
      document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === lang));
    }
  }

  function setLang(next) {
    if (!dict[next]) return;
    lang = next;
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
    apply();
  }

  window.I18n = { t, apply, setLang, get lang() { return lang; } };
})();
