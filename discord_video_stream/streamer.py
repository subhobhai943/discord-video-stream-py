"""Streamer — the main entry point for library users."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .enums import Codec, Resolution, StreamType
from .voice.gateway import VoiceGateway
from .voice.udp import MediaUdp

if TYPE_CHECKING:
    import discord

log = logging.getLogger(__name__)


class Streamer:
    """
    Wraps a ``discord.py-self`` Client and manages the full streaming lifecycle.

    Example::

        client = discord.Client()
        streamer = Streamer(client)

        @client.event
        async def on_ready():
            await streamer.join_voice(guild_id=123, channel_id=456)
            udp = await streamer.create_stream(resolution="720p", fps=30)
            player = VideoPlayer("video.mp4", udp)
            await player.play()
    """

    def __init__(self, client: "discord.Client") -> None:
        self._client  = client
        self._gateway: VoiceGateway | None = None
        self._udp:     MediaUdp     | None = None
        self._voice_client: VoiceStreamClient | None = None

    # ------------------------------------------------------------------
    # Voice channel lifecycle
    # ------------------------------------------------------------------

    async def join_voice(
        self,
        guild_id: int,
        channel_id: int,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> None:
        """
        Send a Voice State Update to join *channel_id* in *guild_id*.
        The client must already be connected to the Discord gateway.
        """
        log.info("Joining voice channel %d in guild %d", channel_id, guild_id)

        if self._voice_client:
            try:
                await self._voice_client.disconnect(force=True)
            except Exception:
                pass
            self._voice_client = None

        guild = self._client.get_guild(guild_id)
        channel = self._client.get_channel(channel_id) if guild else None

        if guild is not None and channel is not None:
            from .voice.client import VoiceStreamClient
            self._voice_client = await channel.connect(
                cls=VoiceStreamClient,
                self_mute=self_mute,
                self_deaf=self_deaf,
            )
            # Sync for backward compatibility
            self._voice_state = self._voice_client._voice_state
            self._voice_server = self._voice_client._voice_server
        else:
            log.warning("Guild or channel not found in cache. Falling back to raw voice state join.")
            await self._client.ws.voice_state(
                guild_id, channel_id,
                self_mute=self_mute, self_deaf=self_deaf,
            )
            self._voice_state, self._voice_server = await asyncio.gather(
                self._wait_for_voice_state(guild_id),
                self._wait_for_voice_server(guild_id),
            )
        log.debug("Voice state : %s", self._voice_state)
        log.debug("Voice server: %s", self._voice_server)

    async def _wait_for_voice_state(self, guild_id: int) -> dict:
        def check(data: dict) -> bool:
            return (
                data.get("guild_id") == str(guild_id)
                and data.get("user_id") == str(self._client.user.id)
            )
        return await self._client.wait_for("voice_state_update_raw", check=check)

    async def _wait_for_voice_server(self, guild_id: int) -> dict:
        def check(data: dict) -> bool:
            return data.get("guild_id") == str(guild_id)
        return await self._client.wait_for("voice_server_update", check=check)

    # ------------------------------------------------------------------
    # Stream creation
    # ------------------------------------------------------------------

    async def create_stream(
        self,
        *,
        resolution: str | Resolution = Resolution.R720P,
        fps: int = 30,
        codec: str | Codec = Codec.H264,
        stream_type: str | StreamType = StreamType.GO_LIVE,
    ) -> MediaUdp:
        """
        Run the voice gateway handshake (OP 0→8→0→2→1→4→18) and return a
        :class:`MediaUdp` ready to receive encrypted RTP packets.

        Parameters
        ----------
        resolution:
            Target resolution: ``"480p"``, ``"720p"``, ``"1080p"``, ``"source"``.
        fps:
            Frames per second (15, 30, 60).
        codec:
            ``"h264"`` (default) or ``"vp8"``.
        stream_type:
            ``"go_live"`` (default) or ``"webcam"``.
        """
        if self._voice_client is not None:
            self._udp = await self._voice_client.create_stream(
                resolution=resolution,
                fps=fps,
                codec=codec,
                stream_type=stream_type,
            )
            self._gateway = self._voice_client._gateway
            return self._udp

        if not hasattr(self, "_voice_state"):
            raise RuntimeError("Call join_voice() before create_stream().")

        res         = Resolution(resolution) if isinstance(resolution, str) else resolution
        codec       = Codec(codec)           if isinstance(codec, str)       else codec
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

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def stop_stream(self) -> None:
        """Stop the active stream and clean up all resources."""
        if self._voice_client:
            await self._voice_client.stop_stream()
        if self._udp:
            await self._udp.stop()
            self._udp = None
        if self._gateway:
            await self._gateway.close()
            self._gateway = None
        log.info("Stream stopped.")

    async def leave_voice(self, guild_id: int) -> None:
        """Leave the voice channel and clean up."""
        await self.stop_stream()
        if self._voice_client:
            await self._voice_client.disconnect(force=True)
            self._voice_client = None
        else:
            await self._client.ws.voice_state(guild_id, None)
        log.info("Left voice channel in guild %d", guild_id)

