# Getting Started

## Prerequisites

- **Python 3.10+**
- **ffmpeg** with `libopus` and `libx264` (or `libvpx` for VP8):
  ```bash
  # Ubuntu / Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  # Download from https://ffmpeg.org/download.html and add ffmpeg to your PATH
  ```

## Installation

### From PyPI (once published)

```bash
pip install discord-video-stream-py
```

### From source (development)

```bash
git clone https://github.com/subhobhai943/discord-video-stream-py.git
cd discord-video-stream-py
pip install -e ".[dev]"
```

## Running the example bot

```bash
export DISCORD_TOKEN="your_user_token"
export GUILD_ID="123456789"
export CHANNEL_ID="987654321"
export VIDEO_FILE="path/to/movie.mp4"

python examples/movie_bot.py
```

## Running the tests

```bash
pip install pytest pytest-asyncio
pytest
```

## Architecture Overview

See the [README](../README.md#architecture) for the full module tree.

## Development Phases

| Phase | Goal |
|-------|------|
| **1 — Foundation** | Voice Gateway handshake + Opus audio streaming |
| **2 — H264 Video** | Go Live H264 video streaming |
| **3 — VP8 + Webcam** | VP8 codec + webcam mode |
| **4 — yt-dlp + DX** | Online sources + full player API |
| **5 — Release** | PyPI package + full docs |

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Run tests: `pytest`
4. Open a PR against `main`

Join the discussion on GitHub Issues for questions and feature requests.
