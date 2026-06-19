"""Unit tests for the RTP header builder and parser."""

import struct
import pytest

from discord_video_stream.voice.rtp import (
    build_audio_rtp_header,
    build_video_rtp_header,
    parse_rtp_header,
    AUDIO_PAYLOAD_TYPE,
    H264_PAYLOAD_TYPE,
)


def test_audio_header_length():
    header = build_audio_rtp_header(sequence=1, timestamp=960, ssrc=12345)
    assert len(header) == 12


def test_audio_header_fields():
    header = build_audio_rtp_header(sequence=42, timestamp=1920, ssrc=99999)
    parsed = parse_rtp_header(header)
    assert parsed["version"] == 2
    assert parsed["payload_type"] == AUDIO_PAYLOAD_TYPE
    assert parsed["sequence"] == 42
    assert parsed["timestamp"] == 1920
    assert parsed["ssrc"] == 99999
    assert not parsed["marker"]


def test_video_header_marker_bit():
    header = build_video_rtp_header(sequence=7, timestamp=3000, ssrc=100, marker=True)
    parsed = parse_rtp_header(header)
    assert parsed["marker"] is True
    assert parsed["payload_type"] == H264_PAYLOAD_TYPE


def test_sequence_wrap():
    header = build_audio_rtp_header(sequence=0xFFFF + 1, timestamp=0, ssrc=1)
    parsed = parse_rtp_header(header)
    assert parsed["sequence"] == 0  # wrapped to 0
