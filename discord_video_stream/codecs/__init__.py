"""Codec packetizers: H264 (NAL), VP8, and Opus.

Re-exports the main packetizer functions::

    from discord_video_stream.codecs import packetize_h264_frame, packetize_vp8_frame
"""

from .h264 import (
    H264FrameReader,
    packetize_h264_frame,
    split_nalus,
    is_keyframe,
    extract_sps_pps,
    nal_type,
)
from .vp8 import packetize_vp8_frame
from .opus import OpusFramer, read_opus_frames_from_pipe

__all__ = [
    "H264FrameReader",
    "packetize_h264_frame",
    "split_nalus",
    "is_keyframe",
    "extract_sps_pps",
    "nal_type",
    "packetize_vp8_frame",
    "OpusFramer",
    "read_opus_frames_from_pipe",
]
