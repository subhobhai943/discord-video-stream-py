"""Unit tests for the VP8 RTP payload packetizer (RFC 7741)."""

import pytest

from discord_video_stream.codecs.vp8 import packetize_vp8_frame, MTU


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(size: int) -> bytes:
    """Create a fake VP8 frame of the given size."""
    return bytes(i & 0xFF for i in range(size))


# ---------------------------------------------------------------------------
# Tests: small frames (single packet)
# ---------------------------------------------------------------------------

class TestSmallFrameSinglePacket:
    """A frame that fits within (MTU - 1) bytes produces exactly one packet."""

    def test_tiny_frame(self) -> None:
        frame = _make_frame(100)
        packets = packetize_vp8_frame(frame)
        assert len(packets) == 1

    def test_frame_at_max_payload(self) -> None:
        """A frame exactly filling the maximum payload still fits in one packet."""
        max_payload = MTU - 1  # 1 byte descriptor
        frame = _make_frame(max_payload)
        packets = packetize_vp8_frame(frame)
        assert len(packets) == 1

    def test_single_byte_frame(self) -> None:
        packets = packetize_vp8_frame(b"\x9d")
        assert len(packets) == 1


# ---------------------------------------------------------------------------
# Tests: large frames (fragmented)
# ---------------------------------------------------------------------------

class TestLargeFrameFragmented:
    """A frame exceeding (MTU - 1) bytes is split into multiple packets."""

    def test_two_fragments(self) -> None:
        frame = _make_frame(MTU)  # MTU > (MTU - 1), so needs 2 packets
        packets = packetize_vp8_frame(frame)
        assert len(packets) == 2

    def test_many_fragments(self) -> None:
        frame = _make_frame(MTU * 5)
        packets = packetize_vp8_frame(frame)
        assert len(packets) >= 5

    def test_reassembly(self) -> None:
        """Stripping the 1-byte descriptor and concatenating should recover
        the original frame data."""
        frame = _make_frame(MTU * 3 + 42)
        packets = packetize_vp8_frame(frame)
        reassembled = b"".join(p[1:] for p in packets)
        assert reassembled == frame


# ---------------------------------------------------------------------------
# Tests: S (start) bit
# ---------------------------------------------------------------------------

class TestStartBitOnFirstFragment:
    """The S bit (0x10) must be set on the first fragment only."""

    def test_single_packet_has_s_bit(self) -> None:
        packets = packetize_vp8_frame(_make_frame(100))
        assert packets[0][0] & 0x10

    def test_first_of_many_has_s_bit(self) -> None:
        packets = packetize_vp8_frame(_make_frame(MTU * 3))
        assert packets[0][0] & 0x10

    def test_continuations_no_s_bit(self) -> None:
        packets = packetize_vp8_frame(_make_frame(MTU * 3))
        for pkt in packets[1:]:
            assert not (pkt[0] & 0x10), "S bit must be 0 on continuation fragments"

    def test_descriptor_upper_nibble_zero_on_continuation(self) -> None:
        """X, R, N bits (upper 3 bits) should all be 0 in our minimal descriptor."""
        packets = packetize_vp8_frame(_make_frame(MTU * 2))
        for pkt in packets:
            assert not (pkt[0] & 0xE0), "X, R, N bits should be 0"


# ---------------------------------------------------------------------------
# Tests: empty frame
# ---------------------------------------------------------------------------

class TestEmptyFrame:
    """An empty frame should produce an empty list (no packets)."""

    def test_empty_bytes(self) -> None:
        assert packetize_vp8_frame(b"") == []

    def test_zero_length_bytearray(self) -> None:
        assert packetize_vp8_frame(bytearray()) == []


# ---------------------------------------------------------------------------
# Tests: payload sizes within MTU
# ---------------------------------------------------------------------------

class TestPayloadSizesWithinMtu:
    """Every fragment (descriptor + data) must be ≤ MTU bytes."""

    @pytest.mark.parametrize("size", [1, 100, MTU - 1, MTU, MTU + 1, MTU * 10])
    def test_all_fragments_within_mtu(self, size: int) -> None:
        packets = packetize_vp8_frame(_make_frame(size))
        for i, pkt in enumerate(packets):
            assert len(pkt) <= MTU, (
                f"Fragment {i} is {len(pkt)} bytes, exceeds MTU={MTU}"
            )

    def test_last_fragment_may_be_smaller(self) -> None:
        """Last fragment can be smaller than the others."""
        frame = _make_frame(MTU * 2 + 50)
        packets = packetize_vp8_frame(frame)
        assert len(packets[-1]) < MTU


# ---------------------------------------------------------------------------
# Tests: PID field
# ---------------------------------------------------------------------------

class TestPidField:
    """PID (partition index) should be 0 for all fragments in our
    simplified packetizer."""

    def test_pid_zero(self) -> None:
        packets = packetize_vp8_frame(_make_frame(MTU * 2))
        for pkt in packets:
            pid = pkt[0] & 0x07
            assert pid == 0, f"PID should be 0, got {pid}"
