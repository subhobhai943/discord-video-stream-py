# discord-video-stream-py — Project Plan

> A Python library for streaming video directly into Discord voice channels using a bot token or selfbot account. Inspired by the TypeScript `@dank074/discord-video-stream`, built from the ground up for Python.

---

## 1. Project Vision

The goal is a clean, pip-installable Python library — `discord-video-stream-py` — that lets any developer build a Discord bot capable of streaming actual video (with audio) into a voice channel's Go Live / webcam stream, using familiar `discord.py`-style APIs. No Node.js required.

There is currently **no maintained Python library** for this purpose. The TypeScript ecosystem has `@dank074/discord-video-stream` and `discord-stream-client`, but Python developers have no equivalent. This library fills that gap and opens the feature to the much larger Python bot-dev community.

---

## 2. How Discord Video Streaming Works (Technical Foundation)

Understanding the underlying protocol is the hardest and most critical part of this project.

### 2.1 Voice Gateway (WebSocket)

Before any media flows, a standard Discord Voice Gateway handshake must occur:[cite:54]

1. **OP 0 — Identify**: Send `guild_id`, `user_id`, `session_id`, `token`
2. **OP 2 — Ready**: Receive `ssrc` (Synchronization Source), UDP IP/port, supported encryption modes
3. **OP 1 — Select Protocol**: Send chosen encryption mode (e.g., `aead_aes256_gcm_rtpsize`) and UDP external IP/port (discovered via UDP hole punch)
4. **OP 4 — Session Description**: Receive the secret key for encrypting media packets
5. **OP 18 — Video / Go Live**: Send to signal video capability and stream resolution/framerate/codec

The library must handle **heartbeating** (OP 3) to keep the WebSocket alive, and **resuming** (OP 7/9) on disconnect.[cite:54]

### 2.2 UDP Media Packets (RTP)

All actual audio and video is sent over UDP using RTP (Real-time Transport Protocol):[cite:48][cite:49]

**Audio packets:**
- Codec: **Opus**, 48kHz, 2 channels (stereo), 20ms frames
- Packet structure: `RTP Header (12 bytes)` + `Encrypted Opus payload`
- RTP Header fields: version=2, payload type=`0x78`, sequence number, timestamp, SSRC

**Video packets:**
- Codec: **H264** (default) or **VP8**
- Packetized using **RTP H264 NAL unit fragmentation** (RFC 6184) or VP8 RTP payload format (RFC 7741)
- Discord uses a custom extension header for video metadata (rotation, width, height)
- Sent on a separate SSRC (`ssrc + 1` or a dedicated video SSRC)

### 2.3 Transport Encryption

Discord uses **SRTP-style encryption** with XSalsa20-Poly1305 or AES-256-GCM, keyed from the session description secret:[cite:51][cite:52]

- Nonce is derived from the RTP header (in `aead_aes256_gcm_rtpsize` mode, the last 4 bytes of header)
- The library must implement this correctly or video will be silently dropped by Discord's SFU

### 2.4 FFmpeg Pipeline

Raw video/audio from a file or URL is decoded and re-encoded by FFmpeg:[cite:42]

```
Input (mp4/mkv/URL/stream)
  └─► FFmpeg subprocess
        ├─► Video: H264/VP8 encoded → raw NAL units → RTP packetized → encrypted → UDP
        └─► Audio: Opus encoded (48kHz stereo 20ms) → RTP packetized → encrypted → UDP
```

`yt-dlp` handles URL extraction for YouTube, Twitch, and 1000+ other platforms before passing the stream URL to FFmpeg.

---

## 3. Library Architecture

```
discord_video_stream/
├── __init__.py                  # Public API surface: Streamer, Player, enums
├── streamer.py                  # Main Streamer class — wraps discord.py-self client
├── voice/
│   ├── __init__.py
│   ├── gateway.py               # Voice WebSocket handler (OPs, heartbeat, resume)
│   ├── udp.py                   # MediaUdp — sends/receives RTP packets over UDP
│   ├── rtp.py                   # RTP packet builder/parser (audio + video headers)
│   └── encryption.py            # XSalsa20-Poly1305 / AES-256-GCM packet encryption
├── codecs/
│   ├── __init__.py
│   ├── h264.py                  # H264 NAL unit packetizer (single, FU-A fragmentation)
│   ├── vp8.py                   # VP8 RTP payload packetizer
│   └── opus.py                  # Opus audio framer (48kHz, 2ch, 20ms)
├── media/
│   ├── __init__.py
│   ├── player.py                # MediaPlayer — manages FFmpeg subprocess + packet dispatch
│   ├── ffmpeg.py                # FFmpeg pipeline builder (args, pipes, process management)
│   └── ytdlp.py                 # yt-dlp URL resolver for online sources
└── utils/
    ├── __init__.py
    └── ssrc.py                  # SSRC generation and video SSRC offset management
```

