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
    get_ffmpeg_path() -- path to ffmpeg binary (auto-downloaded on first call)
    get_ytdlp_path()  -- path to yt-dlp binary (auto-downloaded on first call)

Binaries are downloaded lazily on first use — never at import time.
This keeps imports fast and safe in offline / restricted environments.
"""

from .streamer import Streamer
from .media.player import VideoPlayer
from .enums import Codec, StreamType, Resolution
from .voice.client import VoiceStreamClient
from ._bootstrap import ensure_binaries, get_ffmpeg_path, get_ytdlp_path

__version__ = "0.1.0"
__all__ = [
    "Streamer",
    "VideoPlayer",
    "Codec",
    "StreamType",
    "Resolution",
    "VoiceStreamClient",
    "ensure_binaries",
    "get_ffmpeg_path",
    "get_ytdlp_path",
]
