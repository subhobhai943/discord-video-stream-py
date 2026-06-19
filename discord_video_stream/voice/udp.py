"""MediaUdp — UDP socket wrapper for dispatching encrypted RTP packets."""

from __future__ import annotations

import asyncio
import logging
import socket
import time

from .rtp import (
    build_audio_rtp_header,
    build_video_rtp_header,
    H264_PAYLOAD_TYPE,
    VP8_PAYLOAD_TYPE,
)
from .encryption import encrypt_packet
from ..enums import Codec

log = logging.getLogger(__name__)

# 90 kHz video RTP clock
VIDEO_CLOCK_RATE = 90_000
# 48 kHz audio RTP clock, 20 ms frames
AUDIO_SAMPLES_PER_FRAME = 960


class MediaUdp:
    """
    Manages the UDP socket that sends encrypted RTP packets to Discord's
    voice server.

    One instance maps to one voice gateway session.  Obtain via
    :meth:`~discord_video_stream.streamer.Streamer.create_stream`.
    """

    def __init__(
        self,
        ip: str,
        port: int,
        ssrc: int,
        secret_key: list[int],
        encryption_mode: str,
        *,
        codec: Codec = Codec.H264,
        fps: int = 30,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._ip   = ip
        self._port = port
        self._ssrc = ssrc
        self._secret_key      = bytes(secret_key)
        self._encryption_mode = encryption_mode
        self._codec  = codec
        self._fps    = fps
        self._width  = width
        self._height = height

        # Audio RTP state
        self._audio_seq: int = 0
        self._audio_ts:  int = 0

        # Video RTP state
        self._video_seq:  int = 0
        self._video_ts:   int = 0
        self._video_ssrc: int = ssrc + 1
        self._video_ts_increment: int = VIDEO_CLOCK_RATE // fps  # e.g. 3000 @ 30fps

        # Payload type for the chosen codec
        self._video_pt = H264_PAYLOAD_TYPE if codec == Codec.H264 else VP8_PAYLOAD_TYPE

        self._sock: socket.socket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Wall-clock anchor for A/V sync
        self._stream_start_wall: float | None = None
        self._stream_start_audio_ts: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the UDP socket and record the stream start time."""
        self._loop = asyncio.get_event_loop()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._stream_start_wall = time.monotonic()
        log.info(
            "MediaUdp ready → %s:%d  SSRC=%d  video_SSRC=%d  mode=%s",
            self._ip, self._port, self._ssrc, self._video_ssrc, self._encryption_mode,
        )

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

        The audio RTP timestamp increments by 960 samples per call
        (48 000 Hz × 0.02 s).
        """
        header = build_audio_rtp_header(
            sequence=self._audio_seq,
            timestamp=self._audio_ts,
            ssrc=self._ssrc,
        )
        packet = encrypt_packet(header, opus_frame, self._secret_key, self._encryption_mode)
        await self._send_raw(packet)

        self._audio_seq = (self._audio_seq + 1) & 0xFFFF
        self._audio_ts  = (self._audio_ts + AUDIO_SAMPLES_PER_FRAME) & 0xFFFFFFFF

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------

    async def send_video_packets(
        self,
        rtp_payloads: list[bytes],
        *,
        is_keyframe: bool = False,
        width:  int | None = None,
        height: int | None = None,
    ) -> None:
        """
        Send a list of RTP payload fragments for **one video frame**.

        The RTP marker bit is automatically set on the last fragment.
        Discord video metadata extension header is included on the
        first packet of each keyframe.

        Parameters
        ----------
        rtp_payloads:
            Packetized NAL unit / VP8 payload bytes (each already within MTU).
        is_keyframe:
            Whether this frame is an IDR / keyframe.
        width, height:
            Override frame dimensions for the extension header.  Defaults
            to the dimensions passed when constructing :class:`MediaUdp`.
        """
        if not rtp_payloads:
            return

        frame_width  = width  or self._width
        frame_height = height or self._height
        n = len(rtp_payloads)

        for i, payload in enumerate(rtp_payloads):
            is_last = (i == n - 1)
            # Include video extension header on the first packet of keyframes
            include_ext = is_keyframe and (i == 0)

            header = build_video_rtp_header(
                sequence=self._video_seq,
                timestamp=self._video_ts,
                ssrc=self._video_ssrc,
                payload_type=self._video_pt,
                marker=is_last,
                width=frame_width  if include_ext else 0,
                height=frame_height if include_ext else 0,
            )
            packet = encrypt_packet(header, payload, self._secret_key, self._encryption_mode)
            await self._send_raw(packet)
            self._video_seq = (self._video_seq + 1) & 0xFFFF

        self._video_ts = (self._video_ts + self._video_ts_increment) & 0xFFFFFFFF

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_raw(self, data: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("MediaUdp not started — call start() first.")
        await self._loop.sock_sendto(self._sock, data, (self._ip, self._port))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

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
        """Negotiated SRTP encryption mode."""
        return self._encryption_mode

    @property
    def fps(self) -> int:
        """Target frames per second."""
        return self._fps
