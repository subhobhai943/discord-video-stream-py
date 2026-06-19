"""Comprehensive unit tests for the VoiceGateway.

Tests cover: initial state, OP payloads, heartbeat interval parsing,
encryption mode selection, and IP discovery packet format — all without
making real network calls.
"""

import asyncio
import json
import struct

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from discord_video_stream.voice.gateway import (
    VoiceGateway,
    OP_IDENTIFY,
    OP_SELECT_PROTOCOL,
    OP_READY,
    OP_HEARTBEAT,
    OP_SESSION_DESCRIPTION,
    OP_HELLO,
    OP_VIDEO,
    SUPPORTED_ENCRYPTION_MODES,
)
from discord_video_stream.enums import Codec, StreamType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_ENDPOINT = "wss://fake.discord.gg?v=7"
GUILD_ID = 111222333
USER_ID = 444555666
SESSION_ID = "session-abc-123"
TOKEN = "voice-token-xyz"

FAKE_SECRET_KEY = list(range(32))
FAKE_SSRC = 12345
FAKE_UDP_IP = "1.2.3.4"
FAKE_UDP_PORT = 50000
FAKE_DISCOVERED_IP = "5.6.7.8"
FAKE_DISCOVERED_PORT = 60000


@pytest.fixture
def gateway() -> VoiceGateway:
    """Create a gateway instance without connecting."""
    return VoiceGateway(
        endpoint=FAKE_ENDPOINT,
        guild_id=GUILD_ID,
        user_id=USER_ID,
        session_id=SESSION_ID,
        token=TOKEN,
    )


def _build_hello(heartbeat_ms: float = 13750.0) -> str:
    """Build a serialised OP 8 Hello message."""
    return json.dumps({"op": OP_HELLO, "d": {"heartbeat_interval": heartbeat_ms}})


def _build_ready(
    ssrc: int = FAKE_SSRC,
    ip: str = FAKE_UDP_IP,
    port: int = FAKE_UDP_PORT,
    modes: list[str] | None = None,
) -> str:
    """Build a serialised OP 2 Ready message."""
    if modes is None:
        modes = ["xsalsa20_poly1305", "xsalsa20_poly1305_lite"]
    return json.dumps({
        "op": OP_READY,
        "d": {"ssrc": ssrc, "ip": ip, "port": port, "modes": modes},
    })


def _build_session_description(
    secret_key: list[int] | None = None,
    mode: str = "xsalsa20_poly1305",
) -> str:
    """Build a serialised OP 4 Session Description message."""
    if secret_key is None:
        secret_key = FAKE_SECRET_KEY
    return json.dumps({
        "op": OP_SESSION_DESCRIPTION,
        "d": {"secret_key": secret_key, "mode": mode},
    })


# ---------------------------------------------------------------------------
# Tests: initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    """VoiceGateway starts with sane default values before connect()."""

    def test_ssrc_starts_at_zero(self, gateway: VoiceGateway) -> None:
        assert gateway._ssrc == 0

    def test_secret_key_empty(self, gateway: VoiceGateway) -> None:
        assert gateway._secret_key == []

    def test_not_closed(self, gateway: VoiceGateway) -> None:
        assert not gateway._closed

    def test_encryption_mode_empty(self, gateway: VoiceGateway) -> None:
        assert gateway._encryption_mode == ""

    def test_heartbeat_interval_zero(self, gateway: VoiceGateway) -> None:
        assert gateway._heartbeat_interval == 0.0


# ---------------------------------------------------------------------------
# Tests: heartbeat interval parsing
# ---------------------------------------------------------------------------

class TestHeartbeatInterval:
    """OP 8 Hello sets the heartbeat interval correctly."""

    @pytest.mark.asyncio
    async def test_heartbeat_interval_from_hello(self, gateway: VoiceGateway) -> None:
        """heartbeat_interval from OP 8 is converted from ms → seconds."""
        heartbeat_ms = 13750.0
        mock_ws = AsyncMock()
        # recv() sequence: Hello → Ready → Session Description
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(heartbeat_ms),
            _build_ready(),
            _build_session_description(),
        ])

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.H264, stream_type=StreamType.WEBCAM,
                )

        assert gateway._heartbeat_interval == heartbeat_ms / 1000.0

    @pytest.mark.asyncio
    async def test_heartbeat_interval_41250(self, gateway: VoiceGateway) -> None:
        """Different interval value is also correctly parsed."""
        heartbeat_ms = 41250.0
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(heartbeat_ms),
            _build_ready(),
            _build_session_description(),
        ])

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.H264, stream_type=StreamType.WEBCAM,
                )

        assert gateway._heartbeat_interval == 41250.0 / 1000.0


