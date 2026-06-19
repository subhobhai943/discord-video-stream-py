"""VoiceGateway — Discord voice WebSocket handler.

Implements the full voice gateway OP flow:
  OP 0  Identify
  OP 1  Select Protocol
  OP 2  Ready
  OP 3  Heartbeat
  OP 4  Session Description
  OP 5  Speaking
  OP 6  Heartbeat ACK
  OP 7  Resume
  OP 8  Hello
  OP 9  Resumed
  OP 18 Video (Go Live signalling)

Reference: https://discord.com/developers/docs/topics/voice-connections
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import socket
import time
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from ..enums import Codec, StreamType

log = logging.getLogger(__name__)

# Voice gateway OP codes
OP_IDENTIFY = 0
OP_SELECT_PROTOCOL = 1
OP_READY = 2
OP_HEARTBEAT = 3
OP_SESSION_DESCRIPTION = 4
OP_SPEAKING = 5
OP_HEARTBEAT_ACK = 6
OP_RESUME = 7
OP_HELLO = 8
OP_RESUMED = 9
OP_VIDEO = 18

SUPPORTED_ENCRYPTION_MODES = [
    "aead_aes256_gcm_rtpsize",
    "aead_xchacha20_poly1305_rtpsize",
    "xsalsa20_poly1305_lite_rtpsize",
    "xsalsa20_poly1305_lite",
    "xsalsa20_poly1305_suffix",
    "xsalsa20_poly1305",
]

# Maximum reconnect attempts before giving up
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF_BASE = 1.5  # seconds — exponential backoff


class VoiceGateway:
    """
    Manages the WebSocket connection to Discord's voice server.

    Usage::

        gw = VoiceGateway(endpoint, guild_id, user_id, session_id, token)
        ip, port, ssrc, secret_key, enc_mode = await gw.connect(
            width=1280, height=720, fps=30,
            codec=Codec.H264, stream_type=StreamType.GO_LIVE
        )
    """

    def __init__(
        self,
        endpoint: str,
        guild_id: int,
        user_id: int,
        session_id: str,
        token: str,
    ) -> None:
        self._endpoint = endpoint
        self._guild_id = guild_id
        self._user_id = user_id
        self._session_id = session_id
        self._token = token

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._heartbeat_interval: float = 0.0
        self._heartbeat_task: asyncio.Task | None = None
        self._recv_task: asyncio.Task | None = None
        self._ssrc: int = 0
        self._secret_key: list[int] = []
        self._encryption_mode: str = ""
        self._closed = False
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------
    # Public connect / close
    # ------------------------------------------------------------------

    async def connect(
        self,
        *,
        width: int,
        height: int,
        fps: int,
        codec: Codec,
        stream_type: StreamType,
    ) -> tuple[str, int, int, list[int], str]:
        """
        Run the full voice gateway handshake and return
        ``(udp_ip, udp_port, ssrc, secret_key, encryption_mode)``.
        """
        log.info("Connecting to voice gateway: %s", self._endpoint)
        self._ws = await websockets.connect(
            self._endpoint,
            max_size=None,
            ping_interval=None,  # we manage heartbeating manually
        )

        # Step 1: receive OP 8 Hello
        hello = await self._recv_op(OP_HELLO)
        self._heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0
        log.debug("Heartbeat interval: %.3f s", self._heartbeat_interval)

        # Step 2: send OP 0 Identify
        await self._send(OP_IDENTIFY, {
            "server_id": str(self._guild_id),
            "user_id": str(self._user_id),
            "session_id": self._session_id,
            "token": self._token,
        })

        # Step 3: receive OP 2 Ready
        ready = await self._recv_op(OP_READY)
        self._ssrc = ready["d"]["ssrc"]
        udp_ip_raw = ready["d"]["ip"]
        udp_port = ready["d"]["port"]
        modes: list[str] = ready["d"]["modes"]
        log.debug("SSRC=%d, UDP=%s:%d, modes=%s", self._ssrc, udp_ip_raw, udp_port, modes)

        # Step 4: UDP IP discovery (hole punch)
        discovered_ip, discovered_port = await self._udp_hole_punch(udp_ip_raw, udp_port)
        log.debug("Discovered external IP: %s:%d", discovered_ip, discovered_port)

        # Select best encryption mode
        self._encryption_mode = next(
            (m for m in SUPPORTED_ENCRYPTION_MODES if m in modes),
            modes[0]
        )
        log.debug("Selected encryption mode: %s", self._encryption_mode)

        # Step 5: send OP 1 Select Protocol
        await self._send(OP_SELECT_PROTOCOL, {
            "protocol": "udp",
            "data": {
                "address": discovered_ip,
                "port": discovered_port,
                "mode": self._encryption_mode,
            },
        })

        # Step 6: receive OP 4 Session Description
        session_desc = await self._recv_op(OP_SESSION_DESCRIPTION)
        self._secret_key = session_desc["d"]["secret_key"]
        self._encryption_mode = session_desc["d"]["mode"]
        log.debug("Secret key received (%d bytes)", len(self._secret_key))

        # Step 7: send OP 18 Video (Go Live signalling)
        if stream_type == StreamType.GO_LIVE:
            await self._send_video_op(width, height, fps, codec)

        # Send OP 5 Speaking to signal audio capability
        await self.set_speaking(True)

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="voice-heartbeat"
        )

        # Start OP receiver loop (handles disconnects / resumes)
        self._recv_task = asyncio.create_task(
            self._receive_loop(), name="voice-recv-loop"
        )

        self._reconnect_attempts = 0  # successful connect resets counter
        return udp_ip_raw, udp_port, self._ssrc, self._secret_key, self._encryption_mode

    async def set_speaking(self, speaking: bool = True, *, video: bool = False) -> None:
        """
        Send OP 5 Speaking to signal audio/video activity.

        Parameters
        ----------
        speaking:
            Whether the bot is currently speaking (sending audio).
        video:
            Whether the bot is also sending video.
        """
        # Speaking flags: bit 0 = microphone, bit 1 = soundshare, bit 2 = priority
        flags = 1 if speaking else 0
        if video:
            flags |= 2  # soundshare flag (used for Go Live audio)
        await self._send(OP_SPEAKING, {
            "speaking": flags,
            "delay": 0,
            "ssrc": self._ssrc,
        })
        log.debug("Sent OP 5 Speaking: flags=%d", flags)

    async def close(self) -> None:
        """Gracefully close the WebSocket and cancel background tasks."""
        self._closed = True
        for task in (self._heartbeat_task, self._recv_task):
            if task and not task.done():
                task.cancel()
        if self._ws:
            await self._ws.close()
        log.info("Voice gateway closed.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _recv(self) -> dict:
        """Receive and decode one JSON message from the gateway."""
        raw = await self._ws.recv()
        return json.loads(raw)

    async def _recv_op(self, expected_op: int, *, timeout: float = 30.0) -> dict:
        """
        Read gateway messages until one with the expected OP code arrives.

        Messages with other OP codes are logged and discarded.  This handles
        the case where Discord sends an unexpected OP (e.g. OP 5 Speaking
        from another user) in the middle of the handshake.
        """
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for OP {expected_op}"
                )
            try:
                msg = await asyncio.wait_for(self._recv(), timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Timed out waiting for OP {expected_op}"
                )
            if msg.get("op") == expected_op:
                return msg
            log.debug(
                "Skipping OP %s while waiting for OP %d",
                msg.get("op"), expected_op,
            )

    async def _send(self, op: int, data: Any) -> None:
        """Encode and send a JSON message to the gateway."""
        await self._ws.send(json.dumps({"op": op, "d": data}))

    async def _send_video_op(self, width: int, height: int, fps: int, codec: Codec) -> None:
        """Send OP 18 to signal video capability and stream parameters."""
        codec_type = 1 if codec == Codec.H264 else 2  # 1=H264, 2=VP8
        payload = {
            "audio_ssrc": self._ssrc,
            "video_ssrc": self._ssrc + 1,
            "rtx_ssrc": self._ssrc + 2,
            "streams": [
                {
                    "type": "video",
                    "rid": "100",
                    "ssrc": self._ssrc + 1,
                    "active": True,
                    "quality": 100,
                    "rtx_ssrc": self._ssrc + 2,
                    "max_bitrate": 2500000,
                    "max_framerate": fps,
                    "max_resolution": {
                        "type": "fixed",
                        "width": width,
                        "height": height,
                    },
                }
            ],
            "streams_metadata": {
                "codec": codec.value,
                "codec_payload_type": 101 if codec == Codec.H264 else 100,
                "rtx_payload_type": 102,
            },
        }
        await self._send(OP_VIDEO, payload)
        log.debug("Sent OP 18 video signalling: %dx%d @ %dfps %s", width, height, fps, codec.value)

    async def _udp_hole_punch(self, ip: str, port: int) -> tuple[str, int]:
        """
        Perform UDP IP discovery: send an 74-byte packet with our SSRC at bytes 4-8,
        then read the server's response which contains our external IP and port.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()

        # Build IP discovery packet (type=1, length=70, ssrc=uint32)
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, self._ssrc)  # type, length, ssrc

        await loop.sock_sendto(sock, bytes(packet), (ip, port))
        response, _ = await loop.sock_recvfrom(sock, 74)
        sock.close()

        # Response: bytes 8..72 = null-terminated IP string, bytes 72..74 = port
        discovered_ip = response[8:72].split(b"\x00", 1)[0].decode()
        discovered_port = struct.unpack_from(">H", response, 72)[0]
        return discovered_ip, discovered_port

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Send OP 3 Heartbeat every heartbeat_interval seconds."""
        try:
            while not self._closed:
                nonce = int(time.time() * 1000)
                await self._send(OP_HEARTBEAT, nonce)
                log.debug("Sent heartbeat nonce=%d", nonce)
                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            pass
        except ConnectionClosed:
            log.warning("Connection closed during heartbeat.")

    async def _receive_loop(self) -> None:
        """Process incoming gateway messages (ACKs, resumes, etc.)."""
        try:
            while not self._closed:
                msg = await self._recv()
                op = msg.get("op")
                if op == OP_HEARTBEAT_ACK:
                    log.debug("Heartbeat ACK received")
                    self._reconnect_attempts = 0  # connection is healthy
                elif op == OP_RESUMED:
                    log.info("Voice gateway session resumed")
                    self._reconnect_attempts = 0
                elif op == OP_HELLO:
                    # Server re-sent Hello after reconnect
                    self._heartbeat_interval = msg["d"]["heartbeat_interval"] / 1000.0
                    log.debug("Updated heartbeat interval: %.3f s", self._heartbeat_interval)
                elif op == OP_SPEAKING:
                    # Another user's speaking state — ignore
                    log.debug("User speaking update: %s", msg.get("d"))
                else:
                    log.debug("Unhandled OP %s: %s", op, msg.get("d"))
        except asyncio.CancelledError:
            pass
        except ConnectionClosed:
            if not self._closed:
                log.warning("Voice gateway disconnected unexpectedly — attempting resume")
                await self._resume()

    async def _resume(self) -> None:
        """
        Attempt to resume a dropped voice gateway connection.

        Uses exponential backoff.  If the resume succeeds, restarts the
        heartbeat and receive loops so the connection stays alive.
        """
        if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            log.error(
                "Exhausted %d reconnect attempts — giving up.",
                MAX_RECONNECT_ATTEMPTS,
            )
            return

        self._reconnect_attempts += 1
        backoff = RECONNECT_BACKOFF_BASE ** self._reconnect_attempts
        log.info(
            "Reconnect attempt %d/%d — waiting %.1f s",
            self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS, backoff,
        )
        await asyncio.sleep(backoff)

        try:
            self._ws = await websockets.connect(
                self._endpoint,
                max_size=None,
                ping_interval=None,
            )

            # Wait for OP 8 Hello on the new connection
            hello = await self._recv_op(OP_HELLO, timeout=10.0)
            self._heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0

            # Send OP 7 Resume
            await self._send(OP_RESUME, {
                "server_id": str(self._guild_id),
                "session_id": self._session_id,
                "token": self._token,
            })
            log.info("Sent OP 7 Resume")

            # Restart heartbeat loop
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name="voice-heartbeat-resumed"
            )

            # Restart receive loop (this method was called from the old one)
            self._recv_task = asyncio.create_task(
                self._receive_loop(), name="voice-recv-loop-resumed"
            )

        except Exception as exc:
            log.error("Failed to resume voice gateway: %s", exc)
            # Try again recursively
            await self._resume()
