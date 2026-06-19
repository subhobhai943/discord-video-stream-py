"""MediaPlayer and VideoPlayer — the FFmpeg → RTP streaming pipeline.

MediaPlayer manages the FFmpeg subprocess and dispatches encoded frames
to a :class:`~discord_video_stream.voice.udp.MediaUdp`.

VideoPlayer wraps MediaPlayer with a public API including events and
playback controls (pause, resume, seek, stop).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from ..enums import Codec
from ..voice.udp import MediaUdp
from .ffmpeg import spawn_ffmpeg
from .ytdlp import resolve_url
from ..codecs.h264 import packetize_h264_frame
from ..codecs.vp8 import packetize_vp8_frame

log = logging.getLogger(__name__)

# Type alias for async event callbacks
EventCallback = Callable[..., Coroutine[Any, Any, None]]


class MediaPlayer:
    """
    Spawns an FFmpeg subprocess, reads encoded frames, and feeds them to
    a :class:`MediaUdp` as encrypted RTP packets.

    This is the low-level player.  Most users should use :class:`VideoPlayer`.
    """

    def __init__(
        self,
        source: str,
        udp: MediaUdp,
        *,
        codec: Codec = Codec.H264,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        video_bitrate: str = "2M",
        audio_bitrate: str = "128k",
    ) -> None:
        self._source = source
        self._udp = udp
        self._codec = codec
        self._width = width
        self._height = height
        self._fps = fps
        self._video_bitrate = video_bitrate
        self._audio_bitrate = audio_bitrate

        self._process: asyncio.subprocess.Process | None = None
        self._video_task: asyncio.Task | None = None
        self._audio_task: asyncio.Task | None = None
        self._paused = False
        self._stop_event = asyncio.Event()

    async def play(self) -> None:
        """
        Resolve the source URL, spawn FFmpeg, and start streaming.
        Returns when the stream finishes or :meth:`stop` is called.
        """
        source = await resolve_url(self._source)
        ffmpeg = await spawn_ffmpeg(
            source,
            width=self._width,
            height=self._height,
            fps=self._fps,
            codec=self._codec,
            video_bitrate=self._video_bitrate,
            audio_bitrate=self._audio_bitrate,
        )
        self._process = ffmpeg.process

        self._video_task = asyncio.create_task(
            self._video_loop(ffmpeg.video_reader), name="video-loop"
        )
        self._audio_task = asyncio.create_task(
            self._audio_loop(ffmpeg.audio_reader), name="audio-loop"
        )

        try:
            await asyncio.gather(self._video_task, self._audio_task)
        except asyncio.CancelledError:
            pass
        finally:
            await self._cleanup()

    def pause(self) -> None:
        """Pause streaming (buffers FFmpeg output — resumes from current position)."""
        self._paused = True
        log.info("Player paused.")

    def resume(self) -> None:
        """Resume a paused stream."""
        self._paused = False
        log.info("Player resumed.")

    def stop(self) -> None:
        """Stop streaming and kill the FFmpeg process."""
        self._stop_event.set()
        if self._video_task:
            self._video_task.cancel()
        if self._audio_task:
            self._audio_task.cancel()
        log.info("Player stopped.")

    async def seek(self, seconds: float) -> None:
        """
        Seek to *seconds* by restarting FFmpeg with a ``-ss`` offset.
        This restarts the subprocess; there will be a brief gap.
        """
        # TODO: Phase 4 — implement seek by restarting FFmpeg with -ss
        raise NotImplementedError("seek() will be implemented in Phase 4")

    # ------------------------------------------------------------------
    # Internal streaming loops
    # ------------------------------------------------------------------

    async def _video_loop(self, reader: asyncio.StreamReader) -> None:
        """Read H264/VP8 frames from FFmpeg stdout and dispatch to UDP."""
        frame_buffer = bytearray()
        packetize = (
            packetize_h264_frame if self._codec == Codec.H264
            else packetize_vp8_frame
        )
        # For H264, FFmpeg -f h264 outputs one NAL unit or Annex-B frame per read.
        # We read in chunks and look for start codes to delimit frames.
        CHUNK = 65536
        try:
            while not self._stop_event.is_set():
                if self._paused:
                    await asyncio.sleep(0.01)
                    continue
                try:
                    chunk = await asyncio.wait_for(reader.read(CHUNK), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                frame_buffer.extend(chunk)

                # Flush complete frames from the buffer
                while True:
                    frame, frame_buffer = _extract_frame(bytes(frame_buffer), self._codec)
                    if frame is None:
                        break
                    payloads = packetize(frame)
                    if payloads:
                        await self._udp.send_video_packets(payloads)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Video loop error: %s", exc)

    async def _audio_loop(self, reader: asyncio.StreamReader) -> None:
        """Read Opus frames from FFmpeg stderr and dispatch to UDP."""
        import struct
        try:
            while not self._stop_event.is_set():
                if self._paused:
                    await asyncio.sleep(0.01)
                    continue
                try:
                    length_bytes = await asyncio.wait_for(
                        reader.readexactly(2), timeout=5.0
                    )
                except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                    continue
                (length,) = struct.unpack(">H", length_bytes)
                if length == 0 or length > 4000:
                    continue
                try:
                    frame = await reader.readexactly(length)
                except asyncio.IncompleteReadError:
                    break
                await self._udp.send_audio_frame(frame)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Audio loop error: %s", exc)

    async def _cleanup(self) -> None:
        """Kill FFmpeg and clean up."""
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        log.info("FFmpeg process cleaned up.")


def _extract_frame(buf: bytes, codec: Codec) -> tuple[bytes | None, bytes]:
    """
    Try to extract one complete frame from *buf*.
    Returns ``(frame_bytes, remaining_buffer)`` or ``(None, buf)`` if
    no complete frame is available yet.

    For H264 Annex-B: a new frame starts with 0x00000001 after the first one.
    For VP8 IVF: each frame is length-prefixed in the IVF container.
    """
    from ..codecs.h264 import START_CODE_4, START_CODE_3

    if codec == Codec.H264:
        # Find second start code to delimit first frame
        pos = buf.find(START_CODE_4, 4)
        if pos == -1:
            pos = buf.find(START_CODE_3, 4)
        if pos == -1:
            return None, buf  # incomplete
        return buf[:pos], buf[pos:]

    elif codec == Codec.VP8:
        # IVF frame: 12-byte frame header, first 4 bytes = frame size
        import struct
        if len(buf) < 12:
            return None, buf
        frame_size = struct.unpack_from("<I", buf, 0)[0]
        total = 12 + frame_size
        if len(buf) < total:
            return None, buf
        return buf[12:total], buf[total:]

    return None, buf


# ──────────────────────────────────────────────────────────────────────
# VideoPlayer — public-facing player with events
# ──────────────────────────────────────────────────────────────────────

class VideoPlayer:
    """
    High-level player wrapping :class:`MediaPlayer` with events and playback
    controls.

    Usage::

        player = VideoPlayer("movie.mp4", udp)

        @player.on("finish")
        async def on_finish():
            await streamer.stop_stream()

        await player.play()
    """

    def __init__(
        self,
        source: str,
        udp: MediaUdp,
        *,
        codec: Codec = Codec.H264,
        resolution: str = "720p",
        fps: int = 30,
    ) -> None:
        from ..enums import Resolution
        res = Resolution(resolution)
        width, height = res.dimensions()

        self._player = MediaPlayer(
            source,
            udp,
            codec=codec,
            width=width,
            height=height,
            fps=fps,
        )
        self._callbacks: dict[str, list[EventCallback]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Event system
    # ------------------------------------------------------------------

    def on(self, event: str) -> Callable[[EventCallback], EventCallback]:
        """
        Decorator to register an async callback for *event*.

        Supported events: ``"start"``, ``"finish"``, ``"error"``, ``"progress"``.
        """
        def decorator(func: EventCallback) -> EventCallback:
            self._callbacks[event].append(func)
            return func
        return decorator

    async def _emit(self, event: str, *args: Any) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                await cb(*args)
            except Exception as exc:
                log.error("Error in %r event callback: %s", event, exc)

    # ------------------------------------------------------------------
    # Playback controls (delegate to MediaPlayer)
    # ------------------------------------------------------------------

    async def play(self) -> None:
        """Start playback. Fires ``start`` and ``finish`` events."""
        await self._emit("start")
        try:
            await self._player.play()
        except Exception as exc:
            await self._emit("error", exc)
            raise
        else:
            await self._emit("finish")

    def pause(self) -> None:
        """Pause playback."""
        self._player.pause()

    def resume(self) -> None:
        """Resume playback."""
        self._player.resume()

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()

    async def seek(self, seconds: float) -> None:
        """Seek to *seconds* (restarts FFmpeg)."""
        await self._player.seek(seconds)
