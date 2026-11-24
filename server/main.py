"""FastAPI app: JSON API under /api, static frontend (web/) at /.

Run locally:   venv\\Scripts\\python.exe -m uvicorn server.main:app --reload
"""

import asyncio
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from server import config, downloader, security
from server.downloader import DownloaderError
from server.jobs import JobManager, QueueFull, TooManyActive
from server.ratelimit import RateLimiter

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Windows can map .js to text/plain via the registry, which breaks service workers.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Error code -> HTTP status. Anything unlisted is a 502 (upstream/extractor problem).
_STATUS = {
    "invalid_url": 400,
    "forbidden_host": 400,
    "unresolvable_host": 400,
    "invalid_option": 400,
    "unsupported_url": 422,
    "too_long": 422,
    "too_large": 422,
    "no_media": 422,
    "ffmpeg_missing": 503,
    "rate_limited": 429,
    "busy": 429,
    "too_many_active": 429,
}


def _http_error(code: str, status: Optional[int] = None, headers: Optional[dict] = None) -> HTTPException:
    return HTTPException(status_code=status or _STATUS.get(code, 502), detail={"code": code}, headers=headers)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, bucket: str, limit: int, window: float) -> None:
    wait = request.app.state.limiter.hit(bucket, _client_ip(request), limit, window)
    if wait is not None:
        raise _http_error("rate_limited", headers={"Retry-After": str(wait)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.jobs = JobManager()
    app.state.jobs.start_cleanup()
    app.state.limiter = RateLimiter()

    async def prune_limiter():
        while True:
            await asyncio.sleep(300)
            app.state.limiter.prune()

    pruner = asyncio.create_task(prune_limiter())
    yield
    pruner.cancel()
    app.state.jobs.shutdown()


app = FastAPI(
    title="YouTube Converter Web",
    docs_url="/api/docs" if config.ENABLE_DOCS else None,
    openapi_url="/api/openapi.json" if config.ENABLE_DOCS else None,
    redoc_url=None,
    lifespan=lifespan,
)

@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _exc: RequestValidationError):
    """Same error shape as every other failure, instead of FastAPI's default list."""
    return JSONResponse(status_code=400, content={"detail": {"code": "invalid_option"}})


# Strict policy: everything is served from our own origin. Thumbnails come from
# arbitrary https hosts, hence img-src https:.
_CSP = (
    "default-src 'self'; img-src 'self' data: https:; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not request.url.path.startswith(("/api/docs", "/api/openapi")):
        response.headers["Content-Security-Policy"] = _CSP
    return response


# ---- request models -----------------------------------------------------
LangCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")]


class InfoRequest(BaseModel):
    url: str


class JobRequest(BaseModel):
    url: str
    kind: Literal["video", "audio"]
    quality: int = Field(1080, description="Max height in px; 0 = best available")
    format: Optional[str] = Field(None, description="Container (video) or codec (audio)")
    bitrate: int = 192
    clip_start: Optional[float] = Field(None, ge=0, le=86400, allow_inf_nan=False)
    clip_end: Optional[float] = Field(None, ge=0, le=86400, allow_inf_nan=False)
    subtitles: bool = False
    sub_langs: list[LangCode] = Field(default_factory=list, max_length=3)
    thumbnail: bool = False


# ---- routes ---------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "ffmpeg": downloader.ffmpeg_available(),
        "yt_dlp": downloader.ytdlp_version(),
        "limits": {
            "max_duration_seconds": config.MAX_DURATION_SECONDS,
            "job_ttl_seconds": config.JOB_TTL_SECONDS,
        },
        "options": {
            "qualities": list(downloader.STANDARD_HEIGHTS),
            "video_formats": list(downloader.VIDEO_FORMATS),
            "audio_formats": list(downloader.AUDIO_FORMATS),
            "lossless_audio": list(downloader.LOSSLESS_AUDIO),
            "audio_bitrates": list(downloader.AUDIO_BITRATES),
        },
    }


@app.post("/api/info")
def info(req: InfoRequest, request: Request):
    _rate_limit(request, "info", config.RATE_INFO_PER_MIN, 60)
    if (code := security.check_url(req.url)):
        raise _http_error(code)
    try:
        return downloader.fetch_info(req.url.strip())
    except DownloaderError as exc:
        raise _http_error(exc.code) from exc


@app.post("/api/jobs", status_code=202)
def create_job(req: JobRequest, request: Request):
    _rate_limit(request, "jobs", config.RATE_JOBS_PER_HOUR, 3600)
    if (code := security.check_url(req.url)):
        raise _http_error(code)

    if req.quality != 0 and req.quality not in downloader.STANDARD_HEIGHTS:
        raise _http_error("invalid_option")
    if (
        req.clip_start is not None and req.clip_end is not None and req.clip_end <= req.clip_start
    ):
        raise _http_error("invalid_option")

    if req.kind == "video":
        container = req.format or "mp4"
        if container not in downloader.VIDEO_FORMATS:
            raise _http_error("invalid_option")
        options = {"height": req.quality, "container": container}
    else:
        audio_format = req.format or "mp3"
        if audio_format not in downloader.AUDIO_FORMATS or req.bitrate not in downloader.AUDIO_BITRATES:
            raise _http_error("invalid_option")
        options = {"audio_format": audio_format, "bitrate": req.bitrate}

    options.update(
        clip_start=req.clip_start,
        clip_end=req.clip_end,
        subtitles=req.subtitles,
        sub_langs=req.sub_langs,
        thumbnail=req.thumbnail,
    )

    try:
        job = request.app.state.jobs.submit(req.url.strip(), req.kind, options, owner=_client_ip(request))
    except QueueFull as exc:
        raise _http_error("busy") from exc
    except TooManyActive as exc:
        raise _http_error("too_many_active") from exc
    return job.public()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise _http_error("job_not_found", 404)
    return job.public()


@app.delete("/api/jobs/{job_id}", status_code=204)
def job_cancel(job_id: str, request: Request):
    if not request.app.state.jobs.cancel(job_id):
        raise _http_error("job_not_found", 404)


@app.get("/api/jobs/{job_id}/file")
def job_file(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise _http_error("job_not_found", 404)
    if job.state != "done" or not job.filepath or not job.filepath.exists():
        raise _http_error("not_ready", 409)
    return FileResponse(job.filepath, filename=job.filename)


# Frontend last, so /api/* wins.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
