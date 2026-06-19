"""MediaPlayer and VideoPlayer — the FFmpeg → RTP streaming pipeline.

Phase 2 changes vs Phase 1:
  - Uses H264FrameReader for proper Annex-B frame delimiting
  - Passes is_keyframe flag + frame dimensions to MediaUdp
  - Video and audio tasks run in parallel with asyncio.gather
  - A/V sync: video pacing via wall-clock instead of busy-loop
  - SPS/PPS cache: injected before every IDR frame automatically
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections import defaultdict
from typing import Any, Callable, Coroutine

from ..enums import Codec
from ..voice.udp import MediaUdp
from .ffmpeg import spawn_ffmpeg
from .ytdlp import resolve_url
from ..codecs.h264 import H264FrameReader, is_keyframe, split_nalus
from ..codecs.vp8 import packetize_vp8_frame

log = logging.getLogger(__name__)

EventCallback = Callable[..., Coroutine[Any, Any, None]]


class MediaPlayer:
    """
    Low-level player: spawns FFmpeg, reads encoded frames, feeds
    :class:`~discord_video_stream.voice.udp.MediaUdp`.

    Most users should use :class:`VideoPlayer` instead.
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
        self._source        = source
        self._udp           = udp
        self._codec         = codec
        self._width         = width
        self._height        = height
        self._fps           = fps
        self._video_bitrate = video_bitrate
        self._audio_bitrate = audio_bitrate

        self._process: asyncio.subprocess.Process | None = None
        self._video_task: asyncio.Task | None = None
        self._audio_task: asyncio.Task | None = None
        self._paused      = False
        self._stop_event  = asyncio.Event()
        self._frame_duration = 1.0 / fps  # seconds per frame for pacing

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def play(self) -> None:
        """
        Resolve the source, spawn FFmpeg, stream until finished or stopped.
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
        log.info("FFmpeg spawned (PID %d)", self._process.pid)

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
        """Pause packet dispatch (FFmpeg keeps running, buffers fill)."""
        self._paused = True
        log.info("Player paused.")

    def resume(self) -> None:
        """Resume packet dispatch."""
        self._paused = False
        log.info("Player resumed.")

    def stop(self) -> None:
        """Stop streaming and kill FFmpeg."""
        self._stop_event.set()
        for task in (self._video_task, self._audio_task):
            if task:
                task.cancel()
        log.info("Player stopped.")

    async def seek(self, seconds: float) -> None:
        """Seek to *seconds* by restarting FFmpeg with ``-ss``."""
        # Phase 4 implementation
        raise NotImplementedError("seek() will be implemented in Phase 4")

    # ------------------------------------------------------------------
    # Video loop
    # ------------------------------------------------------------------

    async def _video_loop(self, reader: asyncio.StreamReader) -> None:
        """Read H264/VP8 frames from FFmpeg stdout and send as RTP."""
        frame_start = time.monotonic()

        if self._codec == Codec.H264:
            h264_reader = H264FrameReader(reader)
            try:
                async for frame in h264_reader.frames():
                    if self._stop_event.is_set():
                        break
                    while self._paused:
                        await asyncio.sleep(0.01)

                    nalus = split_nalus(frame)
                    idr   = is_keyframe(nalus)
                    payloads = h264_reader.packetize(frame)

                    if payloads:
                        await self._udp.send_video_packets(
                            payloads,
                            is_keyframe=idr,
                            width=self._width,
                            height=self._height,
                        )

                    # Pace to target fps using wall clock
                    await self._pace_frame(frame_start)
                    frame_start = time.monotonic()

            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.error("H264 video loop error: %s", exc, exc_info=True)

        elif self._codec == Codec.VP8:
            await self._vp8_loop(reader)

    async def _vp8_loop(self, reader: asyncio.StreamReader) -> None:
        """Read VP8 IVF frames from FFmpeg stdout and send as RTP."""
        frame_start = time.monotonic()
        try:
            while not self._stop_event.is_set():
                while self._paused:
                    await asyncio.sleep(0.01)
                # IVF frame header: 4 bytes size, 8 bytes pts
                hdr = await asyncio.wait_for(reader.readexactly(12), timeout=10.0)
                frame_size = struct.unpack_from("<I", hdr, 0)[0]
                frame = await reader.readexactly(frame_size)
                payloads = packetize_vp8_frame(frame)
                if payloads:
                    await self._udp.send_video_packets(
                        payloads,
                        width=self._width,
                        height=self._height,
                    )
                await self._pace_frame(frame_start)
                frame_start = time.monotonic()
        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            log.error("VP8 video loop error: %s", exc, exc_info=True)

    async def _pace_frame(self, frame_start: float) -> None:
        """
        Sleep for the remaining time in the current frame budget to achieve
        the target fps without busy-looping.
        """
        elapsed = time.monotonic() - frame_start
        remaining = self._frame_duration - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    # ------------------------------------------------------------------
    # Audio loop
    # ------------------------------------------------------------------

    async def _audio_loop(self, reader: asyncio.StreamReader) -> None:
        """Read length-prefixed Opus frames from FFmpeg stderr and send as RTP."""
        FRAME_INTERVAL = 0.020  # 20 ms
        try:
            while not self._stop_event.is_set():
                while self._paused:
                    await asyncio.sleep(0.01)
                try:
                    length_bytes = await asyncio.wait_for(
                        reader.readexactly(2), timeout=5.0
                    )
                except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                    continue

                (length,) = struct.unpack(">H", length_bytes)
                if length == 0 or length > 4000:
                    log.warning("Unexpected Opus frame length: %d — skipping", length)
                    continue

                try:
                    frame = await reader.readexactly(length)
                except asyncio.IncompleteReadError:
                    break

                await self._udp.send_audio_frame(frame)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Audio loop error: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        log.info("FFmpeg process cleaned up.")


# ---------------------------------------------------------------------------
# VideoPlayer — public-facing player with events
# ---------------------------------------------------------------------------

class VideoPlayer:
    """
    High-level player with events and playback controls.

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
        video_bitrate: str = "2M",
        audio_bitrate: str = "128k",
    ) -> None:
        from ..enums import Resolution
        res = Resolution(resolution)
        width, height = res.dimensions()

        self._player = MediaPlayer(
            source, udp,
            codec=codec,
            width=width, height=height,
            fps=fps,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )
        self._callbacks: dict[str, list[EventCallback]] = defaultdict(list)

    def on(self, event: str) -> Callable[[EventCallback], EventCallback]:
        """
        Register an async callback for *event*.

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
                log.error("Error in %r callback: %s", event, exc)

    async def play(self) -> None:
        """Start playback. Fires ``start`` then ``finish`` events."""
        await self._emit("start")
        try:
            await self._player.play()
        except Exception as exc:
            await self._emit("error", exc)
            raise
        else:
            await self._emit("finish")

    def pause(self)  -> None: self._player.pause()
    def resume(self) -> None: self._player.resume()
    def stop(self)   -> None: self._player.stop()

    async def seek(self, seconds: float) -> None:
        await self._player.seek(seconds)
