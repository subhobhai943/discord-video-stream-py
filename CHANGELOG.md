# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.1] — 2026-06-24

### Fixed
- **`ytdlp.py` — Cookie authentication support** — `resolve_url()` now reads
  `YTDLP_COOKIES_FILE` (default `cookies.txt`) and `YTDLP_BROWSER` environment
  variables and passes them to both the yt-dlp binary (via `--cookies` /
  `--cookies-from-browser` CLI flags) and the Python module (via `cookiefile` /
  `cookiesfrombrowser` opts). Fixes YouTube bot-detection errors
  (`Sign in to confirm you're not a bot`) when streaming YouTube videos.
- **`ytdlp.py` — Default format selector updated** — changed from
  `bestvideo+bestaudio/best` to `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best`
  to ensure FFmpeg always receives a compatible combined mp4 stream.

---

## [Unreleased]

### Phase 2 — H264 Video Streaming (Go Live)

#### Added
- **`H264FrameReader`** (`codecs/h264.py`) — async generator that reads a raw
  Annex-B byte stream from an `asyncio.StreamReader` and yields complete frames
  delimited by start codes.
- **`extract_sps_pps()`** — extracts SPS and PPS NAL units from a bitstream;
  used to build a cache that is injected before every IDR (keyframe).
- **`is_keyframe()` / `nal_type()`** — helpers for NAL classification.
- **`_split_next_frame()`** — internal buffer splitter for Annex-B streams.
- **AUD (Access Unit Delimiter) stripping** in `packetize_h264_frame()` —
  Discord's SFU rejects AUD NALs, so they are now silently dropped.
- **SPS/PPS injection before IDR frames** — ensures remote decoders can always
  recover without prior state (handles late-joiners and reconnects).
- **Discord video RTP extension header** (`voice/rtp.py`) — one-byte RFC 5285
  extension with frame dimensions (width/4, height/4) and rotation, included on
  the first packet of every keyframe.
- **`MediaUdp` codec/fps/dimensions constructor params** — `fps`, `width`,
  `height`, and `codec` passed from `Streamer.create_stream()` so video timestamp
  increments are automatically correct for any fps setting.
- **Wall-clock frame pacing** in `MediaPlayer._video_loop()` — replaces the
  previous busy-loop with `asyncio.sleep(remaining)` to hit target fps without
  over-sending.
- **VP8 IVF frame reader** in `MediaPlayer._vp8_loop()` — reads 12-byte IVF
  frame headers to delimit VP8 frames (vs the undifferentiated chunk approach).
- **`is_keyframe` + dimension passthrough** in `MediaUdp.send_video_packets()` —
  extension header only included on first packet of keyframes.
- **`Streamer.create_stream()`** now forwards `codec`, `fps`, `width`, `height`
  to `MediaUdp` so all components share the same stream parameters.
- **Extended test suite** for `test_h264_packetizer.py` and `test_rtp.py` —
  covers FU-A flags, SPS/PPS injection, AUD stripping, extension header
  dimensions and profile bytes.

#### Fixed
- `h264.py` was truncated in Phase 1 commit (missing `_fragment_fu_a` end and
  all Phase 2 additions) — replaced with complete implementation.

---

## [0.1.0] — Phase 1 Foundation

### Added
- `VoiceGateway` — full Discord voice WebSocket handshake (OP 0/1/2/3/4/8/18),
  UDP hole-punch, heartbeat loop, session resume.
- `MediaUdp` — UDP socket, audio + video RTP dispatch.
- `encryption.py` — xchacha20-poly1305, aes-256-gcm, xsalsa20 (all modes).
- `rtp.py` — audio and video RTP header builder + parser.
- `opus.py` — `OpusFramer` for length-prefixed Opus frames.
- `h264.py` — Annex-B split, FU-A fragmentation (Phase 1 stub).
- `vp8.py` — VP8 RTP payload descriptor packetizer.
- `ffmpeg.py` — FFmpeg subprocess builder.
- `player.py` — `MediaPlayer` + `VideoPlayer` with event system.
- `ytdlp.py` — async yt-dlp URL resolver.
- `streamer.py` — `Streamer` entry-point class.
- `pyproject.toml`, `README.md`, CI workflow, examples, tests.
