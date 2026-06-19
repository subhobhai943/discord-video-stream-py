"""VP8 RTP payload packetizer (RFC 7741).

VP8 RTP payload descriptor (simplified, non-extended)::

  0                   1
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |X|R|N|S|R| PID  |  (optional) |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

  X   = 1 if extension fields present
  S   = 1 on first fragment of a VP8 partition
  PID = partition index (0 for first and only partition)
"""

from __future__ import annotations

MTU = 1200


def packetize_vp8_frame(frame_data: bytes) -> list[bytes]:
    """
    Packetize one raw VP8 frame into a list of RTP payloads.

    Each returned bytes object is the *payload* only (no RTP header).
    The last entry should carry the RTP marker bit.

    Parameters
    ----------
    frame_data:
        Raw VP8 bitstream bytes for one frame (from FFmpeg ``-f rawvideo`` with
        libvpx encoding piped to stdout, or a VP8 IVF container demuxed).

    Returns
    -------
    list[bytes]
        RTP payloads with VP8 payload descriptor prepended.
    """
    payloads: list[bytes] = []
    max_payload = MTU - 1  # 1 byte for VP8 payload descriptor
    i = 0
    first = True

    while i < len(frame_data):
        chunk = frame_data[i : i + max_payload]

        # VP8 payload descriptor
        s_bit = 0x10 if first else 0x00  # S=1 on first fragment
        descriptor = bytes([s_bit])       # X=0, R=0, N=0, S, R, PID=0

        payloads.append(descriptor + chunk)
        i += max_payload
        first = False

    return payloads
