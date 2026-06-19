"""Media pipeline: FFmpeg process management and the MediaPlayer class.

Re-exports the main classes for convenience::

    from discord_video_stream.media import VideoPlayer, MediaPlayer
"""

from .player import MediaPlayer, VideoPlayer
from .ffmpeg import spawn_ffmpeg, FFmpegProcess
from .ytdlp import resolve_url

__all__ = [
    "MediaPlayer",
    "VideoPlayer",
    "spawn_ffmpeg",
    "FFmpegProcess",
    "resolve_url",
]
