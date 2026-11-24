"""yt-dlp wrapper: metadata extraction and file download.

Pure functions, no web or job logic here. Errors are raised as
DownloaderError(code, detail) so the API layer can map them to HTTP responses.
"""

import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional, Sequence

import yt_dlp
from yt_dlp.utils import DownloadCancelled, download_range_func

from server import config

STANDARD_HEIGHTS = (144, 240, 360, 480, 720, 1080, 1440, 2160)
VIDEO_FORMATS = ("mp4", "webm", "mkv")
AUDIO_FORMATS = ("mp3", "m4a", "flac", "wav", "ogg")
LOSSLESS_AUDIO = ("flac", "wav")
AUDIO_BITRATES = (128, 192, 256, 320)
# UI label -> yt-dlp codec name
_AUDIO_CODEC = {"ogg": "vorbis"}

_TEMP_SUFFIXES = {".part", ".ytdl", ".temp"}

ProgressCb = Callable[[dict], None]


class DownloaderError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ytdlp_version() -> str:
    return yt_dlp.version.__version__


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # we report progress through hooks, not stdout
        "noplaylist": True,
        "socket_timeout": 20,
    }
    if config.COOKIES_FILE:
        opts["cookiefile"] = config.COOKIES_FILE
    return opts


def _format_duration(seconds) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _single_entry(info: dict) -> dict:
    """If yt-dlp returned a playlist, describe its first entry."""
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise DownloaderError("no_media")
        return entries[0]
    return info


def _check_duration(info: dict) -> None:
    limit = config.MAX_DURATION_SECONDS
    duration = info.get("duration")
    if limit and duration and duration > limit:
        raise DownloaderError("too_long", str(limit))


def _map_error(exc: Exception) -> DownloaderError:
    """Translate a yt-dlp failure into a stable error code for the UI."""
    text = str(exc)
    low = text.lower()
    if "max-filesize" in low:
        return DownloaderError("too_large", text)
    if "unsupported url" in low:
        return DownloaderError("unsupported_url", text)
    if "sign in" in low or "confirm you" in low or "bot" in low:
        return DownloaderError("auth_required", text)
    if "private" in low or "members-only" in low or "login" in low:
        return DownloaderError("private_media", text)
    if "unavailable" in low or "removed" in low or "not available" in low:
        return DownloaderError("unavailable", text)
    return DownloaderError("extract_failed", text)


