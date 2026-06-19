"""Opus audio framer — reads raw Opus frames from FFmpeg stdout.

FFmpeg command for Opus extraction::

    ffmpeg -i input.mp4 \\
        -ac 2 -ar 48000 \\
        -c:a libopus -b:a 128k \\
        -application lowdelay \\
        -frame_duration 20 \\
        -f opus pipe:1

Each packet in the Ogg/Opus pipe starts with an Ogg page header.
For real-time RTP delivery we use the raw Opus framer instead:

    ffmpeg -i input.mp4 \\
        -ac 2 -ar 48000 \\
        -c:a libopus -b:a 128k \\
        -vn -f data pipe:1

The raw output is a stream of length-prefixed Opus frames.
"""

from __future__ import annotations

import struct
from typing import AsyncGenerator

# Opus at 48 kHz, 2 ch, 20 ms per frame = 960 samples per frame
OPUS_SAMPLE_RATE = 48_000
OPUS_CHANNELS = 2
OPUS_FRAME_DURATION_MS = 20
OPUS_SAMPLES_PER_FRAME = OPUS_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000  # 960

# Maximum Opus frame size (2.5 s at 510 kbps = ~160 kB; practical max is much smaller)
OPUS_MAX_FRAME_SIZE = 4000


class OpusFramer:
    """
    Reads length-prefixed raw Opus frames produced by FFmpeg's custom pipe output.

    FFmpeg with ``-c:a libopus -f data`` writes 2-byte big-endian length
    headers before each Opus frame.  This class consumes that byte stream
    from a :class:`asyncio.StreamReader` and yields individual frames.
    """

    def __init__(self, reader: "asyncio.StreamReader") -> None:
        self._reader = reader

    async def frames(self) -> AsyncGenerator[bytes, None]:
        """
        Async generator that yields individual Opus frames (bytes) until EOF.
        """
        while True:
            # Read 2-byte length header
            length_bytes = await self._reader.readexactly(2)
            (length,) = struct.unpack(">H", length_bytes)
            if length == 0 or length > OPUS_MAX_FRAME_SIZE:
                # Malformed stream — try to re-sync by skipping
                continue
            frame = await self._reader.readexactly(length)
            yield frame


async def read_opus_frames_from_pipe(pipe_stdout) -> AsyncGenerator[bytes, None]:
    """
    Convenience async generator to read length-prefixed Opus frames
    from a raw ``asyncio.subprocess`` stdout pipe.

    Yields
    ------
    bytes
        One Opus frame (20 ms) per iteration.
    """
    import asyncio
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, pipe_stdout)
    framer = OpusFramer(reader)
    async for frame in framer.frames():
        yield frame
