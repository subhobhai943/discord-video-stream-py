"""Binary resolver for ffmpeg and yt-dlp.

Delegates to _bootstrap for lazy download logic.
Keeps a PATH fallback for environments where the user has installed
ffmpeg/yt-dlp system-wide and prefers not to use the bundled binaries.
"""

from __future__ import annotations

from .._bootstrap import get_ffmpeg_path, get_ytdlp_path, get_platform_key

__all__ = ["get_ffmpeg_path", "get_ytdlp_path", "get_platform_key"]
