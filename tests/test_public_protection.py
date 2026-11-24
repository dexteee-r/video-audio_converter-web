import threading

from conftest import wait_for

URL = "https://example.com/watch?v=abc"


def test_security_headers_on_api_and_static(client):
    for path in ("/api/health", "/"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert "default-src 'self'" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_docs_are_disabled_by_default(client):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_info_is_rate_limited_per_ip(client, monkeypatch):
    from server import config

    monkeypatch.setattr(config, "RATE_INFO_PER_MIN", 2)
    # Invalid URLs still count: they cost us DNS lookups.
    for _ in range(2):
        assert client.post("/api/info", json={"url": "nope"}).status_code == 400
    r = client.post("/api/info", json={"url": "nope"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_job_creation_is_rate_limited(client, monkeypatch):
    from server import config

    monkeypatch.setattr(config, "RATE_JOBS_PER_HOUR", 1)
    assert client.post("/api/jobs", json={"url": URL, "kind": "audio"}).status_code == 202
    r = client.post("/api/jobs", json={"url": URL, "kind": "audio"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "rate_limited"


def test_active_jobs_per_ip_are_capped(client, monkeypatch):
    from server import config

    monkeypatch.setattr(config, "MAX_ACTIVE_PER_IP", 2)
    release = threading.Event()

    def blocking_download(url, kind, out_dir, *, on_progress=None, should_cancel=None, **_):
        release.wait(5)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "x.mp3"
        path.write_bytes(b"x")
        return {"filepath": path, "title": "x"}

    manager = client.app.state.jobs
    manager._download_fn = blocking_download

    ids = []
    for _ in range(2):
        r = client.post("/api/jobs", json={"url": URL, "kind": "audio"})
        assert r.status_code == 202
        ids.append(r.json()["id"])

    r = client.post("/api/jobs", json={"url": URL, "kind": "audio"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_active"

    release.set()
    for job_id in ids:
        wait_for(client, job_id)
    # Slots are free again once jobs finish.
    assert client.post("/api/jobs", json={"url": URL, "kind": "audio"}).status_code == 202


def test_malformed_body_uses_the_standard_error_shape(client):
    r = client.post("/api/jobs", json={"url": URL, "kind": "audio", "sub_langs": ["en; rm -rf /"]})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_option"
