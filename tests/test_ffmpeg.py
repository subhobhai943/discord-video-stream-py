"""Unit tests for the FFmpeg subprocess builder (media/ffmpeg.py)."""

import pytest

from discord_video_stream.enums import Codec
from discord_video_stream.media.ffmpeg import _codec_args


# ---------------------------------------------------------------------------
# _codec_args
# ---------------------------------------------------------------------------

def test_codec_args_h264_encoder():
    encoder, _fmt = _codec_args(Codec.H264)
    assert encoder == "libx264"


def test_codec_args_h264_format():
    _enc, fmt = _codec_args(Codec.H264)
    assert fmt == "h264"


def test_codec_args_vp8_encoder():
    encoder, _fmt = _codec_args(Codec.VP8)
    assert encoder == "libvpx"


def test_codec_args_vp8_format():
    _enc, fmt = _codec_args(Codec.VP8)
    assert fmt == "ivf"


def test_codec_args_unsupported_raises():
    """An unrecognised codec value should raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported codec"):
        _codec_args("unknown")


def test_codec_args_h264_returns_tuple():
    result = _codec_args(Codec.H264)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_codec_args_vp8_returns_tuple():
    result = _codec_args(Codec.VP8)
    assert isinstance(result, tuple)
    assert len(result) == 2
