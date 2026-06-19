"""H264 NAL unit packetizer for RTP (RFC 6184).

Supports:
  - Single NAL unit packets (NAL < MTU)
  - FU-A fragmentation for large NALs (NAL >= MTU)
  - SPS/PPS injection before every IDR (keyframe) frame

RFC 6184 FU-A header structure (2 bytes after RTP header)::

    FU indicator byte:
      +---------------+
      |0|1|2|3|4|5|6|7|
      +-+-+-+-+-+-+-+-+
      |F|NRI|  Type   |   Type = 28 (0x1C) for FU-A
      +---------------+

    FU header byte:
      +---------------+
      |0|1|2|3|4|5|6|7|
      +-+-+-+-+-+-+-+-+
      |S|E|R|  Type   |   S=start, E=end, R=reserved(0)
      +---------------+

Reference: RFC 6184 § 5.8
"""

from __future__ import annotations

MTU = 1200  # safe maximum RTP payload size (bytes)

# NAL unit type constants (ITU-T H.264 Table 7-1)
NAL_TYPE_UNSPECIFIED = 0
NAL_TYPE_SLICE      = 1
NAL_TYPE_IDR        = 5   # keyframe / Instantaneous Decoding Refresh
NAL_TYPE_SEI        = 6
NAL_TYPE_SPS        = 7   # Sequence Parameter Set
NAL_TYPE_PPS        = 8   # Picture Parameter Set
NAL_TYPE_AUD        = 9   # Access Unit Delimiter
NAL_TYPE_FU_A       = 28

# Annex-B start codes
START_CODE_4 = b"\x00\x00\x00\x01"
START_CODE_3 = b"\x00\x00\x01"


# ---------------------------------------------------------------------------
# Annex-B splitting
# ---------------------------------------------------------------------------

def split_nalus(bitstream: bytes) -> list[bytes]:
    """
    Split an Annex-B H264 bitstream into individual NAL units.
    Strips all 3- and 4-byte start codes.

    Parameters
    ----------
    bitstream:
        Raw H264 bytes as output by FFmpeg with ``-f h264``.

    Returns
    -------
    list[bytes]
        Non-empty NAL unit byte strings (start code stripped).
    """
    nalus: list[bytes] = []
    i = 0
    start = -1

    while i < len(bitstream):
        if bitstream[i:i + 4] == START_CODE_4:
            if start != -1:
                nalus.append(bitstream[start:i])
            start = i + 4
            i += 4
        elif bitstream[i:i + 3] == START_CODE_3:
            if start != -1:
                nalus.append(bitstream[start:i])
            start = i + 3
            i += 3
        else:
            i += 1

    if start != -1 and start < len(bitstream):
        nalus.append(bitstream[start:])

    return [n for n in nalus if n]


def nal_type(nalu: bytes) -> int:
    """Return the NAL unit type from the first byte."""
    if not nalu:
        return NAL_TYPE_UNSPECIFIED
    return nalu[0] & 0x1F


def is_keyframe(nalus: list[bytes]) -> bool:
    """Return True if any NAL in the list is an IDR (keyframe) slice."""
    return any(nal_type(n) == NAL_TYPE_IDR for n in nalus)


def extract_sps_pps(bitstream: bytes) -> tuple[list[bytes], list[bytes]]:
    """
    Extract all SPS and PPS NAL units from an Annex-B bitstream.

    Returns
    -------
    tuple[list[bytes], list[bytes]]
        ``(sps_list, pps_list)`` where each element is a raw NAL (no start code).
    """
    sps_list: list[bytes] = []
    pps_list: list[bytes] = []
    for nalu in split_nalus(bitstream):
        t = nal_type(nalu)
        if t == NAL_TYPE_SPS:
            sps_list.append(nalu)
        elif t == NAL_TYPE_PPS:
            pps_list.append(nalu)
    return sps_list, pps_list


# ---------------------------------------------------------------------------
# RTP packetization
# ---------------------------------------------------------------------------

def packetize_h264_frame(
    frame_data: bytes,
    cached_sps: list[bytes] | None = None,
    cached_pps: list[bytes] | None = None,
) -> list[bytes]:
    """
    Convert one H264 frame (Annex-B) into a list of RTP payloads.

    - Skips AUD (Access Unit Delimiter) NALs.
    - On IDR (keyframe) frames, prepends SPS+PPS payloads so decoders
      can always recover without prior state.
    - Sends each NAL as a single-unit packet if it fits within MTU.
    - Splits oversized NALs using FU-A fragmentation.

    Parameters
    ----------
    frame_data:
        Raw H264 Annex-B bytes for one frame.
    cached_sps:
        Cached SPS NAL units to inject before IDR frames.  If ``None``,
        the SPS/PPS found inside *frame_data* are used instead.
    cached_pps:
        Cached PPS NAL units (see *cached_sps*).

    Returns
    -------
    list[bytes]
        RTP payload bytes.  The RTP marker bit must be set on the **last**
        entry by the caller (or :class:`~discord_video_stream.voice.udp.MediaUdp`).
    """
    nalus = split_nalus(frame_data)
    if not nalus:
        return []

    payloads: list[bytes] = []
    is_idr = is_keyframe(nalus)

    # Inject SPS + PPS before the IDR so remote decoders can always sync
    if is_idr:
        sps_list = cached_sps or [n for n in nalus if nal_type(n) == NAL_TYPE_SPS]
        pps_list = cached_pps or [n for n in nalus if nal_type(n) == NAL_TYPE_PPS]
        for sps in sps_list:
            payloads.append(sps)
        for pps in pps_list:
            payloads.append(pps)

    for nalu in nalus:
        t = nal_type(nalu)
        # Skip AUD and duplicate SPS/PPS (already injected above)
        if t == NAL_TYPE_AUD:
            continue
        if is_idr and t in (NAL_TYPE_SPS, NAL_TYPE_PPS):
            continue  # already injected

        if len(nalu) <= MTU:
            payloads.append(nalu)
        else:
            payloads.extend(_fragment_fu_a(nalu))

    return payloads


