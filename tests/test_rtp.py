"""Unit tests for the RTP header builder and parser (Phase 2)."""

import struct
import pytest

from discord_video_stream.voice.rtp import (
    build_audio_rtp_header,
    build_video_rtp_header,
    parse_rtp_header,
    AUDIO_PAYLOAD_TYPE,
    H264_PAYLOAD_TYPE,
    VP8_PAYLOAD_TYPE,
    EXTENSION_PROFILE,
)


# ---------------------------------------------------------------------------
# Audio header
# ---------------------------------------------------------------------------

def test_audio_header_length():
    h = build_audio_rtp_header(sequence=1, timestamp=960, ssrc=12345)
    assert len(h) == 12


def test_audio_header_fields():
    h = build_audio_rtp_header(sequence=42, timestamp=1920, ssrc=99999)
    p = parse_rtp_header(h)
    assert p["version"]      == 2
    assert p["payload_type"] == AUDIO_PAYLOAD_TYPE
    assert p["sequence"]     == 42
    assert p["timestamp"]    == 1920
    assert p["ssrc"]         == 99999
    assert not p["marker"]
    assert not p["extension"]


def test_audio_sequence_wrap():
    h = build_audio_rtp_header(sequence=0x10000, timestamp=0, ssrc=1)
    p = parse_rtp_header(h)
    assert p["sequence"] == 0


# ---------------------------------------------------------------------------
# Video header — no extension
# ---------------------------------------------------------------------------

def test_video_header_no_extension():
    h = build_video_rtp_header(sequence=7, timestamp=3000, ssrc=100)
    assert len(h) == 12
    p = parse_rtp_header(h)
    assert p["payload_type"] == H264_PAYLOAD_TYPE
    assert not p["extension"]
    assert not p["marker"]


def test_video_header_marker_bit():
    h = build_video_rtp_header(sequence=7, timestamp=3000, ssrc=100, marker=True)
    p = parse_rtp_header(h)
    assert p["marker"] is True


def test_video_header_vp8_payload_type():
    h = build_video_rtp_header(
        sequence=1, timestamp=3000, ssrc=50,
        payload_type=VP8_PAYLOAD_TYPE
    )
    p = parse_rtp_header(h)
    assert p["payload_type"] == VP8_PAYLOAD_TYPE


# ---------------------------------------------------------------------------
# Video header — with extension (Discord video metadata)
# ---------------------------------------------------------------------------

def test_video_header_extension_present():
    h = build_video_rtp_header(
        sequence=1, timestamp=3000, ssrc=100,
        width=1280, height=720,
    )
    p = parse_rtp_header(h)
    assert p["extension"] is True
    # Total length: 12 (base) + 4 (ext header) + 8 (ext payload) = 24
    assert len(h) == 24


def test_video_header_extension_profile():
    h = build_video_rtp_header(
        sequence=1, timestamp=3000, ssrc=100,
        width=1280, height=720,
    )
    # Bytes 12-13 should be 0xBEDE
    profile = struct.unpack_from(">H", h, 12)[0]
    assert profile == EXTENSION_PROFILE


def test_video_header_extension_dimensions():
    h = build_video_rtp_header(
        sequence=1, timestamp=3000, ssrc=100,
        width=1280, height=720,
    )
    # Extension payload starts at byte 16
    # byte 16 = id/len (0x55), bytes 17-18 = rotation (16-bit BE),
    # bytes 19-20 = width (16-bit BE), bytes 21-22 = height (16-bit BE)
    assert struct.unpack_from(">H", h, 19)[0] == 1280
    assert struct.unpack_from(">H", h, 21)[0] == 720
