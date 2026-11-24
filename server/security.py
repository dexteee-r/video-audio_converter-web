"""URL validation.

The server fetches whatever URL a visitor submits, so it must never be
pointed at the server's own network (SSRF): localhost, private ranges, cloud
metadata endpoints, etc.
"""

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

MAX_URL_LENGTH = 2048


def check_url(url: str) -> Optional[str]:
    """Return None if the URL is acceptable, otherwise an error code."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LENGTH:
        return "invalid_url"

    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid_url"

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "invalid_url"

    try:
        addresses = {
            info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        }
    except (socket.gaierror, UnicodeError):
        return "unresolvable_host"

    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip IPv6 zone id
        except ValueError:
            return "invalid_url"
        if not ip.is_global:
            return "forbidden_host"

    return None
