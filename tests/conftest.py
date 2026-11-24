import sys
import time
from pathlib import Path

import pytest

# Make `server` importable when running `pytest` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def fake_download(url, kind, out_dir, *, on_progress=None, should_cancel=None, **options):
    """Stand-in for server.downloader.download: writes a tiny file, no network."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if "fail" in url:
        from server.downloader import DownloaderError
        raise DownloaderError("private_media")
    on_progress({"state": "downloading", "progress": 50.0, "speed": 1000.0, "eta": 1})
    ext = "mp3" if kind == "audio" else "mp4"
    path = out_dir / f"Fake title.{ext}"
    path.write_bytes(b"x" * 64)
    return {"filepath": path, "title": "Fake title"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with downloads redirected to tmp_path and a fake downloader."""
    from fastapi.testclient import TestClient

    from server import config, jobs, main

    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path)
    # URL checks do real DNS; stub them so tests are offline-safe.
    monkeypatch.setattr(main.security, "check_url", lambda u: None if u.startswith("http") else "invalid_url")

    with TestClient(main.app) as c:
        main.app.state.jobs = jobs.JobManager(download_dir=tmp_path, download_fn=fake_download)
        yield c


def wait_for(client, job_id, state="done", timeout=5.0):
    """Poll the API until a job reaches `state`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["state"] == state:
            return data
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached {state!r}: {data}")
