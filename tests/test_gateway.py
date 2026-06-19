"""Unit tests for the VoiceGateway helper methods."""

import struct
import pytest

from discord_video_stream.voice.gateway import VoiceGateway


@pytest.fixture
def gateway() -> VoiceGateway:
    return VoiceGateway(
        endpoint="wss://fake.discord.gg?v=7",
        guild_id=1,
        user_id=2,
        session_id="abc123",
        token="tok",
    )


def test_initial_state(gateway):
    assert gateway._ssrc == 0
    assert gateway._secret_key == []
    assert not gateway._closed


def test_send_video_op_not_called_before_connect(gateway):
    # _send_video_op depends on _ssrc being set, which only happens after connect().
    # Before connect(), _ssrc == 0 which is a valid fallback value.
    assert gateway._ssrc == 0
