"""Unit tests for the Opus framer (codecs/opus.py)."""

import asyncio
import struct
import pytest

from discord_video_stream.codecs.opus import (
    OPUS_SAMPLE_RATE,
    OPUS_CHANNELS,
    OPUS_FRAME_DURATION_MS,
    OPUS_SAMPLES_PER_FRAME,
    OPUS_MAX_FRAME_SIZE,
    OpusFramer,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_sample_rate():
    assert OPUS_SAMPLE_RATE == 48_000


def test_channels():
    assert OPUS_CHANNELS == 2


def test_frame_duration_ms():
    assert OPUS_FRAME_DURATION_MS == 20


def test_samples_per_frame():
    assert OPUS_SAMPLES_PER_FRAME == 960


def test_samples_per_frame_formula():
    assert OPUS_SAMPLES_PER_FRAME == OPUS_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000


# ---------------------------------------------------------------------------
# Helpers: build length-prefixed data for a mock StreamReader
# ---------------------------------------------------------------------------

def _length_prefixed(payload: bytes) -> bytes:
    """Return a 2-byte big-endian length header followed by *payload*."""
    return struct.pack(">H", len(payload)) + payload


def _make_reader(data: bytes) -> asyncio.StreamReader:
    """Create a StreamReader pre-loaded with *data* then fed EOF."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


# ---------------------------------------------------------------------------
# OpusFramer.frames()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_single_frame():
    payload = b"\xfc\x01\x02\x03"
    reader = _make_reader(_length_prefixed(payload))
    framer = OpusFramer(reader)

    frames = []
    try:
        async for frame in framer.frames():
            frames.append(frame)
    except asyncio.IncompleteReadError:
        pass

    assert frames == [payload]


@pytest.mark.asyncio
async def test_read_multiple_frames():
    p1 = b"\xaa" * 100
    p2 = b"\xbb" * 200
    p3 = b"\xcc" * 50
    data = _length_prefixed(p1) + _length_prefixed(p2) + _length_prefixed(p3)
    reader = _make_reader(data)
    framer = OpusFramer(reader)

    frames = []
    try:
        async for frame in framer.frames():
            frames.append(frame)
    except asyncio.IncompleteReadError:
        pass

    assert len(frames) == 3
    assert frames[0] == p1
    assert frames[1] == p2
    assert frames[2] == p3


@pytest.mark.asyncio
async def test_empty_stream_raises_incomplete_read():
    """An empty stream should raise IncompleteReadError on first read."""
    reader = _make_reader(b"")
    framer = OpusFramer(reader)

    frames = []
    with pytest.raises(asyncio.IncompleteReadError):
        async for frame in framer.frames():
            frames.append(frame)

    assert frames == []


@pytest.mark.asyncio
async def test_truncated_header_raises_incomplete_read():
    """Only 1 byte available when 2-byte header is expected."""
    reader = _make_reader(b"\x00")
    framer = OpusFramer(reader)

    frames = []
    with pytest.raises(asyncio.IncompleteReadError):
        async for frame in framer.frames():
            frames.append(frame)

    assert frames == []


@pytest.mark.asyncio
async def test_truncated_payload_raises_incomplete_read():
    """Header says 10 bytes but only 5 are available."""
    header = struct.pack(">H", 10)
    reader = _make_reader(header + b"\x01" * 5)
    framer = OpusFramer(reader)

    frames = []
    with pytest.raises(asyncio.IncompleteReadError):
        async for frame in framer.frames():
            frames.append(frame)

    assert frames == []


@pytest.mark.asyncio
async def test_zero_length_frame_skipped():
    """A zero-length header should be skipped (re-sync), followed by a valid frame."""
    valid_payload = b"\xdd" * 20
    data = struct.pack(">H", 0) + _length_prefixed(valid_payload)
    reader = _make_reader(data)
    framer = OpusFramer(reader)

    frames = []
    try:
        async for frame in framer.frames():
            frames.append(frame)
    except asyncio.IncompleteReadError:
        pass

    assert frames == [valid_payload]


@pytest.mark.asyncio
async def test_oversized_length_skipped():
    """A length exceeding OPUS_MAX_FRAME_SIZE should be skipped."""
    oversized_len = OPUS_MAX_FRAME_SIZE + 1
    valid_payload = b"\xee" * 30
    # The oversized header is followed by another valid frame header.
    # After skipping, the framer reads the next 2-byte header.
    data = struct.pack(">H", oversized_len) + _length_prefixed(valid_payload)
    reader = _make_reader(data)
    framer = OpusFramer(reader)

    frames = []
    try:
        async for frame in framer.frames():
            frames.append(frame)
    except asyncio.IncompleteReadError:
        pass

    assert frames == [valid_payload]
