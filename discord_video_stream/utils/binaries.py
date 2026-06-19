"""Binary resolver for ffmpeg and yt-dlp.

Handles locating the platform-specific bundled binaries or falling back to
the system installation (PATH).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys

log = logging.getLogger(__name__)


def get_platform_bin_dir() -> str | None:
    """Return the folder name containing binaries for the current OS/architecture."""
    system = sys.platform
    machine = platform.machine().lower()

    if system == "win32":
        if "amd64" in machine or "x86_64" in machine:
            return "windows-x64"
    elif system.startswith("linux"):
        if "x86_64" in machine:
            return "linux-x64"
        elif "aarch64" in machine or "arm64" in machine:
            return "linux-arm64"
    elif system == "darwin":
        if "x86_64" in machine:
            return "macos-x64"
        elif "arm64" in machine:
            return "macos-arm64"

    return None


def get_ffmpeg_path() -> str:
    """Get the path to the ffmpeg executable.

    Checks bundled directory first, then falls back to system PATH.
    """
    # 1. Check bundled
    plat_dir = get_platform_bin_dir()
    if plat_dir:
        filename = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bundled_path = os.path.join(base_dir, "bin", plat_dir, filename)

        if os.path.exists(bundled_path):
            if sys.platform != "win32":
                try:
                    os.chmod(bundled_path, 0o755)
                except Exception as exc:
                    log.warning("Could not set execute permissions on bundled ffmpeg: %s", exc)
            return bundled_path

    # 2. Check system PATH
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path

    raise RuntimeError(
        "ffmpeg not found in bundled binaries or system PATH. "
        "Install it with: sudo apt install ffmpeg  (Linux) "
        "or: brew install ffmpeg  (macOS)"
    )


def get_ytdlp_path() -> str | None:
    """Get the path to the yt-dlp executable, if available.

    Checks bundled directory first, then falls back to system PATH.
    """
    # 1. Check bundled
    plat_dir = get_platform_bin_dir()
    if plat_dir:
        filename = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bundled_path = os.path.join(base_dir, "bin", plat_dir, filename)

        if os.path.exists(bundled_path):
            if sys.platform != "win32":
                try:
                    os.chmod(bundled_path, 0o755)
                except Exception as exc:
                    log.warning("Could not set execute permissions on bundled yt-dlp: %s", exc)
            return bundled_path

    # 2. Check system PATH
    system_path = shutil.which("yt-dlp")
    if system_path:
        return system_path

    return None
