"""Runtime configuration, read from environment variables (YTC_*).

Everything has a safe default so the app runs locally with zero setup; in
production, override through the environment (Docker/systemd/PaaS).
"""

import os
import tempfile
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# Where job folders are written. Files are short-lived (see JOB_TTL_SECONDS).
DOWNLOAD_DIR = Path(os.getenv("YTC_DOWNLOAD_DIR") or Path(tempfile.gettempdir()) / "ytc-web")

# How long a finished file stays downloadable before being deleted.
JOB_TTL_SECONDS = _int("YTC_JOB_TTL_SECONDS", 30 * 60)

# Parallel downloads on the server, and how many jobs may wait in line.
MAX_CONCURRENT_JOBS = _int("YTC_MAX_CONCURRENT_JOBS", 2)
MAX_QUEUED_JOBS = _int("YTC_MAX_QUEUED_JOBS", 10)

# Refuse media longer than this (seconds). 0 = no limit.
MAX_DURATION_SECONDS = _int("YTC_MAX_DURATION_SECONDS", 3 * 3600)

# Refuse files larger than this many MB (0 = no limit). Protects the disk on a
# public server. Only enforced when yt-dlp knows the size.
MAX_FILESIZE_MB = _int("YTC_MAX_FILESIZE_MB", 1024)

# ---- public-site abuse protection (per client IP) ----
# Behind a reverse proxy, run uvicorn with --proxy-headers and
# --forwarded-allow-ips=<proxy ip> so request.client.host is the real visitor.
RATE_INFO_PER_MIN = _int("YTC_RATE_INFO_PER_MIN", 60)       # /api/info calls
RATE_JOBS_PER_HOUR = _int("YTC_RATE_JOBS_PER_HOUR", 60)     # download jobs created
MAX_ACTIVE_PER_IP = _int("YTC_MAX_ACTIVE_PER_IP", 2)        # queued+running jobs at once

# Interactive API docs (/api/docs). Off by default: they load scripts from a CDN
# and have no place on a public site.
ENABLE_DOCS = os.getenv("YTC_ENABLE_DOCS", "") == "1"

# Optional Netscape cookies file (helps with age-gated / "sign in to confirm
# you're not a bot" YouTube pages from datacenter IPs). Empty = not used.
COOKIES_FILE = os.getenv("YTC_COOKIES_FILE", "")
