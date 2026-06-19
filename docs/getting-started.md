# Getting Started with discord-video-stream-py

This guide walks you through setting up and using `discord-video-stream-py` to stream video into Discord voice channels from Python.

## Prerequisites

### 1. Python 3.10+

```bash
python --version  # must be 3.10 or higher
```

### 2. FFmpeg

FFmpeg must be installed with `libopus`, `libx264`, and optionally `libvpx` support.

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Verify it's installed
ffmpeg -version
```

### 3. Discord Token

This library uses `discord.py-self`, which works with **user tokens** (selfbot). You'll need your Discord user token.

> ⚠️ **Selfbots violate Discord's Terms of Service.** Use at your own risk. This library is intended for educational and private use only.

## Installation

### From PyPI (when published)

```bash
pip install discord-video-stream-py
```

### From source (development)

```bash
git clone https://github.com/subhobhai943/discord-video-stream-py.git
cd discord-video-stream-py
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows
pip install -e .
```

## Basic Usage

### Minimal Example — Stream a Local File

```python
import discord
from discord_video_stream import Streamer, VideoPlayer

client = discord.Client()
streamer = Streamer(client)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    # Join a voice channel
    await streamer.join_voice(guild_id=YOUR_GUILD_ID, channel_id=YOUR_CHANNEL_ID)

    # Create a stream (Go Live)
    udp = await streamer.create_stream(
        resolution="720p",
        fps=30,
        codec="h264",
    )

    # Play a video file
    player = VideoPlayer("movie.mp4", udp)
    await player.play()

    # Clean up
    await streamer.stop_stream()

client.run("YOUR_TOKEN")
```

### Stream from YouTube

The library integrates with `yt-dlp` to automatically resolve URLs from 1000+ sites:

```python
player = VideoPlayer("https://www.youtube.com/watch?v=dQw4w9WgXcQ", udp)
await player.play()
```

No extra code needed — the URL is automatically resolved before passing to FFmpeg.

### VP8 Codec + Webcam Mode

```python
udp = await streamer.create_stream(
    resolution="480p",
    fps=30,
    codec="vp8",
    stream_type="webcam",  # or "go_live" (default)
)
player = VideoPlayer("video.mp4", udp, codec="vp8")
await player.play()
```

### Playback Controls

```python
player.pause()       # Pause (FFmpeg keeps running)
player.resume()      # Resume playback
await player.seek(120)  # Seek to 2:00 mark (restarts FFmpeg at offset)
player.stop()        # Stop completely
```

### Event Handling

```python
@player.on("start")
async def on_start():
    print("Streaming started!")

@player.on("finish")
async def on_finish():
    print("Playback finished.")
    await streamer.stop_stream()

@player.on("error")
async def on_error(exc):
    print(f"Error during streaming: {exc}")
```

## Configuration Options

### Resolution Presets

| Preset | Dimensions | Typical Use |
|--------|-----------|-------------|
| `"480p"` | 854 × 480 | Lower bandwidth, mobile |
| `"720p"` | 1280 × 720 | Default, good quality |
| `"1080p"` | 1920 × 1080 | High quality |
| `"source"` | Original | Pass-through (no scaling) |

### Codec Selection

| Codec | RTP PT | Notes |
|-------|--------|-------|
| `"h264"` (default) | 101 | Best quality, hardware decode |
| `"vp8"` | 100 | Open codec, wider compatibility |

### Stream Types

| Type | Description |
|------|-------------|
| `"go_live"` (default) | Screen share / Go Live mode |
| `"webcam"` | Camera-style stream |

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                 Your Bot Code                    │
│  Streamer ─── VideoPlayer ─── on("finish")       │
└──────┬────────────┬──────────────────────────────┘
       │            │
       ▼            ▼
┌────────────┐  ┌─────────────────────────┐
│   Voice    │  │     Media Pipeline       │
│  Gateway   │  │  FFmpeg → H264/VP8       │
│  (WS)      │  │        → Opus            │
│  OP 0-18   │  │  yt-dlp URL resolver     │
└─────┬──────┘  └──────────┬──────────────┘
      │                    │
      ▼                    ▼
┌──────────────────────────────────────────────┐
│              MediaUdp                         │
│  RTP Header ──► Encrypt (SRTP) ──► UDP Send  │
│  Nonce counter, keepalive, A/V sync          │
└──────────────────────────────────────────────┘
```

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Troubleshooting

### "ffmpeg not found in PATH"

Make sure `ffmpeg` is installed and accessible:
```bash
which ffmpeg   # Linux/macOS
where ffmpeg   # Windows
```

### Video shows but no audio (or vice versa)

- Ensure your video file has both audio and video streams
- Check FFmpeg can decode it: `ffprobe your_file.mp4`

### Connection drops frequently

The library auto-reconnects with exponential backoff (up to 5 attempts). If connections keep dropping, check your network stability and Discord rate limits.

### "Unsupported encryption mode"

Your Discord client may be using a newer encryption mode. The library supports:
- `aead_xchacha20_poly1305_rtpsize` (primary)
- `aead_aes256_gcm_rtpsize`
- `xsalsa20_poly1305_lite_rtpsize`
- `xsalsa20_poly1305_lite`
- `xsalsa20_poly1305_suffix`
- `xsalsa20_poly1305`

## Next Steps

- See [`examples/movie_bot.py`](../examples/movie_bot.py) for a full Discord bot example
- See [`examples/stream_file.py`](../examples/stream_file.py) for a minimal example
- Read the [ROADMAP.md](../ROADMAP.md) for planned features