def _fragment_fu_a(nalu: bytes) -> list[bytes]:
    """
    Fragment a single oversized NAL unit into FU-A RTP payloads.

    Each returned bytes object is a complete FU-A payload
    (FU indicator byte + FU header byte + data chunk).
    """
    nal_header = nalu[0]
    nal_nri  = nal_header & 0x60          # NRI bits preserved
    nal_type_val = nal_header & 0x1F

    fu_indicator = nal_nri | NAL_TYPE_FU_A   # 0b0_NRI_11100

    body = nalu[1:]                          # strip the original NAL header byte
    chunk_size = MTU - 2                     # 2 bytes overhead: FU indicator + FU header
    fragments: list[bytes] = []

    i = 0
    total = len(body)
    while i < total:
        chunk = body[i:i + chunk_size]
        start_bit = 0x80 if i == 0 else 0x00
        end_bit   = 0x40 if (i + chunk_size) >= total else 0x00
        fu_header = start_bit | end_bit | (nal_type_val & 0x1F)

        fragments.append(bytes([fu_indicator, fu_header]) + chunk)
        i += chunk_size

    return fragments


# ---------------------------------------------------------------------------
# Async H264 frame reader (for FFmpeg stdout pipe)
# ---------------------------------------------------------------------------

class H264FrameReader:
    """
    Reads a raw Annex-B H264 byte stream from an :class:`asyncio.StreamReader`
    and yields complete frames delimited by the next start code.

    FFmpeg with ``-f h264`` outputs Annex-B frames concatenated.  A new
    access unit starts with either ``\\x00\\x00\\x00\\x01`` or
    ``\\x00\\x00\\x01``.  We buffer until we see the *second* occurrence,
    then yield everything up to it as one complete frame.

    Usage::

        reader = H264FrameReader(proc.stdout)
        async for frame_bytes in reader.frames():
            payloads = packetize_h264_frame(frame_bytes)
            await udp.send_video_packets(payloads)
    """

    CHUNK_SIZE = 65536  # 64 KiB read buffer

    def __init__(self, stream: "asyncio.StreamReader") -> None:
        self._stream = stream
        self._buf = bytearray()
        # Pre-cache cached SPS/PPS to inject before IDR frames
        self._cached_sps: list[bytes] = []
        self._cached_pps: list[bytes] = []

    async def frames(self):
        """
        Async generator that yields complete H264 Annex-B frame byte strings.
        """
        import asyncio
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self._stream.read(self.CHUNK_SIZE), timeout=10.0
                )
            except asyncio.TimeoutError:
                continue

            if not chunk:
                # EOF — flush remaining buffer
                if self._buf:
                    yield bytes(self._buf)
                break

            self._buf.extend(chunk)

            # Yield all complete frames from the buffer
            while True:
                frame, remainder = _split_next_frame(bytes(self._buf))
                if frame is None:
                    break
                self._buf = bytearray(remainder)
                # Update SPS/PPS cache whenever we see them
                sps, pps = extract_sps_pps(frame)
                if sps:
                    self._cached_sps = sps
                if pps:
                    self._cached_pps = pps
                yield frame

    def packetize(self, frame: bytes) -> list[bytes]:
        """Packetize a frame, injecting cached SPS/PPS on IDR frames."""
        return packetize_h264_frame(
            frame,
            cached_sps=self._cached_sps or None,
            cached_pps=self._cached_pps or None,
        )


def _split_next_frame(buf: bytes) -> tuple[bytes | None, bytes]:
    """
    Find the boundary between the first and second access unit in *buf*.

    Returns ``(frame, remaining)`` where *frame* is the first complete
    Annex-B frame, or ``(None, buf)`` if no boundary is found yet.
    """
    # Scan for a start code after offset 4 (skip the first one)
    search_start = 4
    pos4 = buf.find(START_CODE_4, search_start)
    pos3 = buf.find(START_CODE_3, search_start)

    candidates = [p for p in (pos4, pos3) if p != -1]
    if not candidates:
        return None, buf

    boundary = min(candidates)
    return buf[:boundary], buf[boundary:]
