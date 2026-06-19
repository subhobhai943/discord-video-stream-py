"""Bootstrap module: lazy-downloads ffmpeg and yt-dlp for the current
platform/architecture on first use. Nothing is bundled in the package.

This module is intentionally import-safe: importing it never triggers a
download. Downloads happen only when ``get_ffmpeg_path()`` or
``get_ytdlp_path()`` are called for the first time and the binary is absent.

Public API
----------
ensure_binaries(verbose=True)  -- download if missing (idempotent, safe to call multiple times)
get_ffmpeg_path()              -- absolute path to ffmpeg binary (downloads if needed)
get_ytdlp_path()               -- absolute path to yt-dlp binary (downloads if needed)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

log = logging.getLogger(__name__)

BIN_DIR = os.path.join(os.path.dirname(__file__), "bin")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# (ffmpeg_url, archive_type, ffmpeg_filename, ytdlp_url, ytdlp_filename)
SOURCES: dict[str, dict] = {
    "windows-x64": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "zip",
            "ffmpeg.exe",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
            "yt-dlp.exe",
        ),
    },
    "linux-x64": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
            "tar.xz",
            "ffmpeg",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
            "yt-dlp",
        ),
    },
    "linux-arm64": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
            "tar.xz",
            "ffmpeg",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64",
            "yt-dlp",
        ),
    },
    "macos-x64": {
        "ffmpeg": (
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip",
            "zip",
            "ffmpeg",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
            "yt-dlp",
        ),
    },
    "macos-arm64": {
        "ffmpeg": (
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip",
            "zip",
            "ffmpeg",
        ),
        "ytdlp": (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
            "yt-dlp",
        ),
    },
}


def get_platform_key() -> str:
    """Detect the current platform/arch key used in SOURCES and bin/ layout."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "windows-x64"
    if system == "linux":
        return "linux-arm64" if machine in ("aarch64", "arm64") else "linux-x64"
    if system == "darwin":
        return "macos-arm64" if machine == "arm64" else "macos-x64"
    raise RuntimeError(
        f"Unsupported platform: {system}-{machine}. "
        "Please install ffmpeg and yt-dlp manually and add them to PATH."
    )


def ensure_binaries(verbose: bool = True) -> None:
    """Download ffmpeg + yt-dlp for the current platform if not already present.

    Safe to call multiple times — exits instantly if both binaries exist.
    Does NOT run automatically on import; called lazily by get_ffmpeg_path()
    and get_ytdlp_path().
    """
    key = get_platform_key()
    plat_dir = os.path.join(BIN_DIR, key)
    os.makedirs(plat_dir, exist_ok=True)

    cfg = SOURCES[key]
    _ensure_ffmpeg(plat_dir, cfg["ffmpeg"], key, verbose)
    _ensure_ytdlp(plat_dir, cfg["ytdlp"], key, verbose)


def get_ffmpeg_path() -> str:
    """Return the absolute path to the ffmpeg binary.

    Downloads the binary on first call if not already present.
    Falls back to the system PATH if the download fails.
    """
    key = get_platform_key()
    plat_dir = os.path.join(BIN_DIR, key)
    fname = SOURCES[key]["ffmpeg"][2]
    dest = os.path.join(plat_dir, fname)

    if not os.path.isfile(dest):
        try:
            os.makedirs(plat_dir, exist_ok=True)
            _ensure_ffmpeg(plat_dir, SOURCES[key]["ffmpeg"], key, verbose=True)
        except Exception as exc:
            log.warning("Could not download ffmpeg binary: %s. Falling back to PATH.", exc)
            system_path = shutil.which("ffmpeg")
            if system_path:
                return system_path
            raise RuntimeError(
                "ffmpeg not found. Install it with:\n"
                "  Linux : sudo apt install ffmpeg\n"
                "  macOS : brew install ffmpeg\n"
                "  Windows: https://ffmpeg.org/download.html"
            ) from exc

    return dest


def get_ytdlp_path() -> str | None:
    """Return the absolute path to the yt-dlp binary.

    Downloads the binary on first call if not already present.
    Falls back to the system PATH. Returns None if unavailable.
    """
    key = get_platform_key()
    plat_dir = os.path.join(BIN_DIR, key)
    fname = SOURCES[key]["ytdlp"][1]
    dest = os.path.join(plat_dir, fname)

    if not os.path.isfile(dest):
        try:
            os.makedirs(plat_dir, exist_ok=True)
            _ensure_ytdlp(plat_dir, SOURCES[key]["ytdlp"], key, verbose=True)
        except Exception as exc:
            log.warning("Could not download yt-dlp binary: %s. Falling back to PATH.", exc)
            return shutil.which("yt-dlp")

    return dest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_ffmpeg(plat_dir: str, cfg: tuple, key: str, verbose: bool) -> None:
    url, archive_type, filename = cfg
    dest = os.path.join(plat_dir, filename)
    if os.path.isfile(dest):
        return
    if verbose:
        print(f"[discord-video-stream] Downloading ffmpeg for {key} ...")
    with tempfile.TemporaryDirectory() as tmp:
        ext = ".zip" if archive_type == "zip" else ".tar.xz"
        archive = os.path.join(tmp, f"ffmpeg{ext}")
        _download(url, archive)
        _extract_binary(archive, archive_type, filename, dest)
    if key != "windows-x64":
        os.chmod(dest, 0o755)
    if verbose:
        print(f"[discord-video-stream] ffmpeg ready: {dest}")


def _ensure_ytdlp(plat_dir: str, cfg: tuple, key: str, verbose: bool) -> None:
    url, filename = cfg
    dest = os.path.join(plat_dir, filename)
    if os.path.isfile(dest):
        return
    if verbose:
        print(f"[discord-video-stream] Downloading yt-dlp for {key} ...")
    _download(url, dest)
    if key != "windows-x64":
        os.chmod(dest, 0o755)
    if verbose:
        print(f"[discord-video-stream] yt-dlp ready: {dest}")


def _download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def _extract_binary(
    archive: str, archive_type: str, target_filename: str, dest: str
) -> None:
    if archive_type == "zip":
        with zipfile.ZipFile(archive, "r") as zf:
            for info in zf.infolist():
                if os.path.basename(info.filename) == target_filename:
                    with zf.open(info) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return
    elif archive_type == "tar.xz":
        with tarfile.open(archive, "r:xz") as tf:
            for member in tf.getmembers():
                if os.path.basename(member.name) == target_filename and member.isfile():
                    src = tf.extractfile(member)
                    if src:
                        with open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    return
    raise RuntimeError(
        f"Could not find '{target_filename}' inside archive '{archive}'"
    )