def fetch_info(url: str) -> dict:
    """Metadata for the preview card. Never downloads anything."""
    opts = {**_base_opts(), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = _single_entry(ydl.extract_info(url, download=False))
    except DownloaderError:
        raise
    except Exception as exc:  # noqa: BLE001 - any extractor failure is a user-facing error
        raise _map_error(exc) from exc

    _check_duration(info)

    formats = info.get("formats") or []
    heights = sorted({f["height"] for f in formats if f.get("height") in STANDARD_HEIGHTS})
    has_video = bool(heights) or any(f.get("vcodec") not in (None, "none") for f in formats)
    has_audio = any(f.get("acodec") not in (None, "none") for f in formats)

    return {
        "title": info.get("title") or url,
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": _format_duration(info.get("duration")),
        "duration_seconds": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "site": info.get("extractor_key") or "",
        "qualities": heights,
        "has_video": has_video,
        "has_audio": has_audio,
    }


def _video_selector(height: int, container: str) -> str:
    cap = f"[height<={height}]" if height else ""
    if container == "mp4":
        # Prefer H.264/AAC streams: they play everywhere (phones, QuickTime, TVs).
        return (
            f"bv*{cap}[ext=mp4]+ba[ext=m4a]"
            f"/bv*{cap}+ba/b{cap}/b"
        )
    if container == "webm":
        return f"bv*{cap}[ext=webm]+ba[ext=webm]/bv*{cap}+ba/b{cap}/b"
    return f"bv*{cap}+ba/b{cap}/b"


def _make_hooks(on_progress: ProgressCb, expected_streams: int):
    """Build yt-dlp hooks that report one smooth 0-100 progress for the whole job.

    yt-dlp downloads video and audio as separate streams, each going 0->100%.
    We track which stream we are on so the bar never jumps backwards.
    """
    state = {"done": 0, "current": None}

    def progress_hook(d: dict) -> None:
        stream = (d.get("info_dict") or {}).get("format_id")
        if state["current"] is None:
            state["current"] = stream
        elif stream != state["current"]:
            state["done"] += 1
            state["current"] = stream

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes") or 0) / total if total else 0.0
            overall = (state["done"] + min(frac, 1.0)) / max(expected_streams, 1)
            on_progress({
                "state": "downloading",
                "progress": round(min(overall, 0.99) * 100, 1),
                "speed": d.get("speed"),
                "eta": d.get("eta"),
            })

    def postprocessor_hook(d: dict) -> None:
        if d["status"] == "started":
            on_progress({"state": "processing", "progress": 99.0, "speed": None, "eta": None})

    return progress_hook, postprocessor_hook


def download(
    url: str,
    kind: str,
    out_dir: Path,
    *,
    height: int = 1080,
    container: str = "mp4",
    audio_format: str = "mp3",
    bitrate: int = 192,
    clip_start: Optional[float] = None,
    clip_end: Optional[float] = None,
    subtitles: bool = False,
    sub_langs: Sequence[str] = (),
    thumbnail: bool = False,
    on_progress: Optional[ProgressCb] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> dict:
    """Download one media into out_dir. Returns {filepath, title}.

    If extras were requested (subtitles, thumbnail) the result is a ZIP holding
    the media and the extras; otherwise it is the media file itself.
    """
    on_progress = on_progress or (lambda _d: None)
    out_dir.mkdir(parents=True, exist_ok=True)

    clipping = bool(clip_start) or clip_end is not None   # start=0 alone means "no cut"
    needs_ffmpeg = kind == "audio" or clipping or thumbnail or subtitles
    if needs_ffmpeg and not ffmpeg_available():
        raise DownloaderError("ffmpeg_missing")

    opts = {
        **_base_opts(),
        "outtmpl": str(out_dir / "%(title).150B.%(ext)s"),
        "windowsfilenames": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    if config.MAX_FILESIZE_MB:
        opts["max_filesize"] = config.MAX_FILESIZE_MB * 1024 * 1024

    postprocessors = []
    if kind == "audio":
        pp = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": _AUDIO_CODEC.get(audio_format, audio_format),
        }
        if audio_format not in LOSSLESS_AUDIO:
            pp["preferredquality"] = str(bitrate)
        opts["format"] = "bestaudio/best"
        postprocessors.append(pp)
        expected_streams = 1
    else:
        opts["format"] = _video_selector(height, container)
        opts["merge_output_format"] = container
        expected_streams = 2

    postprocessors.append({"key": "FFmpegMetadata"})

    if clipping:
        # Cut [start, end]; re-encode at the cuts so they are frame-accurate.
        opts["download_ranges"] = download_range_func(
            None, [(clip_start or 0, clip_end if clip_end is not None else float("inf"))]
        )
        opts["force_keyframes_at_cuts"] = True

    if subtitles:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = list(sub_langs) or ["en"]
        postprocessors.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})

    if thumbnail:
        opts["writethumbnail"] = True
        postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})

    opts["postprocessors"] = postprocessors

    progress_hook, postprocessor_hook = _make_hooks(on_progress, expected_streams)

    def guarded_progress_hook(d: dict) -> None:
        if should_cancel and should_cancel():
            raise DownloadCancelled("cancelled")
        progress_hook(d)

    opts["progress_hooks"] = [guarded_progress_hook]
    opts["postprocessor_hooks"] = [postprocessor_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = _single_entry(ydl.extract_info(url, download=False))
            _check_duration(info)
            result = ydl.process_ie_result(info, download=True)
    except DownloaderError:
        raise
    except DownloadCancelled as exc:
        raise DownloaderError("cancelled") from exc
    except Exception as exc:  # noqa: BLE001 - map every extractor/ffmpeg failure
        raise _map_error(exc) from exc

    media = _locate_media(result, out_dir)
    final = _bundle_extras(media, out_dir)
    return {"filepath": final, "title": result.get("title") or media.stem}


def _output_files(out_dir: Path) -> list[Path]:
    return [p for p in out_dir.iterdir() if p.is_file() and p.suffix not in _TEMP_SUFFIXES]


def _locate_media(result: dict, out_dir: Path) -> Path:
    """Find the finished media file: trust yt-dlp first, fall back to the job folder."""
    for item in result.get("requested_downloads") or []:
        path = item.get("filepath")
        if path and Path(path).exists():
            return Path(path)

    candidates = _output_files(out_dir)
    if not candidates:
        raise DownloaderError("no_output")
    return max(candidates, key=lambda p: p.stat().st_size)


def _bundle_extras(media: Path, out_dir: Path) -> Path:
    """If subtitles/thumbnail files sit next to the media, zip them all together."""
    files = _output_files(out_dir)
    if len(files) <= 1:
        return media

    archive = out_dir / f"{media.stem}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            zf.write(f, arcname=f.name)
    for f in files:
        f.unlink(missing_ok=True)
    return archive