### 3.1 Core Classes

**`Streamer`** — Entry point for library users:
```python
from discord_video_stream import Streamer
streamer = Streamer(client)                        # wraps discord.py-self Client
await streamer.join_voice(guild_id, channel_id)
udp = await streamer.create_stream()               # initiates Go Live
player = streamer.create_player("video.mp4", udp)
await player.play()
```

**`MediaUdp`** — Manages the UDP socket, sequence numbers, timestamps, and dispatches encrypted RTP packets to Discord's voice server.

**`MediaPlayer`** — Spawns an FFmpeg subprocess, reads raw H264/Opus frames from stdout pipes, packetizes them, and feeds `MediaUdp`.

**`VoiceGateway`** — Maintains the WebSocket connection to Discord's voice gateway, handles all OPs, heartbeat loop, and session resumption.

---

## 4. Development Phases

### Phase 1 — Foundation (Voice Gateway + Audio)
**Goal:** Bot joins VC and streams audio correctly.

- [ ] Implement `VoiceGateway` with all required OPs (0, 1, 2, 3, 4, 5, 7, 8, 9)
- [ ] Implement UDP hole punching (IP discovery)
- [ ] Implement `encryption.py` — XSalsa20-Poly1305 (`aead_xchacha20_poly1305_rtpsize`)
- [ ] Implement `rtp.py` — RTP header construction for audio
- [ ] Implement `opus.py` — Opus framer
- [ ] FFmpeg subprocess → raw Opus frames → UDP
- [ ] Test: Bot plays audio in VC ✅

### Phase 2 — Video Streaming (H264)
**Goal:** Bot streams H264 video via Go Live.

- [ ] Add OP 18 handling to `gateway.py` (video signalling, resolution/fps/codec negotiation)
- [ ] Implement `h264.py` — SPS/PPS detection, NAL unit splitting, FU-A fragmentation for large NALs
- [ ] Add video RTP header (separate SSRC, video extension header for Discord)
- [ ] Wire FFmpeg `-f h264` raw output pipe → H264 packetizer → UDP
- [ ] Test: Bot streams video in Go Live mode ✅

### Phase 3 — VP8 + Webcam Mode
**Goal:** Support VP8 codec and webcam (non-Go Live) streaming.

- [ ] Implement `vp8.py` — VP8 RTP payload format packetizer (RFC 7741)
- [ ] Add codec selection API (`codec="vp8"` or `codec="h264"`)
- [ ] Add `stream_type="webcam"` mode (different OP 18 flags vs Go Live)
- [ ] Test: Both codec modes work ✅

### Phase 4 — Online Sources + DX Polish
**Goal:** yt-dlp integration + clean developer experience.

- [ ] Implement `ytdlp.py` — async URL resolver, best format selection
- [ ] Add `Player` events: `on_start`, `on_finish`, `on_error`, `on_progress`
- [ ] Add resolution presets: `"480p"`, `"720p"`, `"1080p"`, `"source"`
- [ ] Add `player.pause()`, `player.resume()`, `player.seek(seconds)`, `player.stop()`
- [ ] Write full API docs with docstrings

### Phase 5 — Stability + Release
**Goal:** Production-ready, pip-installable library.

- [ ] Handle voice gateway reconnects and session resumption gracefully
- [ ] Add `asyncio`-safe cleanup (cancel tasks, close sockets, kill FFmpeg on stop)
- [ ] Write pytest test suite (mock UDP, gateway, FFmpeg pipe)
- [ ] Package as `pyproject.toml` (build with `hatchling`)
- [ ] Publish to PyPI as `discord-video-stream-py`
- [ ] Create example bot (`examples/movie_bot.py`)

---

## 5. Dependencies

