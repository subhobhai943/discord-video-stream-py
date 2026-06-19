"""Unit tests for the SRTP-style packet encryption."""

import os
import pytest

from discord_video_stream.voice.encryption import encrypt_packet
from discord_video_stream.voice.rtp import build_audio_rtp_header


@pytest.fixture
def secret_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def sample_header() -> bytes:
    return build_audio_rtp_header(sequence=1, timestamp=960, ssrc=42)


@pytest.fixture
def sample_payload() -> bytes:
    return b"fake-opus-frame-data" * 5


def test_xchacha20_rtpsize(secret_key, sample_header, sample_payload):
    packet = encrypt_packet(sample_header, sample_payload, secret_key, "aead_xchacha20_poly1305_rtpsize")
    assert packet[:12] == sample_header
    assert len(packet) > 12 + len(sample_payload)  # includes auth tag


def test_xsalsa20_normal(secret_key, sample_header, sample_payload):
    packet = encrypt_packet(sample_header, sample_payload, secret_key, "xsalsa20_poly1305")
    assert packet[:12] == sample_header


def test_xsalsa20_suffix(secret_key, sample_header, sample_payload):
    packet = encrypt_packet(sample_header, sample_payload, secret_key, "xsalsa20_poly1305_suffix")
    assert packet[:12] == sample_header
    # Last 24 bytes are the random nonce
    assert len(packet) == 12 + len(sample_payload) + 16 + 24  # +16 Poly1305 tag


def test_unsupported_mode_raises(secret_key, sample_header, sample_payload):
    with pytest.raises(ValueError, match="Unsupported encryption mode"):
        encrypt_packet(sample_header, sample_payload, secret_key, "nonexistent_mode")
