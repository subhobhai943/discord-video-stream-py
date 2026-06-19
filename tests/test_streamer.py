"""Unit tests for VoiceStreamClient and its Streamer integration."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord_video_stream.voice.client import VoiceStreamClient
from discord_video_stream.streamer import Streamer
from discord_video_stream.enums import Codec, StreamType, Resolution


class MockGuild:
    def __init__(self, guild_id: int):
        self.id = guild_id
        self.change_voice_state = AsyncMock()


class MockVoiceChannel:
    def __init__(self, channel_id: int, guild: MockGuild):
        self.id = channel_id
        self.guild = guild
        self.connect = AsyncMock()

    def _get_voice_client_key(self):
        return (self.guild.id, self.id)


class MockClient:
    def __init__(self):
        self.user = MagicMock()
        self.user.id = 12345
        self.ws = AsyncMock()
        self.wait_for = AsyncMock()
        self._connection = MagicMock()
        self.get_guild = MagicMock()
        self.get_channel = MagicMock()


@pytest.fixture
def mock_client():
    return MockClient()


@pytest.fixture
def mock_guild():
    return MockGuild(guild_id=111)


@pytest.fixture
def mock_channel(mock_guild):
    return MockVoiceChannel(channel_id=222, guild=mock_guild)


class TestVoiceStreamClient:
    """Tests the functionality of VoiceStreamClient."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_client, mock_channel):
        client = VoiceStreamClient(mock_client, mock_channel)
        
        # Start connection in a task so we can trigger updates
        connect_task = asyncio.create_task(
            client.connect(timeout=1.0)
        )
        
        # Yield execution to allow connect() to start
        await asyncio.sleep(0.01)
        
        # Verify it called change_voice_state
        mock_channel.guild.change_voice_state.assert_called_once_with(
            channel=mock_channel,
            self_mute=False,
            self_deaf=False,
        )
        
        # Provide voice state and voice server updates
        state_payload = {"guild_id": "111", "user_id": "12345", "session_id": "sess123"}
        server_payload = {"guild_id": "111", "endpoint": "xyz.discord.gg", "token": "tok123"}
        
        await client.on_voice_state_update(state_payload)
        await client.on_voice_server_update(server_payload)
        
        await connect_task
        
        assert client._voice_state == state_payload
        assert client._voice_server == server_payload

    @pytest.mark.asyncio
    async def test_connect_timeout(self, mock_client, mock_channel):
        client = VoiceStreamClient(mock_client, mock_channel)
        
        with pytest.raises(asyncio.TimeoutError):
            await client.connect(timeout=0.05)

    @pytest.mark.asyncio
    async def test_disconnect_and_cleanup(self, mock_client, mock_channel):
        client = VoiceStreamClient(mock_client, mock_channel)
        
        with patch.object(client, "cleanup") as mock_cleanup, \
             patch.object(client, "stop_stream", new_callable=AsyncMock) as mock_stop_stream:
            await client.disconnect()
            
            mock_stop_stream.assert_called_once()
            mock_channel.guild.change_voice_state.assert_called_once_with(channel=None)
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_stream(self, mock_client, mock_channel):
        client = VoiceStreamClient(mock_client, mock_channel)
        client._voice_state = {"guild_id": "111", "user_id": "12345", "session_id": "sess123"}
        client._voice_server = {"guild_id": "111", "endpoint": "xyz.discord.gg", "token": "tok123"}
        
        mock_gateway_connect = AsyncMock(return_value=("1.1.1.1", 1234, 555, [1, 2], "xsalsa20_poly1305"))
        
        with patch("discord_video_stream.voice.client.VoiceGateway") as MockGateway, \
             patch("discord_video_stream.voice.client.MediaUdp") as MockUdp:
            
            mock_gw_instance = MockGateway.return_value
            mock_gw_instance.connect = mock_gateway_connect
            
            mock_udp_instance = MockUdp.return_value
            mock_udp_instance.start = AsyncMock()
            
            udp = await client.create_stream(resolution="720p", fps=30)
            
            MockGateway.assert_called_once_with(
                endpoint="wss://xyz.discord.gg?v=7",
                guild_id=111,
                user_id=12345,
                session_id="sess123",
                token="tok123",
            )
            mock_gw_instance.connect.assert_called_once()
            MockUdp.assert_called_once()
            mock_udp_instance.start.assert_called_once()
            
            assert udp == mock_udp_instance
            assert client._udp == mock_udp_instance
            assert client._gateway == mock_gw_instance


class TestStreamerIntegration:
    """Tests the Streamer wrapper and how it interacts with VoiceStreamClient."""

    @pytest.mark.asyncio
    async def test_join_voice_via_client_connect(self, mock_client, mock_channel, mock_guild):
        # Set up cache so guild and channel are found
        mock_client.get_guild.return_value = mock_guild
        mock_client.get_channel.return_value = mock_channel
        
        mock_voice_client = MagicMock()
        mock_voice_client._voice_state = {"guild_id": "111"}
        mock_voice_client._voice_server = {"token": "abc"}
        mock_channel.connect.return_value = mock_voice_client
        
        streamer = Streamer(mock_client)
        await streamer.join_voice(guild_id=111, channel_id=222)
        
        mock_client.get_guild.assert_called_once_with(111)
        mock_client.get_channel.assert_called_once_with(222)
        mock_channel.connect.assert_called_once_with(
            cls=VoiceStreamClient,
            self_mute=False,
            self_deaf=False,
        )
        assert streamer._voice_client == mock_voice_client
        assert streamer._voice_state == {"guild_id": "111"}
        assert streamer._voice_server == {"token": "abc"}

    @pytest.mark.asyncio
    async def test_join_voice_fallback(self, mock_client):
        # Guild or channel is not cached
        mock_client.get_guild.return_value = None
        mock_client.get_channel.return_value = None
        
        mock_client.wait_for.side_effect = [
            {"guild_id": "111", "user_id": "12345", "session_id": "sess"},
            {"guild_id": "111", "token": "xyz"},
        ]
        
        streamer = Streamer(mock_client)
        await streamer.join_voice(guild_id=111, channel_id=222)
        
        mock_client.ws.voice_state.assert_called_once_with(
            111, 222,
            self_mute=False,
            self_deaf=False,
        )
        assert streamer._voice_client is None
        assert streamer._voice_state["session_id"] == "sess"
        assert streamer._voice_server["token"] == "xyz"
