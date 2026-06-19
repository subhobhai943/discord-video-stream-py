"""
discord-video-stream-py
~~~~~~~~~~~~~~~~~~~~~~~
Stream video and audio into Discord voice channels from Python.

Public API surface:
    Streamer          -- joins a voice channel and manages the stream lifecycle
    VideoPlayer       -- wraps MediaPlayer with a user-facing API
    Codec             -- enum for H264 / VP8
    StreamType        -- enum for GoLive / Webcam
    Resolution        -- preset helper
    get_ffmpeg_path() -- path to the bundled ffmpeg binary (auto-downloaded)
    get_ytdlp_path()  -- path to the bundled yt-dlp binary (auto-downloaded)
"""

from ._bootstrap import ensure_binaries, get_ffmpeg_path, get_ytdlp_path
from .streamer import Streamer
from .media.player import VideoPlayer
from .enums import Codec, StreamType, Resolution
from .voice.client import VoiceStreamClient

# Download ffmpeg + yt-dlp for the current platform on first import.
# Subsequent imports are instant (files already exist on disk).
ensure_binaries()

__version__ = "0.1.0"
__all__ = [
    "Streamer",
    "VideoPlayer",
    "Codec",
    "StreamType",
    "Resolution",
    "VoiceStreamClient",
    "get_ffmpeg_path",
    "get_ytdlp_path",
]
