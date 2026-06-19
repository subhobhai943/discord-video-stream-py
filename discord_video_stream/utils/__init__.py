"""Utility helpers.

Re-exports SSRC utilities::

    from discord_video_stream.utils import generate_ssrc, video_ssrc, rtx_ssrc
"""

from .ssrc import generate_ssrc, video_ssrc, rtx_ssrc

__all__ = ["generate_ssrc", "video_ssrc", "rtx_ssrc"]
