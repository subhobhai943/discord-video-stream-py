"""Unit tests for the yt-dlp URL resolver (media/ytdlp.py)."""

import asyncio
import os
import pytest
from unittest import mock

from discord_video_stream.media.ytdlp import _is_local_or_direct, resolve_url


# ---------------------------------------------------------------------------
# _is_local_or_direct — direct media file extensions
# ---------------------------------------------------------------------------

def test_local_mp4_extension():
    assert _is_local_or_direct("video.mp4") is True


def test_local_mkv_extension():
    assert _is_local_or_direct("video.mkv") is True


def test_local_webm_extension():
    assert _is_local_or_direct("video.webm") is True


def test_local_avi_extension():
    assert _is_local_or_direct("video.avi") is True


def test_local_mov_extension():
    assert _is_local_or_direct("recording.mov") is True


def test_local_flv_extension():
    assert _is_local_or_direct("stream.flv") is True


def test_local_ts_extension():
    assert _is_local_or_direct("segment.ts") is True


def test_local_m3u8_extension():
    assert _is_local_or_direct("playlist.m3u8") is True


# ---------------------------------------------------------------------------
# _is_local_or_direct — direct URLs with file extensions
# ---------------------------------------------------------------------------

def test_direct_url_mp4():
    assert _is_local_or_direct("https://example.com/file.mp4") is True


def test_direct_url_mkv():
    assert _is_local_or_direct("http://cdn.example.com/movie.mkv") is True


# ---------------------------------------------------------------------------
# _is_local_or_direct — streaming protocols
# ---------------------------------------------------------------------------

def test_rtmp_protocol():
    assert _is_local_or_direct("rtmp://live.example.com/stream") is True


def test_rtmps_protocol():
    assert _is_local_or_direct("rtmps://secure.example.com/live") is True


def test_rtsp_protocol():
    assert _is_local_or_direct("rtsp://camera.local:554/feed") is True


# ---------------------------------------------------------------------------
# _is_local_or_direct — returns False for platform URLs
# ---------------------------------------------------------------------------

def test_youtube_url():
    assert _is_local_or_direct("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False


def test_twitch_url():
    assert _is_local_or_direct("https://www.twitch.tv/streamer") is False


def test_generic_webpage():
    assert _is_local_or_direct("https://example.com/page") is False


# ---------------------------------------------------------------------------
# _is_local_or_direct — existing local file (via os.path.exists)
# ---------------------------------------------------------------------------

def test_existing_local_file(tmp_path):
    f = tmp_path / "test_video.xyz"
    f.write_text("dummy")
    assert _is_local_or_direct(str(f)) is True


# ---------------------------------------------------------------------------
# resolve_url — local files returned unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_url_local_file():
    url = "/home/user/video.mp4"
    result = await resolve_url(url)
    assert result == url


@pytest.mark.asyncio
async def test_resolve_url_direct_url():
    url = "https://cdn.example.com/stream.mkv"
    result = await resolve_url(url)
    assert result == url


@pytest.mark.asyncio
async def test_resolve_url_rtmp():
    url = "rtmp://live.example.com/app/stream"
    result = await resolve_url(url)
    assert result == url


# ---------------------------------------------------------------------------
# resolve_url — yt-dlp not installed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_url_ytdlp_not_installed():
    """When yt-dlp is not importable, resolve_url returns the URL unchanged."""
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("mocked: yt_dlp not installed")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=mock_import):
        result = await resolve_url(youtube_url)

    assert result == youtube_url
