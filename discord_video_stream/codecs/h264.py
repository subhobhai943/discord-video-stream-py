"""H264 NAL unit packetizer for RTP (RFC 6184).

Supports:
  - Single NAL unit packets (NAL < MTU)
  - FU-A fragmentation for large NALs (NAL >= MTU)

RFC 6184 FU-A header structure (2 bytes after 12-byte RTP header)::

    FU indicator:
      +---------------+
      |0|1|2|3|4|5|6|7|
      +-+-+-+-+-+-+-+-+
      |F|NRI|  Type   |
      +---------------+
      Type = 28 (0x1C) for FU-A

    FU header:
      +---------------+
      |0|1|2|3|4|5|6|7|
      +-+-+-+-+-+-+-+-+
      |S|E|R|  Type   |
      +---------------+
      S = start bit (first fragment)
      E = end bit   (last fragment)
      R = reserved  (0)
"""

from __future__ import annotations

MTU = 1200  # safe maximum RTP payload size (bytes)

# NAL unit type constants
NAL_TYPE_SPS = 7
NAL_TYPE_PPS = 8
NAL_TYPE_IDR = 5
NAL_TYPE_FU_A = 28

# Annex-B start codes
START_CODE_4 = b"\x00\x00\x00\x01"
START_CODE_3 = b"\x00\x00\x01"


def split_nalus(bitstream: bytes) -> list[bytes]:
    """
    Split an Annex-B H264 bitstream into individual NAL units.
    Strips the 3- or 4-byte start codes.
    """
    nalus: list[bytes] = []
    i = 0
    start = -1

    while i < len(bitstream):
        # Detect 4-byte start code
        if bitstream[i:i+4] == START_CODE_4:
            if start != -1:
                nalus.append(bitstream[start:i])
            start = i + 4
            i += 4
        # Detect 3-byte start code
        elif bitstream[i:i+3] == START_CODE_3:
            if start != -1:
                nalus.append(bitstream[start:i])
            start = i + 3
            i += 3
        else:
            i += 1

    if start != -1 and start < len(bitstream):
        nalus.append(bitstream[start:])

    return [n for n in nalus if n]  # filter empty


def packetize_h264_frame(frame_data: bytes) -> list[bytes]:
    """
    Convert one H264 frame (Annex-B encoded) into a list of RTP payloads.

    Each returned bytes object is the *payload* portion only (no RTP header).
    The caller is responsible for building headers and encrypting.

    Parameters
    ----------
    frame_data:
        Raw H264 frame bytes in Annex-B format (as produced by FFmpeg with
        ``-f h264``).

    Returns
    -------
    list[bytes]
        One or more RTP payload bytes.  The last entry corresponds to the
        last fragment and should have the RTP marker bit set.
    """
    nalus = split_nalus(frame_data)
    payloads: list[bytes] = []

    for nalu in nalus:
        if not nalu:
            continue
        if len(nalu) <= MTU:
            # Single NAL unit packet — payload = raw NAL
            payloads.append(nalu)
        else:
            # FU-A fragmentation
            payloads.extend(_fragment_fu_a(nalu))

    return payloads


def _fragment_fu_a(nalu: bytes) -> list[bytes]:
    """
    Fragment a single large NAL unit into FU-A RTP payloads.
    """
    nal_header = nalu[0]
    nal_type = nal_header & 0x1F
    nal_nri = nal_header & 0x60

    fu_indicator = nal_nri | NAL_TYPE_FU_A  # FU indicator byte

    data = nalu[1:]  # NAL body without header byte
    fragments: list[bytes] = []

    chunk_size = MTU - 2  # 2 bytes for FU indicator + FU header
    i = 0
    while i < len(data):
        chunk = data[i:i + chunk_size]
        start_bit = 0x80 if i == 0 else 0x00
        end_bit = 0x40 if (i + chunk_size) >= len(da