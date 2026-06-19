"""FFmpeg subprocess builder and manager.

Builds the FFmpeg command-line arguments for the audio and video pipes,
spawns the subprocess, and exposes asyncio stdout pipes for the codec
readers to consume.

Example command built internally for H264 + Opus::

    ffmpeg -re -i <source> \\
        -map 0:v:0 -c:v libx264 -preset ultrafast -tune zerolatency \\
            -x264opts keyint=60:min-keyint=60:no-scenecut \\
            -b:v 2M -maxrate 2M -bufsize 4M \\
            -vf scale=1280:720 -r 30 \\
            -f h264 pipe:3 \\
        -map 0:a:0 -ac 2 -ar 48000 -c:a libopus -b:a 128k \\
            -application lowdelay -frame_duration 20 -vbr off \\
            -f data pipe:4
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import NamedTuple

from ..enums import Codec, Resolution

log = logging.getLogger(__name__)


def _parse_bitrate_to_kbits(bitrate_str: str) -> int:
    """Convert a bitrate string like '2M', '2500K', '500k', '2m' to kilobits."""
    s = bitrate_str.strip()
    if not s:
        raise ValueError("Empty bitrate string")
    suffix = s[-1].upper()
    if suffix == 'M':
        return int(float(s[:-1]) * 1000)
    elif suffix == 'K':
        return int(float(s[:-1]))
    else:
        # No suffix — assume raw bits per second, convert to kilobits.
        return int(float(s) / 1000)


class FFmpegProcess(NamedTuple):
    """Holds the spawned process and its stdout pipe handles."""
    process: asyncio.subprocess.Process
    video_reader: asyncio.StreamReader
    audio_reader: asyncio.StreamReader


async def spawn_ffmpeg(
    source: str,
    *,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    codec: Codec = Codec.H264,
    video_bitrate: str = "2M",
    audio_bitrate: str = "128k",
    realtime: bool = True,
    seek_offset: float = 0.0,
) -> FFmpegProcess:
    """
    Spawn an FFmpeg subprocess and return :class:`FFmpegProcess` with async
    reader handles for the video and audio output pipes.

    Parameters
    ----------
    source:
        Local file path or direct stream URL (already resolved by yt-dlp).
    width, height:
        Output resolution. Pass 0 to use source dimensions.
    fps:
        Output framerate.
    codec:
        Video codec — H264 or VP8.
    video_bitrate:
        Target video bitrate string, e.g. ``"2M"``.
    audio_bitrate:
        Target audio bitrate string, e.g. ``"128k"``.
    realtime:
        Whether to add ``-re`` flag (read at native frame rate).
        Set ``False`` for pipe sources.
    seek_offset:
        If > 0, passed as ``-ss`` *before* ``-i`` for fast input seeking.
        Value is in seconds (e.g. 90.5 for 1 min 30.5 s).
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise RuntimeError(
            "ffmpeg not found in PATH. "
            "Install it with: sudo apt install ffmpeg  (Linux) "
            "or: brew install ffmpeg  (macOS)"
        )

    video_encoder, video_format = _codec_args(codec)
    scale_filter = f"scale={width}:{height}" if width and height else "scale=iw:ih"

    cmd = [ffmpeg_bin]

    if seek_offset > 0:
        cmd += ["-ss", str(seek_offset)]

    if realtime:
        cmd += ["-re"]

    cmd += ["-loglevel", "quiet", "-i", source]

    # Video output pipe (pipe:1)
    bufsize_kbits = _parse_bitrate_to_kbits(video_bitrate) * 2
    cmd += [
        "-map", "0:v:0",
        "-c:v", video_encoder,
    ]
    if codec == Codec.H264:
        cmd += [
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-x264opts", "keyint=60:min-keyint=60:no-scenecut",
        ]
    cmd += [
        "-b:v", video_bitrate,
        "-maxrate", video_bitrate,
        "-bufsize", f"{bufsize_kbits}K",
        "-vf", scale_filter,
        "-r", str(fps),
        "-f", video_format,
        "pipe:1",
    ]

    # NOTE: Audio is sent through pipe:2 (stderr) while video uses pipe:1
    # (stdout).  FFmpeg's diagnostic output is suppressed with -loglevel quiet
    # so that log messages do not corrupt the raw audio stream on stderr.
    cmd += [
        "-map", "0:a:0",
        "-ac", "2",
        "-ar", "48000",
        "-c:a", "libopus",
        "-b:a", audio_bitrate,
        "-application", "lowdelay",
        "-frame_duration", "20",
        "-vbr", "off",
        "-f", "data",
        "pipe:2",
    ]

    log.debug("FFmpeg command: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=2 ** 22,  # 4 MiB read buffer
    )

    video_reader = proc.stdout
    audio_reader = proc.stderr

    return FFmpegProcess(process=proc, video_reader=video_reader, audio_reader=audio_reader)


def _codec_args(codec: Codec) -> tuple[str, str]:
    """Return (encoder_name, ffmpeg_format) for the codec."""
    if codec == Codec.H264:
        return "libx264", "h264"
    elif codec == Codec.VP8:
        return "libvpx", "ivf"
    else:
        raise ValueError(f"Unsupported codec: {codec}")
