"""yt-dlp URL resolver — extract direct stream URLs from online platforms.

Supports YouTube, Twitch, and 1000+ sites supported by yt-dlp.
Falls back to the original URL if yt-dlp fails (allows passing direct
HTTP stream URLs or local files through unchanged).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)


async def resolve_url(url: str, *, prefer_format: str = "bestvideo+bestaudio/best") -> str:
    """
    Resolve an online URL to a direct stream URL using yt-dlp.

    If the URL is a local file path or direct media URL, it is returned
    unchanged without invoking yt-dlp.

    Parameters
    ----------
    url:
        YouTube/Twitch/etc. URL, a direct media URL, or a local file path.
    prefer_format:
        yt-dlp format selector string. Defaults to best available quality.

    Returns
    -------
    str
        A direct URL that FFmpeg can consume, or the original path/URL.
    """
    if _is_local_or_direct(url):
        return url

    log.info("Resolving URL via yt-dlp: %s", url)
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        log.warning("yt-dlp not installed — returning URL unchanged.")
        return url

    ydl_opts = {
        "format": prefer_format,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, lambda: _extract(url, ydl_opts))
    except Exception as exc:
        log.error("yt-dlp failed for %s: %s", url, exc)
        return url

    # For combined formats, yt-dlp returns a single direct URL
    direct_url = info.get("url") or info.get("manifest_url") or url
    log.debug("Resolved to: %s", direct_url[:80])
    return direct_url


def _extract(url: str, opts: dict) -> dict:
    import yt_dlp  # type: ignore[import-untyped]
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _is_local_or_direct(url: str) -> bool:
    """Return True if the string looks like a local path or a direct media URL."""
    import os
    if os.path.exists(url):
        return True
    # Direct file extensions that don’t need yt-dlp
    direct_exts = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m3u8")
    lower = url.lower()
    if any(lower.endswith(ext) for ext in direct_exts):
        return True
    # Direct stream URLs (RTMP, RTSP, HLS already resolved)
    if lower.startswith(("rtmp://", "rtmps://", "rtsp://")):
        return True
    return False
