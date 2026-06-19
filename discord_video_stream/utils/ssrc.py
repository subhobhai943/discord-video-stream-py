"""SSRC generation and video SSRC offset management.

SSRC (Synchronization Source) identifiers must be unique per RTP session.
Discord uses:
  - ssrc       → audio stream
  - ssrc + 1   → video stream
  - ssrc + 2   → video RTX (retransmission) stream
"""

from __future__ import annotations

import os
import struct


def generate_ssrc() -> int:
    """
    Generate a random 32-bit SSRC suitable for an RTP session.
    Uses OS-level random bytes for unpredictability.
    """
    return struct.unpack(">I", os.urandom(4))[0]


def video_ssrc(base_ssrc: int) -> int:
    """Return the video SSRC derived from the base (audio) SSRC."""
    return (base_ssrc + 1) & 0xFFFFFFFF


def rtx_ssrc(base_ssrc: int) -> int:
    """Return the RTX (retransmission) SSRC derived from the base SSRC."""
    return (base_ssrc + 2) & 0xFFFFFFFF
