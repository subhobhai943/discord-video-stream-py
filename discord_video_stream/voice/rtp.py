"""RTP packet header construction for audio and video streams.

RTP header layout (RFC 3550, 12 bytes)::

  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |V=2|P|X|  CC   |M|     PT      |       sequence number         |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                           timestamp                           |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |           synchronization source (SSRC) identifier           |
 +=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+

Discord video extension header (appended after 12-byte base header
when X=1, used for video metadata)::

  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
  |  0xBE  |  0xDE  |          length (# of 32-bit words)         |
  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
  |  id=5  |  len=2 |  rotation   |   width (px, /4)  |   height  |
  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Discord audio payload type : 0x78 (120)
Discord H264  payload type : 0x65 (101)
Discord VP8   payload type : 0x64 (100)
"""

from __future__ import annotations

import struct

# Payload type constants
AUDIO_PAYLOAD_TYPE = 0x78   # Opus
H264_PAYLOAD_TYPE  = 0x65   # 101
VP8_PAYLOAD_TYPE   = 0x64   # 100

# One-byte RTP extension magic (RFC 5285)
EXTENSION_PROFILE = 0xBEDE


# ---------------------------------------------------------------------------
# Audio header
# ---------------------------------------------------------------------------

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
        32-bit timestamp.  For Opus at 48 kHz: +960 per 20 ms frame.
    ssrc:
        32-bit Synchronization Source identifier.
    """
    # First byte: V=2, P=0, X=0, CC=0 → 0x80
    # Second byte: M=0, PT=0x78
    return struct.pack(
        ">BBHII",
        0x80,
        AUDIO_PAYLOAD_TYPE,
        sequence  & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc      & 0xFFFFFFFF,
    )


# ---------------------------------------------------------------------------
# Video header
# ---------------------------------------------------------------------------

def build_video_rtp_header(
    sequence: int,
    timestamp: int,
    ssrc: int,
    *,
    payload_type: int = H264_PAYLOAD_TYPE,
    marker: bool = False,
    width: int = 0,
    height: int = 0,
    rotation: int = 0,
) -> bytes:
    """
    Build a video RTP header.

    If *width* and *height* are non-zero, a one-byte RTP header extension
    (RFC 5285 / Discord video metadata) is appended.  This lets Discord's
    SFU know the frame dimensions without inspecting the payload.

    Parameters
    ----------
    sequence:
        16-bit sequence number.
    timestamp:
        32-bit timestamp.  For 90 kHz video clock at 30 fps: +3000 per frame.
    ssrc:
        32-bit video SSRC.
    payload_type:
        101 for H264, 100 for VP8.
    marker:
        Set on the **last** RTP packet of every video frame.
    width, height:
        Frame dimensions in pixels.  When non-zero, the Discord video
        extension header is included.
    rotation:
        Video rotation in degrees (0, 90, 180, 270).
    """
    use_extension = width > 0 and height > 0
    extension_bit = 0x10 if use_extension else 0x00

    first_byte  = 0x80 | extension_bit   # V=2, P=0, X=ext, CC=0
    second_byte = (0x80 if marker else 0x00) | (payload_type & 0x7F)

    base = struct.pack(
        ">BBHII",
        first_byte,
        second_byte,
        sequence  & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc      & 0xFFFFFFFF,
    )

    if not use_extension:
        return base

    # One-byte extension header (RFC 5285)
    # profile=0xBEDE, length=1 (one 32-bit word of extension data)
    # Extension element: id=5, len=2 (3 bytes data), then 3 data bytes:
    #   byte0 = rotation, byte1 = width // 4, byte2 = height // 4
    ext_data = struct.pack(
        ">HH",
        EXTENSION_PROFILE,  # 0xBEDE
        1,                  # number of 32-bit words that follow
    )
    # id=5 (4 bits), len=2 meaning 3 bytes data (4 bits), then 3 data bytes, 1 pad
    elem_id_len = (5 << 4) | 2   # id=5, len=2 => 3 bytes
    ext_payload = struct.pack(
        ">BBBB",
        elem_id_len,
        rotation & 0xFF,
        (width  // 4) & 0xFF,
        (height // 4) & 0xFF,
    )
    return base + ext_data + ext_payload


# ---------------------------------------------------------------------------
# Parser (debug / tests)
# ---------------------------------------------------------------------------

def parse_rtp_header(data: bytes) -> dict:
    """Parse a 12-byte RTP header into a dict."""
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
