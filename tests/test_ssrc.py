"""Unit tests for SSRC generation and offset helpers (utils/ssrc.py)."""

import pytest

from discord_video_stream.utils.ssrc import generate_ssrc, video_ssrc, rtx_ssrc


# ---------------------------------------------------------------------------
# generate_ssrc
# ---------------------------------------------------------------------------

def test_generate_ssrc_returns_int():
    ssrc = generate_ssrc()
    assert isinstance(ssrc, int)


def test_generate_ssrc_32_bit_range():
    ssrc = generate_ssrc()
    assert 0 <= ssrc <= 0xFFFFFFFF


def test_generate_ssrc_randomness():
    """Two calls should almost certainly produce different values."""
    results = {generate_ssrc() for _ in range(10)}
    # With 2^32 possibilities, 10 values should be distinct
    assert len(results) > 1


# ---------------------------------------------------------------------------
# video_ssrc
# ---------------------------------------------------------------------------

def test_video_ssrc_basic():
    assert video_ssrc(100) == 101


def test_video_ssrc_zero():
    assert video_ssrc(0) == 1


def test_video_ssrc_large():
    assert video_ssrc(0x7FFFFFFF) == 0x80000000


def test_video_ssrc_wraps_at_max():
    assert video_ssrc(0xFFFFFFFF) == 0


def test_video_ssrc_near_max():
    assert video_ssrc(0xFFFFFFFE) == 0xFFFFFFFF


# ---------------------------------------------------------------------------
# rtx_ssrc
# ---------------------------------------------------------------------------

def test_rtx_ssrc_basic():
    assert rtx_ssrc(100) == 102


def test_rtx_ssrc_zero():
    assert rtx_ssrc(0) == 2


def test_rtx_ssrc_large():
    assert rtx_ssrc(0x7FFFFFFF) == 0x80000001


def test_rtx_ssrc_wraps_at_max():
    assert rtx_ssrc(0xFFFFFFFF) == 1


def test_rtx_ssrc_wraps_at_max_minus_1():
    assert rtx_ssrc(0xFFFFFFFE) == 0


# ---------------------------------------------------------------------------
# Relationship invariants
# ---------------------------------------------------------------------------

def test_video_is_base_plus_one():
    base = generate_ssrc()
    assert video_ssrc(base) == (base + 1) & 0xFFFFFFFF


def test_rtx_is_base_plus_two():
    base = generate_ssrc()
    assert rtx_ssrc(base) == (base + 2) & 0xFFFFFFFF


def test_rtx_is_video_plus_one():
    base = generate_ssrc()
    assert rtx_ssrc(base) == (video_ssrc(base) + 1) & 0xFFFFFFFF
