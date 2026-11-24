"""In-memory job queue.

A job = one download requested by a visitor. Jobs run in a small thread pool
(yt-dlp is blocking), live in a dict keyed by an unguessable id, and their
files are deleted after JOB_TTL_SECONDS.

In-memory state is fine for one server process. If the site ever needs several
workers/instances, swap this module for a Redis/DB-backed store.
"""

import secrets
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from server import config, downloader
from server.downloader import DownloaderError

# Signature of the download function (injectable so tests don't hit the network).
DownloadFn = Callable[..., dict]


@dataclass
class Job:
    id: str
    url: str
    kind: str                       # "video" | "audio"
    options: dict
    owner: str = ""                 # client IP, for the per-IP active-jobs cap
    state: str = "queued"           # queued | downloading | processing | done | error
    progress: float = 0.0
    speed: Optional[float] = None   # bytes/s
    eta: Optional[int] = None       # seconds
    title: str = ""
    filename: str = ""
    filesize: int = 0
    error_code: str = ""
    created: float = field(default_factory=time.time)
    finished: Optional[float] = None
    filepath: Optional[Path] = None
    cancelled: bool = False

    def public(self) -> dict:
        """What the API exposes (never the server-side path)."""
        return {
            "id": self.id,
            "state": self.state,
            "progress": self.progress,
            "speed": self.speed,
            "eta": self.eta,
            "title": self.title,
            "filename": self.filename,
            "filesize": self.filesize,
            "error": self.error_code or None,
            "expires_in": self._expires_in(),
        }

    def _expires_in(self) -> Optional[int]:
        if self.finished is None:
            return None
        return max(0, int(self.finished + config.JOB_TTL_SECONDS - time.time()))


class QueueFull(Exception):
    pass


class TooManyActive(Exception):
    """This client already has the maximum number of queued/running jobs."""


_ACTIVE_STATES = ("queued", "downloading", "processing")


class JobManager:
    def __init__(
        self,
        download_dir: Path = config.DOWNLOAD_DIR,
        max_workers: int = config.MAX_CONCURRENT_JOBS,
        max_queued: int = config.MAX_QUEUED_JOBS,
        download_fn: DownloadFn = downloader.download,
    ):
        self.download_dir = download_dir
        self.max_queued = max_queued
        self._download_fn = download_fn
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dl")
        self._stop = threading.Event()
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # ---- public API --------------------------------------------------
    def submit(self, url: str, kind: str, options: dict, owner: str = "") -> Job:
        with self._lock:
            waiting = sum(1 for j in self._jobs.values() if j.state == "queued")
            if waiting >= self.max_queued:
                raise QueueFull()
            cap = config.MAX_ACTIVE_PER_IP
            if cap > 0 and owner:
                active = sum(1 for j in self._jobs.values() if j.owner == owner and j.state in _ACTIVE_STATES)
                if active >= cap:
                    raise TooManyActive()
            job = Job(id=secrets.token_urlsafe(12), url=url, kind=kind, options=options, owner=owner)
            self._jobs[job.id] = job
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.state in ("done", "error"):
            return False
        job.cancelled = True
        return True

    def start_cleanup(self, interval: int = 60) -> None:
        threading.Thread(target=self._cleanup_loop, args=(interval,), daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- internals ---------------------------------------------------
    def _job_dir(self, job: Job) -> Path:
        return self.download_dir / job.id

    def _on_progress(self, job: Job, data: dict) -> None:
        job.state = data.get("state", job.state)
        job.progress = data.get("progress", job.progress)
        job.speed = data.get("speed")
        job.eta = data.get("eta")

    def _run(self, job: Job) -> None:
        if job.cancelled:
            self._fail(job, "cancelled")
            return
        job.state = "downloading"
        try:
            result = self._download_fn(
                job.url,
                job.kind,
                self._job_dir(job),
                on_progress=lambda d: self._on_progress(job, d),
                should_cancel=lambda: job.cancelled,
                **job.options,
            )
        except DownloaderError as exc:
            self._fail(job, exc.code)
            return
        except Exception:  # noqa: BLE001 - never let a worker thread die silently
            self._fail(job, "internal_error")
            return

        path = Path(result["filepath"])
        job.filepath = path
        job.filename = path.name
        job.filesize = path.stat().st_size
        job.title = result.get("title", path.stem)
        job.progress = 100.0
        job.speed = job.eta = None
        job.finished = time.time()
        job.state = "done"

    def _fail(self, job: Job, code: str) -> None:
        job.state = "error"
        job.error_code = code
        job.speed = job.eta = None
        job.finished = time.time()
        shutil.rmtree(self._job_dir(job), ignore_errors=True)

    def _cleanup_loop(self, interval: int) -> None:
        while not self._stop.wait(interval):
            self.cleanup()

    def cleanup(self) -> int:
        """Delete expired jobs and their files. Returns how many were removed."""
        now = time.time()
        with self._lock:
            expired = [
                j for j in self._jobs.values()
                if j.finished is not None and now - j.finished > config.JOB_TTL_SECONDS
            ]
            for job in expired:
                del self._jobs[job.id]
        for job in expired:
            shutil.rmtree(self._job_dir(job), ignore_errors=True)
        return len(expired)
