"""MediaUdp — UDP socket wrapper for dispatching encrypted RTP packets."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from collections.abc import Callable

from .rtp import build_audio_rtp_header, build_video_rtp_header
from .encryption import encrypt_packet

log = logging.getLogger(__name__)

# Discord voice server MTU safe ceiling
RTP_MAX_PAYLOAD = 1200


class MediaUdp:
    """
    Manages the UDP socket used to send encrypted RTP packets to Discord's
    voice server.

    One instance is tied to a single voice gateway session.  Create it via
    :meth:`Streamer.create_stream`.
    """

    def __init__(
        self,
        ip: str,
        port: int,
        ssrc: int,
        secret_key: list[int],
        encryption_mode: str,
    ) -> None:
        self._ip = ip
        self._port = port
        self._ssrc = ssrc
        self._secret_key = bytes(secret_key)
        self._encryption_mode = encryption_mode

        # Audio RTP state
        self._audio_seq: int = 0
        self._audio_ts: int = 0

        # Video RTP state
        self._video_seq: int = 0
        self._video_ts: int = 0
        self._video_ssrc: int = ssrc + 1

        self._sock: socket.socket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the UDP socket."""
        self._loop = asyncio.get_event_loop()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        log.info("MediaUdp ready, sending to %s:%d (SSRC=%d)", self._ip, self._port, self._ssrc)

    async def stop(self) -> None:
        """Close the UDP socket."""
        if self._sock:
            self._sock.close()
            self._sock = None
        log.info("MediaUdp stopped.")

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    async def send_audio_frame(self, opus_frame: bytes) -> None:
        """
        Packetize and send one 20 ms Opus audio frame.

        Parameters
        ----------
        opus_frame:
            Raw Opus-encoded bytes for a single 20 ms frame.
        """
        header = build_audio_rtp_header(
            sequence=self._audio_seq,
            timestamp=self._audio_ts,
            ssrc=self._ssrc,
        )
        packet = encrypt_packet(
            header=header,
            payload=opus_frame,
            secret_key=self._secret_key,
            mode=self._encryption_mode,
        )
        await self._send_raw(packet)
        self._audio_seq = (self._audio_seq + 1) & 0xFFFF
        self._audio_ts += 960  # 48000 Hz / 20 ms = 960 samples

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------

    async def send_video_packets(self, rtp_payloads: list[bytes], is_keyframe: bool = False) -> None:
        """
        Send a list of RTP payload fragments for one video frame.

        Parameters
        ----------
        rtp_payloads:
            List of packetized NAL/VP8 payload bytes (already fragmented to MTU).
        is_keyframe:
            Whether this is a keyframe/IDR frame.
        """
        n = len(rtp_payloads)
        for i, payload in enumerate(rtp_payloads):
            marker = (i == n - 1)  # set on last packet of a frame
            header = build_video_rtp_header(
                sequence=self._video_seq,
                timestamp=self._video_ts,
                ssrc=self._video_ssrc,
                marker=marker,
            )
            packet = encrypt_packet(
                header=header,
                payload=payload,
                secret_key=self._secret_key,
                mode=self._encryption_mode,
            )
            await self._send_raw(packet)
            self._video_seq = (self._video_seq + 1) & 0xFFFF

        # Advance video timestamp: 90kHz clock, assuming 30fps = 3000 ticks
        self._video_ts += 3000

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_raw(self, data: bytes) -> None:
        """Send raw bytes over the UDP socket."""
        if self._sock is None:
            raise RuntimeError("MediaUdp not started — call start() first.")
        await self._loop.sock_sendto(self._sock, data, (self._ip, self._port))

    @property
    def ssrc(self) -> int:
        """Audio SSRC."""
        return self._ssrc

    @property
    def video_ssrc(self) -> int:
        """Video SSRC (audio SSRC + 1)."""
        return self._video_ssrc

    @property
    def encryption_mode(self) -> str:
        """Negotiated encryption mode string."""
        return self._encryption_mode