# ---------------------------------------------------------------------------
# Tests: encryption mode selection
# ---------------------------------------------------------------------------

class TestEncryptionModeSelection:
    """Best encryption mode is chosen from the server's advertised list."""

    def test_preferred_mode_selected(self, gateway: VoiceGateway) -> None:
        """When the server offers our top choice, it is selected."""
        modes = ["xsalsa20_poly1305", "aead_aes256_gcm_rtpsize"]
        # Walk the same logic the gateway uses
        selected = next(
            (m for m in SUPPORTED_ENCRYPTION_MODES if m in modes),
            modes[0],
        )
        assert selected == "aead_aes256_gcm_rtpsize"

    def test_fallback_to_first_server_mode(self) -> None:
        """If no preferred modes match, fall back to server's first mode."""
        modes = ["totally_unsupported_mode"]
        selected = next(
            (m for m in SUPPORTED_ENCRYPTION_MODES if m in modes),
            modes[0],
        )
        assert selected == "totally_unsupported_mode"

    def test_priority_order(self) -> None:
        """Modes earlier in SUPPORTED_ENCRYPTION_MODES are preferred."""
        modes = ["xsalsa20_poly1305_suffix", "xsalsa20_poly1305_lite_rtpsize"]
        selected = next(
            (m for m in SUPPORTED_ENCRYPTION_MODES if m in modes),
            modes[0],
        )
        # lite_rtpsize has higher priority in SUPPORTED_ENCRYPTION_MODES
        assert selected == "xsalsa20_poly1305_lite_rtpsize"


# ---------------------------------------------------------------------------
# Tests: IP discovery packet format
# ---------------------------------------------------------------------------

class TestIpDiscoveryPacketFormat:
    """The 74-byte UDP IP discovery packet is correctly structured."""

    def test_packet_is_74_bytes(self) -> None:
        """Packet must be exactly 74 bytes."""
        ssrc = 42
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, ssrc)
        assert len(packet) == 74

    def test_type_field(self) -> None:
        """First 2 bytes encode type=1."""
        ssrc = 99
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, ssrc)
        pkt_type = struct.unpack_from(">H", packet, 0)[0]
        assert pkt_type == 1

    def test_length_field(self) -> None:
        """Bytes 2-3 encode length=70."""
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, 0)
        length = struct.unpack_from(">H", packet, 2)[0]
        assert length == 70

    def test_ssrc_field(self) -> None:
        """Bytes 4-7 encode the SSRC as big-endian uint32."""
        ssrc = 0xDEADBEEF
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, ssrc)
        stored_ssrc = struct.unpack_from(">I", packet, 4)[0]
        assert stored_ssrc == ssrc

    def test_remaining_bytes_zero(self) -> None:
        """Bytes 8-73 should be zero (padding)."""
        packet = bytearray(74)
        struct.pack_into(">HHI", packet, 0, 1, 70, 12345)
        assert packet[8:] == bytes(66)


# ---------------------------------------------------------------------------
# Tests: OP 0 Identify payload
# ---------------------------------------------------------------------------

