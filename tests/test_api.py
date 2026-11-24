from conftest import wait_for

URL = "https://example.com/watch?v=abc"


def test_health(client):
    data = client.get("/api/health").json()
    assert data["ok"] is True
    assert "mp3" in data["options"]["audio_formats"]
    assert 1080 in data["options"]["qualities"]


def test_info_rejects_bad_url(client):
    r = client.post("/api/info", json={"url": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_url"


def test_video_job_roundtrip(client):
    r = client.post("/api/jobs", json={"url": URL, "kind": "video", "quality": 720, "format": "mp4"})
    assert r.status_code == 202
    job = wait_for(client, r.json()["id"])
    assert job["filename"] == "Fake title.mp4"
    assert job["progress"] == 100.0
    assert job["expires_in"] > 0

    f = client.get(f"/api/jobs/{job['id']}/file")
    assert f.status_code == 200
    assert f.content == b"x" * 64
    assert "attachment" in f.headers["content-disposition"]


def test_audio_job_roundtrip(client):
    r = client.post("/api/jobs", json={"url": URL, "kind": "audio", "format": "mp3", "bitrate": 320})
    job = wait_for(client, r.json()["id"])
    assert job["filename"].endswith(".mp3")


def test_failed_job_reports_error_code(client):
    r = client.post("/api/jobs", json={"url": "https://example.com/fail", "kind": "video"})
    job = wait_for(client, r.json()["id"], state="error")
    assert job["error"] == "private_media"
    assert client.get(f"/api/jobs/{job['id']}/file").status_code == 409


def test_rejects_invalid_options(client):
    bad = [
        {"kind": "video", "quality": 999},
        {"kind": "video", "format": "avi"},
        {"kind": "audio", "format": "aac"},
        {"kind": "audio", "bitrate": 1},
    ]
    for extra in bad:
        r = client.post("/api/jobs", json={"url": URL, **extra})
        assert r.status_code == 400, extra
        assert r.json()["detail"]["code"] == "invalid_option"


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/file").status_code == 404


def test_cleanup_removes_expired_job_files(client, monkeypatch):
    from server import config

    r = client.post("/api/jobs", json={"url": URL, "kind": "audio"})
    job_id = r.json()["id"]
    wait_for(client, job_id)

    manager = client.app.state.jobs
    job_dir = manager.download_dir / job_id
    assert job_dir.exists()

    monkeypatch.setattr(config, "JOB_TTL_SECONDS", -1)  # everything is expired
    assert manager.cleanup() == 1
    assert not job_dir.exists()
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
