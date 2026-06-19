"""Streamer — the main entry point for library users."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .enums import Codec, Resolution, StreamType
from .voice.gateway import VoiceGateway
from .voice.udp import MediaUdp

if TYPE_CHECKING:
    import discord  # discord.py-self

log = logging.getLogger(__name__)


class Streamer:
    """
    Wraps a ``discord.py-self`` Client and manages the full streaming lifecycle:
    joining a voice channel, negotiating the voice gateway, and exposing
    a :class:`MediaUdp` to feed encoded media packets.

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
        self._client = client
        self._gateway: VoiceGateway | None = None
        self._udp: MediaUdp | None = None

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

        The client must already be connected to the Discord gateway before
        calling this method.
        """
        log.info("Joining voice channel %d in guild %d", channel_id, guild_id)
        # discord.py-self exposes this via the underlying connection
        await self._client.ws.voice_state(
            guild_id,
            channel_id,
            self_mute=self_mute,
            self_deaf=self_deaf,
        )
        # Wait for VOICE_STATE_UPDATE + VOICE_SERVER_UPDATE events
        self._voice_state, self._voice_server = await asyncio.gather(
            self._wait_for_voice_state(guild_id),
            self._wait_for_voice_server(guild_id),
        )
        log.debug("Voice state received: %s", self._voice_state)
        log.debug("Voice server received: %s", self._voice_server)

    async def _wait_for_voice_state(self, guild_id: int) -> dict:
        """Wait for VOICE_STATE_UPDATE for our own user in the given guild."""
        def check(data: dict) -> bool:
            return (
                data.get("guild_id") == str(guild_id)
                and data.get("user_id") == str(self._client.user.id)
            )
        return await self._client.wait_for("voice_state_update_raw", check=check)

    async def _wait_for_voice_server(self, guild_id: int) -> dict:
        """Wait for VOICE_SERVER_UPDATE for the given guild."""
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
        Negotiate the voice gateway (OP 0→2→1→4→18) and return a
        :class:`MediaUdp` ready to receive encrypted RTP packets.

        Parameters
        ----------
        resolution:
            Target resolution. Accepts a :class:`Resolution` enum or a string
            like ``"720p"``.
        fps:
            Target frames per second (15, 30, 60).
        codec:
            Video codec — ``"h264"`` or ``"vp8"``.
        stream_type:
            ``"go_live"`` (default) or ``"webcam"``.
        """
        if not hasattr(self, "_voice_state"):
            raise RuntimeError(
                "Call join_voice() before create_stream()."
            )

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

        udp_ip, udp_port, ssrc, secret_key, encryption_mode = await self._gateway.connect(
            width=width,
            height=height,
            fps=fps,
            codec=codec,
            stream_type=stream_type,
        )

        self._udp = MediaUdp(
            ip=udp_ip,
            port=udp_port,
            ssrc=ssrc,
            secret_key=secret_key,
            encryption_mode=encryption_mode,
        )
        await self._udp.start()
        return self._udp

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def stop_stream(self) -> None:
        """Stop the current stream and clean up all resources."""
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
        await self._client.ws.voice_state(guild_id, None)
        log.info("Left voice channel in guild %d", guild_id)