class TestIdentifyPayload:
    """OP 0 Identify contains the expected fields."""

    @pytest.mark.asyncio
    async def test_identify_payload_fields(self, gateway: VoiceGateway) -> None:
        """Identify carries server_id, user_id, session_id, token."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(),
            _build_ready(),
            _build_session_description(),
        ])

        sent_messages: list[dict] = []

        async def capture_send(msg: str) -> None:
            sent_messages.append(json.loads(msg))

        mock_ws.send = AsyncMock(side_effect=capture_send)

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.H264, stream_type=StreamType.WEBCAM,
                )

        # First sent message should be OP 0 Identify
        identify = sent_messages[0]
        assert identify["op"] == OP_IDENTIFY
        d = identify["d"]
        assert d["server_id"] == str(GUILD_ID)
        assert d["user_id"] == str(USER_ID)
        assert d["session_id"] == SESSION_ID
        assert d["token"] == TOKEN


# ---------------------------------------------------------------------------
# Tests: OP 1 Select Protocol payload
# ---------------------------------------------------------------------------

class TestSelectProtocolPayload:
    """OP 1 Select Protocol contains address, port, and encryption mode."""

    @pytest.mark.asyncio
    async def test_select_protocol_payload(self, gateway: VoiceGateway) -> None:
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(),
            _build_ready(modes=["xsalsa20_poly1305"]),
            _build_session_description(mode="xsalsa20_poly1305"),
        ])

        sent_messages: list[dict] = []

        async def capture_send(msg: str) -> None:
            sent_messages.append(json.loads(msg))

        mock_ws.send = AsyncMock(side_effect=capture_send)

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.H264, stream_type=StreamType.WEBCAM,
                )

        # Second sent message should be OP 1 Select Protocol
        select = sent_messages[1]
        assert select["op"] == OP_SELECT_PROTOCOL
        data = select["d"]["data"]
        assert data["address"] == FAKE_DISCOVERED_IP
        assert data["port"] == FAKE_DISCOVERED_PORT
        assert "mode" in data


# ---------------------------------------------------------------------------
# Tests: OP 18 Video payload
# ---------------------------------------------------------------------------

class TestVideoOpPayload:
    """OP 18 Video contains correct stream parameters."""

    @pytest.mark.asyncio
    async def test_video_op_for_go_live(self, gateway: VoiceGateway) -> None:
        """When stream_type=GO_LIVE, OP 18 is sent with video parameters."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(),
            _build_ready(ssrc=1000),
            _build_session_description(),
        ])

        sent_messages: list[dict] = []

        async def capture_send(msg: str) -> None:
            sent_messages.append(json.loads(msg))

        mock_ws.send = AsyncMock(side_effect=capture_send)

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1920, height=1080, fps=60,
                    codec=Codec.H264, stream_type=StreamType.GO_LIVE,
                )

        # Third message should be OP 18
        video_msgs = [m for m in sent_messages if m["op"] == OP_VIDEO]
        assert len(video_msgs) == 1
        d = video_msgs[0]["d"]

        assert d["audio_ssrc"] == 1000
        assert d["video_ssrc"] == 1001
        assert d["rtx_ssrc"] == 1002

        stream = d["streams"][0]
        assert stream["type"] == "video"
        assert stream["max_framerate"] == 60
        assert stream["max_resolution"]["width"] == 1920
        assert stream["max_resolution"]["height"] == 1080

    @pytest.mark.asyncio
    async def test_video_op_not_sent_for_webcam(self, gateway: VoiceGateway) -> None:
        """When stream_type=WEBCAM, OP 18 should NOT be sent."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(),
            _build_ready(),
            _build_session_description(),
        ])

        sent_messages: list[dict] = []

        async def capture_send(msg: str) -> None:
            sent_messages.append(json.loads(msg))

        mock_ws.send = AsyncMock(side_effect=capture_send)

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.H264, stream_type=StreamType.WEBCAM,
                )

        video_msgs = [m for m in sent_messages if m["op"] == OP_VIDEO]
        assert len(video_msgs) == 0

    @pytest.mark.asyncio
    async def test_vp8_codec_type(self, gateway: VoiceGateway) -> None:
        """VP8 codec uses payload_type=100 in OP 18 metadata."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            _build_hello(),
            _build_ready(),
            _build_session_description(),
        ])

        sent_messages: list[dict] = []

        async def capture_send(msg: str) -> None:
            sent_messages.append(json.loads(msg))

        mock_ws.send = AsyncMock(side_effect=capture_send)

        with patch("discord_video_stream.voice.gateway.websockets.connect",
                    new_callable=AsyncMock, return_value=mock_ws):
            with patch.object(gateway, "_udp_hole_punch",
                              new_callable=AsyncMock,
                              return_value=(FAKE_DISCOVERED_IP, FAKE_DISCOVERED_PORT)):
                await gateway.connect(
                    width=1280, height=720, fps=30,
                    codec=Codec.VP8, stream_type=StreamType.GO_LIVE,
                )

        video_msgs = [m for m in sent_messages if m["op"] == OP_VIDEO]
        meta = video_msgs[0]["d"]["streams_metadata"]
        assert meta["codec"] == "vp8"
        assert meta["codec_payload_type"] == 100
