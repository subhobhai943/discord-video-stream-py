"""Unit tests for the H264 NAL unit packetizer (Phase 2 complete)."""

import pytest

from discord_video_stream.codecs.h264 import (
    split_nalus,
    packetize_h264_frame,
    extract_sps_pps,
    is_keyframe,
    nal_type,
    _fragment_fu_a,
    _split_next_frame,
    MTU,
    START_CODE_4,
    START_CODE_3,
    NAL_TYPE_SPS,
    NAL_TYPE_PPS,
    NAL_TYPE_IDR,
    NAL_TYPE_AUD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_nal(size: int, nal_type_val: int = 1) -> bytes:
    """Create a fake NAL unit of *size* bytes with the given type."""
    header = bytes([nal_type_val & 0x1F])
    body   = (bytes(range(256)) * ((size) // 256 + 1))[:size]
    return (header + body)[:size]


# ---------------------------------------------------------------------------
# split_nalus
# ---------------------------------------------------------------------------

def test_split_nalus_4byte_start_codes():
    n1, n2 = _make_nal(50, 1), _make_nal(80, 1)
    stream = START_CODE_4 + n1 + START_CODE_4 + n2
    assert split_nalus(stream) == [n1, n2]


def test_split_nalus_3byte_start_codes():
    n1, n2 = _make_nal(30, 1), _make_nal(40, 1)
    stream = START_CODE_3 + n1 + START_CODE_3 + n2
    assert split_nalus(stream) == [n1, n2]


def test_split_nalus_empty():
    assert split_nalus(b"") == []


# ---------------------------------------------------------------------------
# nal_type / is_keyframe
# ---------------------------------------------------------------------------

def test_nal_type_idr():
    assert nal_type(bytes([NAL_TYPE_IDR])) == NAL_TYPE_IDR


def test_is_keyframe_true():
    nalus = [_make_nal(20, NAL_TYPE_IDR)]
    assert is_keyframe(nalus)


def test_is_keyframe_false():
    nalus = [_make_nal(20, 1)]
    assert not is_keyframe(nalus)


# ---------------------------------------------------------------------------
# extract_sps_pps
# ---------------------------------------------------------------------------

def test_extract_sps_pps():
    sps = _make_nal(30, NAL_TYPE_SPS)
    pps = _make_nal(10, NAL_TYPE_PPS)
    idr = _make_nal(200, NAL_TYPE_IDR)
    stream = START_CODE_4 + sps + START_CODE_4 + pps + START_CODE_4 + idr
    sps_list, pps_list = extract_sps_pps(stream)
    assert sps_list == [sps]
    assert pps_list == [pps]


# ---------------------------------------------------------------------------
# packetize_h264_frame
# ---------------------------------------------------------------------------

def test_single_small_nalu():
    nalu = _make_nal(100, 1)
    payloads = packetize_h264_frame(START_CODE_4 + nalu)
    assert payloads == [nalu]


def test_large_nalu_fragmented_within_mtu():
    nalu = _make_nal(MTU * 3, 1)
    payloads = packetize_h264_frame(START_CODE_4 + nalu)
    assert len(payloads) > 1
    for p in payloads:
        assert len(p) <= MTU


def test_aud_stripped():
    aud  = _make_nal(2, NAL_TYPE_AUD)
    nalu = _make_nal(50, 1)
    payloads = packetize_h264_frame(START_CODE_4 + aud + START_CODE_4 + nalu)
    # AUD should not appear in payloads
    for p in payloads:
        assert nal_type(p) != NAL_TYPE_AUD


def test_sps_pps_injected_before_idr():
    sps = _make_nal(30, NAL_TYPE_SPS)
    pps = _make_nal(10, NAL_TYPE_PPS)
    idr = _make_nal(200, NAL_TYPE_IDR)
    stream = START_CODE_4 + sps + START_CODE_4 + pps + START_CODE_4 + idr
    payloads = packetize_h264_frame(stream)
    types = [nal_type(p) for p in payloads]
    # SPS must appear before IDR
    assert NAL_TYPE_SPS in types
    assert NAL_TYPE_PPS in types
    assert types.index(NAL_TYPE_SPS) < types.index(NAL_TYPE_IDR)


# ---------------------------------------------------------------------------
# FU-A fragmentation
# ---------------------------------------------------------------------------

def test_fu_a_start_end_flags():
    nalu = _make_nal(MTU * 2 + 100, 1)
    fragments = _fragment_fu_a(nalu)
    assert len(fragments) >= 2
    assert fragments[0][1]  & 0x80  # S bit on first
    assert fragments[-1][1] & 0x40  # E bit on last
    # Middle fragments should have neither S nor E
    if len(fragments) > 2:
        mid = fragments[1]
        assert not (mid[1] & 0x80)
        assert not (mid[1] & 0x40)


def test_fu_a_type_preserved():
    """FU header type field must equal original NAL type."""
    nal_type_val = 1
    nalu = _make_nal(MTU + 100, nal_type_val)
    fragments = _fragment_fu_a(nalu)
    for frag in fragments:
        assert (frag[1] & 0x1F) == nal_type_val


# ---------------------------------------------------------------------------
# _split_next_frame
# ---------------------------------------------------------------------------

def test_split_next_frame_finds_boundary():
    n1 = _make_nal(100, 1)
    n2 = _make_nal(80, 1)
    buf = START_CODE_4 + n1 + START_CODE_4 + n2
    frame, remainder = _split_next_frame(buf)
    assert frame is not None
    assert START_CODE_4 + n2 == remainder


def test_split_next_frame_incomplete():
    buf = START_CODE_4 + _make_nal(50, 1)
    frame, remainder = _split_next_frame(buf)
    assert frame is None
    assert remainder == buf
