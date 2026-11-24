import zipfile

from conftest import wait_for

from server import downloader
from server.ratelimit import RateLimiter

URL = "https://example.com/watch?v=abc"


def test_extra_options_reach_the_downloader(client):
    seen = {}

    def spy(url, kind, out_dir, *, on_progress=None, should_cancel=None, **options):
        seen.update(options)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "a.mp4"
        path.write_bytes(b"x")
        return {"filepath": path, "title": "a"}

    client.app.state.jobs._download_fn = spy
    r = client.post("/api/jobs", json={
        "url": URL, "kind": "video", "quality": 720, "format": "mkv",
        "clip_start": 10, "clip_end": 25.5,
        "subtitles": True, "sub_langs": ["fr", "en"], "thumbnail": True,
    })
    assert r.status_code == 202
    wait_for(client, r.json()["id"])
    assert seen == {
        "height": 720, "container": "mkv",
        "clip_start": 10, "clip_end": 25.5,
        "subtitles": True, "sub_langs": ["fr", "en"], "thumbnail": True,
    }


def test_clip_end_must_be_after_start(client):
    for start, end in ((30, 30), (30, 10)):
        r = client.post("/api/jobs", json={"url": URL, "kind": "audio", "clip_start": start, "clip_end": end})
        assert r.status_code == 400, (start, end)


def test_clip_values_are_bounded(client):
    assert client.post("/api/jobs", json={"url": URL, "kind": "audio", "clip_start": -1}).status_code == 400
    assert client.post("/api/jobs", json={"url": URL, "kind": "audio", "clip_end": 10**9}).status_code == 400


def test_too_many_sub_langs_rejected(client):
    r = client.post("/api/jobs", json={"url": URL, "kind": "audio", "subtitles": True,
                                       "sub_langs": ["fr", "en", "es", "de"]})
    assert r.status_code == 400


# ---- downloader helpers (no network) -------------------------------------
def test_extras_are_bundled_into_a_zip(tmp_path):
    media = tmp_path / "Song.mp3"
    media.write_bytes(b"audio")
    (tmp_path / "Song.fr.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    (tmp_path / "Song.jpg").write_bytes(b"img")
    (tmp_path / "Song.mp3.part").write_bytes(b"junk")  # temp files are ignored

    result = downloader._bundle_extras(media, tmp_path)

    assert result.name == "Song.zip"
    with zipfile.ZipFile(result) as zf:
        assert sorted(zf.namelist()) == ["Song.fr.srt", "Song.jpg", "Song.mp3"]
    assert not media.exists()  # originals removed, only the zip remains


def test_single_file_is_returned_as_is(tmp_path):
    media = tmp_path / "Clip.mp4"
    media.write_bytes(b"video")
    assert downloader._bundle_extras(media, tmp_path) == media


def test_error_mapping():
    m = downloader._map_error
    assert m(Exception("File is larger than max-filesize (10 bytes > 5 bytes)")).code == "too_large"
    assert m(Exception("Unsupported URL: https://x")).code == "unsupported_url"
    assert m(Exception("Sign in to confirm you're not a bot")).code == "auth_required"
    assert m(Exception("Video unavailable")).code == "unavailable"
    assert m(Exception("boom")).code == "extract_failed"


def test_video_selector_prefers_mp4_streams_and_caps_height():
    sel = downloader._video_selector(720, "mp4")
    assert sel.startswith("bv*[height<=720][ext=mp4]+ba[ext=m4a]")
    assert sel.endswith("/b")
    assert "height" not in downloader._video_selector(0, "mkv")  # 0 = no cap


# ---- rate limiter --------------------------------------------------------
def test_rate_limiter_window_and_isolation():
    rl = RateLimiter()
    assert rl.hit("b", "1.1.1.1", 2, 60) is None
    assert rl.hit("b", "1.1.1.1", 2, 60) is None
    assert rl.hit("b", "1.1.1.1", 2, 60) >= 1       # third hit blocked
    assert rl.hit("b", "2.2.2.2", 2, 60) is None    # other IP unaffected
    assert rl.hit("other", "1.1.1.1", 2, 60) is None  # other bucket unaffected
    assert rl.hit("b", "1.1.1.1", 0, 60) is None    # limit 0 = disabled


def test_rate_limiter_prune_drops_idle_keys():
    rl = RateLimiter()
    rl.hit("b", "1.1.1.1", 5, 60)
    rl.prune(max_window=-1)  # everything counts as idle
    assert rl._hits == {}
