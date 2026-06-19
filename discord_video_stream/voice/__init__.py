"""Voice connection — gateway, UDP, RTP, encryption.

Re-exports the main classes for convenience::

    from discord_video_stream.voice import VoiceGateway, MediaUdp
"""

from .gateway import VoiceGateway
from .udp import MediaUdp
from .encryption import encrypt_packet
from .client import VoiceStreamClient

__all__ = ["VoiceGateway", "MediaUdp", "encrypt_packet", "VoiceStreamClient"]

