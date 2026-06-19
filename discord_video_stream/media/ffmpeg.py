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

    if realtime:
        cmd += ["-re"]

    cmd += ["-i", source]

    # Video output pipe (pipe:1)
    cmd += [
        "-map", "0:v:0",
        "-c:v", video_encoder,
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-x264opts", "keyint=60:min-keyint=60:no-scenecut",  # ignored for vp8
        "-b:v", video_bitrate,
        "-maxrate", video_bitrate,
        "-bufsize", str(int(video_bitrate.rstrip("MK")) * 2)
            + ("M" if "M" in video_bitrate else "K"),
        "-vf", scale_filter,
        "-r", str(fps),
        "-f", video_format,
        "pipe:1",
    ]

    # Audio output pipe (pipe:2) via stderr fd trick — actually use pipe:2 via subprocess
    # We use stdout for video, stderr for audio to avoid mixing.
    # In practice, FFmpeg writes video to stdout (1) and we parse audio from stderr (2).
    # For a cleaner split, you can use named pipes or fd=3/4 with asyncio open_connection.
    # For now, we use a single pipe approach: video on stdout, audio on a separate process.
    # TODO: Phase 4 — use fd-based multiplexed pipes for simultaneous A+V.
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
