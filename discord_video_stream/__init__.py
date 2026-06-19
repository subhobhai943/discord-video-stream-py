"""
discord-video-stream-py
~~~~~~~~~~~~~~~~~~~~~~~
Stream video and audio into Discord voice channels from Python.

Public API surface:
    Streamer      — joins a voice channel and manages the stream lifecycle
    VideoPlayer   — wraps MediaPlayer with a user-facing API
    Codec         — enum for H264 / VP8
    StreamType    — enum for GoLive / Webcam
    Resolution    — preset helper
"""

from .streamer import Streamer
from .media.player import VideoPlayer
from .enums import Codec, StreamType, Resolution
from .voice.client import VoiceStreamClient

__version__ = "0.1.0"
__all__ = ["Streamer", "VideoPlayer", "Codec", "StreamType", "Resolution", "VoiceStreamClient"]

