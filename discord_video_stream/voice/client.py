"""VoiceStreamClient subclassing discord.VoiceProtocol."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from ..enums import Codec, Resolution, StreamType
from .gateway import VoiceGateway
from .udp import MediaUdp

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class VoiceStreamClient(discord.VoiceProtocol):
    """
    A subclass of ``discord.VoiceProtocol`` for streaming video and audio.

    This can be passed directly to ``VoiceChannel.connect``:

    .. code-block:: python

        voice_client = await channel.connect(cls=VoiceStreamClient)
        udp = await voice_client.create_stream(resolution="720p", fps=30)
        player = VideoPlayer("video.mp4", udp)
        await player.play()
    """

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable) -> None:
        super().__init__(client, channel)
        self._gateway: VoiceGateway | None = None
        self._udp: MediaUdp | None = None
        self._voice_state_future: asyncio.Future[dict] = asyncio.Future()
        self._voice_server_future: asyncio.Future[dict] = asyncio.Future()
        self._voice_state: dict | None = None
        self._voice_server: dict | None = None

    async def connect(
        self,
        *,
        timeout: float = 30.0,
        reconnect: bool = True,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        """Called when the client initiates connection."""
        log.info("Connecting voice stream client to channel %d", self.channel.id)

        # Reset futures in case they were previously resolved
        if self._voice_state_future.done():
            self._voice_state_future = asyncio.Future()
        if self._voice_server_future.done():
            self._voice_server_future = asyncio.Future()

        # Join the voice channel
        await self.channel.guild.change_voice_state(
            channel=self.channel,
            self_mute=self_mute,
            self_deaf=self_deaf,
        )

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    self._voice_state_future,
                    self._voice_server_future,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.error("Timed out waiting for voice state and server updates.")
            raise

    async def on_voice_state_update(self, data: dict) -> None:
        """Called when VOICE_STATE_UPDATE is received."""
        log.debug("Received voice state update payload: %s", data)
        self._voice_state = data
        if not self._voice_state_future.done():
            self._voice_state_future.set_result(data)

    async def on_voice_server_update(self, data: dict) -> None:
        """Called when VOICE_SERVER_UPDATE is received."""
        log.debug("Received voice server update payload: %s", data)
        self._voice_server = data
        if not self._voice_server_future.done():
            self._voice_server_future.set_result(data)

    async def create_stream(
        self,
        *,
        resolution: str | Resolution = Resolution.R720P,
        fps: int = 30,
        codec: str | Codec = Codec.H264,
        stream_type: str | StreamType = StreamType.GO_LIVE,
    ) -> MediaUdp:
        """
        Run the voice gateway handshake and return a
        :class:`MediaUdp` ready to receive encrypted RTP packets.
        """
        if self._voice_state is None or self._voice_server is None:
            raise RuntimeError("Voice connection is not fully established yet.")

        res = Resolution(resolution) if isinstance(resolution, str) else resolution
        codec = Codec(codec) if isinstance(codec, str) else codec
        stream_type = StreamType(stream_type) if isinstance(stream_type, str) else stream_type

        width, height = res.dimensions()
        endpoint = self._voice_server["endpoint"].rstrip(":80")

        self._gateway = VoiceGateway(
            endpoint=f"wss://{endpoint}?v=7",
            guild_id=int(self._voice_state["guild_id"]),
            user_id=int(self._voice_state["user_id"]),
            session_id=self._voice_state["session_id"],
            token=self._voice_server["token"],
        )

        udp_ip, udp_port, ssrc, secret_key, enc_mode = await self._gateway.connect(
            width=width, height=height, fps=fps,
            codec=codec, stream_type=stream_type,
        )

        self._udp = MediaUdp(
            ip=udp_ip,
            port=udp_port,
            ssrc=ssrc,
            secret_key=secret_key,
            encryption_mode=enc_mode,
            codec=codec,
            fps=fps,
            width=width,
            height=height,
        )
        await self._udp.start()
        return self._udp

    async def stop_stream(self) -> None:
        """Stop the active stream and clean up all resources."""
        if self._udp:
            await self._udp.stop()
            self._udp = None
        if self._gateway:
            await self._gateway.close()
            self._gateway = None
        log.info("Stream stopped.")

    async def disconnect(self, *, force: bool = False) -> None:
        """Disconnect the voice connection and cleanup."""
        log.info("Disconnecting voice stream client...")
        await self.stop_stream()
        try:
            await self.channel.guild.change_voice_state(channel=None)
        except Exception:
            pass
        self.cleanup()
