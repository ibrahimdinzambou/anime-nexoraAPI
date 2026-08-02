from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse


BAD_URL_RX = re.compile(
    r"(doubleclick|googlesyndication|googletagmanager|google-analytics|facebook|"
    r"fbcdn|disqus|popads|popcash|exoclick|adnxs|mgid|taboola|outbrain|"
    r"adsterra|hilltopads|trafficjunky|propellerads|analytics|tracking|ads|"
    r"advertisement)",
    re.IGNORECASE,
)

PLAYER_HOST_RX = re.compile(
    r"(?:^|\.)(vidmoly|sibnet|sendvid|uqload|netu|voe|dood|streamtape|"
    r"filemoon|lulustream|kokoflix|mixdrop|vidoza|upstream|waaw|streamwish|"
    r"streamsb|filelions|savefiles|wolfstream|vidzy|multiup|fsvid)\."
    r"[a-z0-9.-]+$",
    re.IGNORECASE,
)

ANIME_SAMA_HOST_RX = re.compile(r"(?:^|\.)anime-sama\.[a-z0-9.-]+$", re.IGNORECASE)


def _hostname(value: str) -> str:
    return (urlparse(value).hostname or "").lower()


def is_safe_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not BAD_URL_RX.search(value)


def is_safe_provider_url(value: str) -> bool:
    return is_safe_http_url(value) and bool(ANIME_SAMA_HOST_RX.search(_hostname(value)))


def is_safe_player_url(value: str) -> bool:
    return is_safe_http_url(value) and bool(PLAYER_HOST_RX.search(_hostname(value)))


def safe_redirect_location(location: str, base_url: str) -> str | None:
    try:
        target = urljoin(base_url, location)
    except ValueError:
        return None
    return target if is_safe_provider_url(target) else None
