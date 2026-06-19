"""RTP packet header construction for audio and video streams.

RTP header layout (RFC 3550):
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |V=2|P|X|  CC   |M|     PT      |       sequence number         |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                           timestamp                           |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |           synchronization source (SSRC) identifier           |
 +=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+

Discord audio payload type: 0x78 (120)
Discord video payload type: 0x65 (101) for H264, 0x64 (100) for VP8
"""

import struct

# Payload type constants
AUDIO_PAYLOAD_TYPE = 0x78  # Opus
H264_PAYLOAD_TYPE  = 0x65  # 101
VP8_PAYLOAD_TYPE   = 0x64  # 100


def build_audio_rtp_header(
    sequence: int,
    timestamp: int,
    ssrc: int,
) -> bytes:
    """
    Build a 12-byte RTP header for an Opus audio packet.

    Parameters
    ----------
    sequence:
        16-bit sequence number (wraps at 0xFFFF).
    timestamp:
        32-bit timestamp. For Opus at 48 kHz: increments by 960 per 20 ms frame.
    ssrc:
        32-bit Synchronization Source identifier.
    """
    # First byte: V=2, P=0, X=0, CC=0  →  0x80
    # Second byte: M=0, PT=0x78        →  0x78
    return struct.pack(
        ">BBHII",
        0x80,               # version=2, no padding, no extension, CC=0
        AUDIO_PAYLOAD_TYPE, # marker=0, payload type
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF,
    )


def build_video_rtp_header(
    sequence: int,
    timestamp: int,
    ssrc: int,
    *,
    payload_type: int = H264_PAYLOAD_TYPE,
    marker: bool = False,
) -> bytes:
    """
    Build a 12-byte RTP header for a video packet.

    Parameters
    ----------
    sequence:
        16-bit sequence number.
    timestamp:
        32-bit timestamp. For video at 90 kHz: increments by 3000 per 30 fps frame.
    ssrc:
        32-bit SSRC for the video stream.
    payload_type:
        Payload type for H264 (101) or VP8 (100).
    marker:
        Set to True on the last RTP packet of a video frame.
    """
    second_byte = (0x80 if marker else 0x00) | (payload_type & 0x7F)
    return struct.pack(
        ">BBHII",
        0x80,          # V=2, P=0, X=0, CC=0
        second_byte,
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF,
    )


def parse_rtp_header(data: bytes) -> dict:
    """
    Parse a 12-byte RTP header into a dict.
    Useful for debugging and testing.
    """
    if len(data) < 12:
        raise ValueError(f"RTP header too short: {len(data)} bytes")
    first, second, seq, ts, ssrc = struct.unpack_from(">BBHII", data, 0)
    return {
        "version":      (first >> 6) & 0x3,
        "padding":      bool(first & 0x20),
        "extension":    bool(first & 0x10),
        "csrc_count":   first & 0x0F,
        "marker":       bool(second & 0x80),
        "payload_type": second & 0x7F,
        "sequence":     seq,
        "timestamp":    ts,
        "ssrc":         ssrc,
    }
