import pytest

from server.security import check_url


@pytest.mark.parametrize("url", [
    "",
    "   ",
    "not a url",
    "ftp://example.com/video",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "http://",
    "https://example.com/" + "a" * 3000,
])
def test_rejects_malformed_urls(url):
    assert check_url(url) == "invalid_url"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://localhost:8000/",
    "http://10.0.0.5/video",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    "http://[::1]/",
])
def test_blocks_private_and_loopback_hosts(url):
    assert check_url(url) == "forbidden_host"


def test_accepts_public_ip_literal():
    assert check_url("https://93.184.216.34/watch?v=abc") is None
