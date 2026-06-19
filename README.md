<p align="center">
  <img src="docs/images/logo.jpg" alt="discord-video-stream-py Logo" width="220"/>
</p>

<h1 align="center">discord-video-stream-py</h1>

> **Stream video and audio directly into Discord voice channels (Go Live / webcam) using Python. No Node.js required.**

Inspired by the TypeScript [`@dank074/discord-video-stream`](https://github.com/dank074/discord-video-stream), built from the ground up for Python developers.

[![PyPI](https://img.shields.io/pypi/v/discord-video-stream-py)](https://pypi.org/project/discord-video-stream-py/)
[![Python](https://img.shields.io/pypi/pyversions/discord-video-stream-py)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Features

- 🎬 **H264 & VP8** video streaming via Discord Go Live
- 🎙️ **Opus audio** (48 kHz stereo, 20 ms frames)
- 🔐 **Full SRTP encryption** — XSalsa20-Poly1305, XChaCha20-Poly1305, and AES-256-GCM
- 📺 **Webcam mode** (non-Go Live) and **Go Live** streaming
- 🌐 **Online sources** via `yt-dlp` (YouTube, Twitch, 1000+ sites)
- ⏯️ Full playback controls: pause, resume, seek, stop
- 🔁 **Auto-reconnect** with exponential backoff on voice gateway drops
- 🎛️ **Events system** — `on_start`, `on_finish`, `on_error`, `on_progress`
- 📐 **Resolution presets** — 480p, 720p, 1080p, or source quality
- 🔌 Familiar `discord.py`-style async API

---

## System Requirements

- Python 3.10+
- (Optional) `ffmpeg` and `yt-dlp` installed in your system PATH.

> [!NOTE]
> **Zero Setup Required:** The library automatically downloads and bundles cross-platform static binaries for `ffmpeg` and `yt-dlp` (supporting Windows x64, Linux x64/arm64, and macOS Intel/Apple Silicon). The library will fall back to your system's `ffmpeg` or `yt-dlp` if the bundled binaries are not found.

---

## Installation

```bash
pip install discord-video-stream-py
```

---

## Quick Start

### Stream a local file

```python
import discord
from discord_video_stream import Streamer, VideoPlayer

client = discord.Client()
streamer = Streamer(client)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await streamer.join_voice(guild_id=123456789, channel_id=987654321)
    udp = await streamer.create_stream(resolution="720p", fps=30, codec="h264")
    player = VideoPlayer("movie.mp4", udp)
    await player.play()

client.run("YOUR_USER_TOKEN")
```

### Stream from YouTube

```python
player = VideoPlayer("https://www.youtube.com/watch?v=dQw4w9WgXcQ", udp)
await player.play()
```

### VP8 & Webcam mode

```python
udp = await streamer.create_stream(
    resolution="480p", fps=30,
    codec="vp8", stream_type="webcam"
)
player = VideoPlayer("video.mp4", udp, codec="vp8")
await player.play()
```

### Playback Controls

```python
player.pause()
await player.seek(120)  # seek to 2:00
player.resume()
player.stop()
```

### Events

```python
@player.on("start")
async def on_start():
    print("Streaming started!")

@player.on("finish")
async def on_finish():
    await streamer.stop_stream()

@player.on("error")
async def on_error(exc):
    print(f"Stream error: {exc}")
```

---

## API Reference

### `Streamer(client)`

Wraps a `discord.py-self` Client and manages the stream lifecycle.

| Method | Description |
|--------|-------------|
| `await join_voice(guild_id, channel_id)` | Join a voice channel |
| `await create_stream(resolution, fps, codec, stream_type)` | Start streaming, returns `MediaUdp` |
| `await stop_stream()` | Stop the stream and clean up |
| `await leave_voice(guild_id)` | Leave the voice channel |

### `VideoPlayer(source, udp, **kwargs)`

High-level media player with events.

| Method | Description |
|--------|-------------|
| `await play()` | Start playback |
| `pause()` | Pause (FFmpeg keeps running) |
| `resume()` | Resume playback |
| `await seek(seconds)` | Seek to position (restarts FFmpeg) |
| `stop()` | Stop playback |
| `on(event)(callback)` | Register event callback |

### Enums

| Enum | Values |
|------|--------|
| `Codec` | `"h264"`, `"vp8"` |
| `StreamType` | `"go_live"`, `"webcam"` |
| `Resolution` | `"480p"`, `"720p"`, `"1080p"`, `"source"` |

---

## Development Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation | ✅ Complete | Voice Gateway + Audio streaming |
| 2 — Video (H264) | ✅ Complete | H264 Go Live streaming + FU-A fragmentation |
| 3 — VP8 + Webcam | ✅ Complete | VP8 codec + webcam mode |
| 4 — yt-dlp + DX | ✅ Complete | Online sources + player events + seek |
| 5 — Release | 🚧 In Progress | PyPI publish + docs + tests |

---

## Architecture

```
discord_video_stream/
├── __init__.py          # Public API: Streamer, VideoPlayer, enums
├── streamer.py          # Main entry point — wraps discord.py-self client
├── bin/                 # Bundled cross-platform binaries (FFmpeg & yt-dlp)
│   ├── windows-x64/
│   ├── linux-x64/
│   ├── linux-arm64/
│   ├── macos-x64/
│   └── macos-arm64/
├── voice/
│   ├── gateway.py       # Voice WebSocket (all OPs, heartbeat, resume)
│   ├── udp.py           # MediaUdp — UDP socket, RTP dispatch, keepalive
│   ├── rtp.py           # RTP packet builder (audio + video + extension)
│   └── encryption.py    # XSalsa20 / XChaCha20 / AES-256-GCM encryption
├── codecs/
│   ├── h264.py          # NAL unit packetizer (FU-A fragmentation, SPS/PPS)
│   ├── vp8.py           # VP8 RTP packetizer (RFC 7741)
│   └── opus.py          # Opus audio framer (48kHz, 20ms)
├── media/
│   ├── player.py        # MediaPlayer + VideoPlayer — FFmpeg → RTP pipeline
│   ├── ffmpeg.py        # FFmpeg subprocess builder (H264/VP8/Opus)
│   └── ytdlp.py         # yt-dlp URL resolver
└── utils/
    ├── ssrc.py          # SSRC generation + video/RTX offsets
    └── binaries.py      # Cross-platform binary helper/resolver
```

---

## Contributing

PRs welcome! See [`docs/getting-started.md`](docs/getting-started.md) for a development setup guide.

```bash
git clone https://github.com/subhobhai943/discord-video-stream-py.git
cd discord-video-stream-py
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
