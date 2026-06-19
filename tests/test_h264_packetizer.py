"""Unit tests for the H264 NAL unit packetizer."""

import pytest

from discord_video_stream.codecs.h264 import (
    split_nalus,
    packetize_h264_frame,
    MTU,
    START_CODE_4,
)


def _make_nal(size: int, nal_type: int = 1) -> bytes:
    """Create a fake NAL unit of *size* bytes with the given type."""
    header = bytes([nal_type & 0x1F])
    body = bytes(range(256)) * (size // 256) + bytes(range(size % 256))
    return header + body[:size - 1]


def test_split_nalus_4byte():
    nal1 = _make_nal(50)
    nal2 = _make_nal(80)
    stream = START_CODE_4 + nal1 + START_CODE_4 + nal2
    result = split_nalus(stream)
    assert result == [nal1, nal2]


def test_single_small_nalu_no_fragmentation():
    nal = _make_nal(100)
    stream = START_CODE_4 + nal
    payloads = packetize_h264_frame(stream)
    assert len(payloads) == 1
    assert payloads[0] == nal


def test_large_nalu_fragmented():
    nal = _make_nal(MTU * 3)
    stream = START_CODE_4 + nal
    payloads = packetize_h264_frame(stream)
    assert len(payloads) > 1
    # All fragments within MTU
    for p in payloads:
        assert len(p) <= MTU


def test_fu_a_start_end_flags():
    """First fragment has FU header S=1; last has E=1."""
    nal = _make_nal(MTU * 2 + 100, nal_type=1)
    stream = START_CODE_4 + nal
    payloads = packetize_h264_frame(stream)
    assert len(payloads) >= 2

    first_fu_header = payloads[0][1]
    last_fu_header = payloads[-1][1]

    assert first_fu_header & 0x80  # S bit set
    assert last_fu_header & 0x40   # E bit set