| Package | Purpose |
|---------|---------|
| `discord.py-self` | Selfbot client with voice gateway access[cite:42] |
| `PyNaCl` | XSalsa20-Poly1305 encryption for SRTP packets[cite:52] |
| `cryptography` | AES-256-GCM for newer Discord encryption modes[cite:51] |
| `yt-dlp` | Extract direct stream URLs from YouTube, Twitch, etc.[cite:42] |
| `ffmpeg-python` | Pythonic FFmpeg subprocess wrapper |
| `websockets` | Async WebSocket client for voice gateway[cite:54] |
| `aiohttp` | HTTP client for Discord REST API calls |
| `asyncio` | Async I/O runtime (stdlib) |

**System dependencies (user must install):**
- `ffmpeg` (with libopus, libx264 or libvpx support)
- `ffprobe` (bundled with ffmpeg)

---

## 6. Key Technical Challenges

### 6.1 H264 NAL Fragmentation
H264 video is encoded as NAL (Network Abstraction Layer) units. NALs larger than the MTU (~1200 bytes) must be split using **FU-A fragmentation** (RFC 6184). The packetizer must:[cite:41]
- Detect SPS/PPS NALs and send them before IDR frames
- Split large NALs into FU-A fragments with correct `start`/`end` flags
- Set the RTP marker bit on the last fragment of each frame

### 6.2 A/V Synchronization
Audio and video have separate RTP timestamp clocks (audio: 48kHz, video: 90kHz). Keeping them synchronized requires careful management of initial timestamps and wall-clock anchoring in the FFmpeg pipeline.

### 6.3 Discord's DAVE E2EE Protocol
Discord rolled out the DAVE (Discord Audio/Video End-to-End Encryption) protocol in 2024.[cite:51] Servers with E2EE enabled require an additional MLS (Messaging Layer Security) key ratchet on top of SRTP. The library needs to detect this and implement the DAVE handshake for full compatibility.

### 6.4 Voice Gateway Resumption
Discord voice connections drop randomly. The library must detect disconnects, attempt to resume via OP 7 (Resume) before falling back to a full reconnect, and buffer/re-queue in-flight packets during reconnection.[cite:54]

---

## 7. Public API Design (Target Usage)

**Minimal example — stream a local file:**
```python
import discord
from discord_video_stream import Streamer, VideoPlayer

client = discord.Client()
streamer = Streamer(client)

@client.event
async def on_ready():
    await streamer.join_voice(guild_id=123, channel_id=456)
    udp = await streamer.create_stream(resolution="720p", fps=30, codec="h264")
    player = VideoPlayer("movie.mp4", udp)
    await player.play()

client.run("USER_TOKEN")
```

**Stream from YouTube:**
```python
player = VideoPlayer("https://www.youtube.com/watch?v=dQw4w9WgXcQ", udp)
await player.play()
```

**Playback controls:**
```python
player.pause()
await player.seek(120)   # seek to 2 minutes
player.resume()
player.stop()
```

**Events:**
```python
@player.on("finish")
async def on_finish():
    await streamer.stop_stream()
```

---

## 8. Repository Structure

```
discord-video-stream-py/
├── discord_video_stream/        # Library source
├── examples/
│   ├── movie_bot.py             # Full example Discord bot
│   └── stream_file.py           # Minimal streaming example
├── tests/
│   ├── test_rtp.py
│   ├── test_h264_packetizer.py
│   ├── test_encryption.py
│   └── test_gateway.py
├── docs/
│   └── getting-started.md
├── pyproject.toml               # Build config (hatchling)
├── README.md
└── LICENSE                      # MIT
```

---

## 9. Reference Implementations to Study

| Project | Language | What to learn |
|---------|----------|---------------|
| `@dank074/discord-video-stream` | TypeScript | Full RTP/H264/VP8/encryption pipeline[cite:41][cite:42] |
| `discord-stream-rs` | Rust | Direct port of the TS lib — cleaner architecture[cite:53] |
| `discord-haskell-voice` | Haskell | Clean RTP header struct layout[cite:43] |
| Discord DAVE Protocol spec | Markdown | E2EE layer on top of SRTP[cite:51] |
| Discord voice connections docs | Markdown | Official gateway OP reference[cite:54] |

---

## 10. Milestones & Timeline (Estimate)

| Milestone | Deliverable | Est. Time |
|-----------|-------------|-----------|
| M1 | Audio playback working in VC | 1–2 weeks |
| M2 | H264 video streaming (Go Live) | 2–3 weeks |
| M3 | VP8 + webcam mode | 1 week |
| M4 | yt-dlp + full player API | 1 week |
| M5 | PyPI publish + docs + examples | 1 week |
| **Total** | **v1.0.0 release** | **~6–8 weeks** |
