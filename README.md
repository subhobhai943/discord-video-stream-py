# discord-video-stream-py

> **Stream video and audio directly into Discord voice channels (Go Live / webcam) using Python. No Node.js required.**

Inspired by the TypeScript [`@dank074/discord-video-stream`](https://github.com/dank074/discord-video-stream), built from the ground up for Python developers.

[![PyPI](https://img.shields.io/pypi/v/discord-video-stream-py)](https://pypi.org/project/discord-video-stream-py/)
[![Python](https://img.shields.io/pypi/pyversions/discord-video-stream-py)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Features

- 🎬 **H264 & VP8** video streaming via Discord Go Live
- 🎙️ **Opus audio** (48 kHz stereo, 20 ms frames)
- 🔐 **SRTP encryption** — XSalsa20-Poly1305 and AES-256-GCM
- 📺 **Webcam mode** (non-Go Live)
- 🌐 **Online sources** via `yt-dlp` (YouTube, Twitch, 1000+ sites)
- ⏯️ Full playback controls: pause, resume, seek, stop
- 🔌 Familiar `discord.py`-style async API

---

## System Requirements

- Python 3.10+
- `ffmpeg` with libopus + libx264/libvpx compiled in:
  ```bash
  # Ubuntu/Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  # Download from https://ffmpeg.org/download.html and add to PATH
  ```

---

## Installation

```bash
pip install discord-video-stream-py
```

---

## Quick Start

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

# Stream from YouTube
# player = VideoPlayer("https://www.youtube.com/watch?v=dQw4w9WgXcQ", udp)

client.run("YOUR_USER_TOKEN")
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
@player.on("finish")
async def on_finish():
    await streamer.stop_stream()

@player.on("error")
async def on_error(exc):
    print(f"Stream error: {exc}")
```

---

## Development Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation | 🚧 In Progress | Voice Gateway + Audio streaming |
| 2 — Video (H264) | ⏳ Planned | H264 Go Live streaming |
| 3 — VP8 + Webcam | ⏳ Planned | VP8 codec + webcam mode |
| 4 — yt-dlp + DX | ⏳ Planned | Online sources + player events |
| 5 — Release | ⏳ Planned | PyPI publish + docs |

---

## Architecture

```
discord_video_stream/
├── __init__.py          # Public API: Streamer, VideoPlayer, enums
├── streamer.py          # Main entry point — wraps discord.py-self client
├── voice/
│   ├── gateway.py       # Voice WebSocket (all OPs, heartbeat, resume)
│   ├── udp.py           # MediaUdp — UDP socket, RTP dispatch
│   ├── rtp.py           # RTP packet builder (audio + video)
│   └── encryption.py   # XSalsa20-Poly1305 / AES-256-GCM
├── codecs/
│   ├── h264.py          # NAL unit packetizer (FU-A fragmentation)
│   ├── vp8.py           # VP8 RTP packetizer
│   └── opus.py          # Opus audio framer
├── media/
│   ├── player.py        # MediaPlayer — FFmpeg → RTP pipeline
│   ├── ffmpeg.py        # FFmpeg subprocess builder
│   └── ytdlp.py         # yt-dlp URL resolver
└── utils/
    └── ssrc.py          # SSRC generation
```

---

## Contributing

PRs welcome! See [`docs/getting-started.md`](docs/getting-started.md) for a development setup guide.

---

## License

MIT — see [LICENSE](LICENSE).
