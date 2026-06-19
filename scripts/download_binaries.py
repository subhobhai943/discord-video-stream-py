#!/usr/bin/env python3
"""Script to download and extract cross-platform binaries of FFmpeg and yt-dlp.

Downloads:
  - FFmpeg for Windows, Linux, and macOS (x64 and arm64).
  - yt-dlp for Windows, Linux, and macOS (x64 and arm64).

Puts them in discord_video_stream/bin/ under corresponding directories:
  - windows-x64
  - linux-x64
  - linux-arm64
  - macos-x64
  - macos-arm64
"""

import os
import urllib.request
import zipfile
import tarfile
import shutil
import tempfile
import sys

# Standard user-agent to avoid 403 blocks from GitHub and Martin Riedl's server
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Setup directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(BASE_DIR, "discord_video_stream", "bin")

PLATFORMS = {
    "windows-x64": {
        "ffmpeg": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "ffmpeg_filename": "ffmpeg.exe",
        "ffmpeg_archive_type": "zip",
        "ytdlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
        "ytdlp_filename": "yt-dlp.exe",
    },
    "linux-x64": {
        "ffmpeg": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "ffmpeg_filename": "ffmpeg",
        "ffmpeg_archive_type": "tar.xz",
        "ytdlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
        "ytdlp_filename": "yt-dlp",
    },
    "linux-arm64": {
        "ffmpeg": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
        "ffmpeg_filename": "ffmpeg",
        "ffmpeg_archive_type": "tar.xz",
        "ytdlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64",
        "ytdlp_filename": "yt-dlp",
    },
    "macos-x64": {
        "ffmpeg": "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip",
        "ffmpeg_filename": "ffmpeg",
        "ffmpeg_archive_type": "zip",
        "ytdlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
        "ytdlp_filename": "yt-dlp",
    },
    "macos-arm64": {
        "ffmpeg": "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip",
        "ffmpeg_filename": "ffmpeg",
        "ffmpeg_archive_type": "zip",
        "ytdlp": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
        "ytdlp_filename": "yt-dlp",
    },
}


def download_file(url: str, dest_path: str):
    """Download a file with custom headers."""
    print(f"Downloading: {url} -> {dest_path}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as response, open(dest_path, "wb") as out_file:
        shutil.copyfileobj(response, out_file)


def extract_ffmpeg(archive_path: str, dest_path: str, archive_type: str, target_filename: str):
    """Extract ffmpeg from the downloaded zip or tar.xz archive."""
    print(f"Extracting ffmpeg from {archive_path}...")
    if archive_type == "zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            for file_info in zip_ref.infolist():
                if os.path.basename(file_info.filename) == target_filename:
                    print(f"Found {file_info.filename} in zip, extracting...")
                    with zip_ref.open(file_info) as source, open(dest_path, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                    return True
    elif archive_type == "tar.xz":
        with tarfile.open(archive_path, "r:xz") as tar_ref:
            for member in tar_ref.getmembers():
                if os.path.basename(member.name) == target_filename and member.isfile():
                    print(f"Found {member.name} in tar.xz, extracting...")
                    source = tar_ref.extractfile(member)
                    if source:
                        with open(dest_path, "wb") as dest:
                            shutil.copyfileobj(source, dest)
                        return True
    return False


def main():
    os.makedirs(BIN_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp()
    try:
        for platform_name, config in PLATFORMS.items():
            print(f"\n=== Processing platform: {platform_name} ===")
            platform_dir = os.path.join(BIN_DIR, platform_name)
            os.makedirs(platform_dir, exist_ok=True)

            # --- Process FFmpeg ---
            ffmpeg_dest = os.path.join(platform_dir, config["ffmpeg_filename"])
            ffmpeg_url = config["ffmpeg"]
            archive_ext = ".zip" if config["ffmpeg_archive_type"] == "zip" else ".tar.xz"
            temp_archive = os.path.join(temp_dir, f"ffmpeg_{platform_name}{archive_ext}")

            try:
                download_file(ffmpeg_url, temp_archive)
                success = extract_ffmpeg(
                    temp_archive,
                    ffmpeg_dest,
                    config["ffmpeg_archive_type"],
                    config["ffmpeg_filename"],
                )
                if success:
                    print(f"Successfully saved FFmpeg to: {ffmpeg_dest}")
                    if platform_name != "windows-x64":
                        os.chmod(ffmpeg_dest, 0o755)
                else:
                    print(f"Error: Could not find ffmpeg in archive for {platform_name}")
            except Exception as e:
                print(f"Failed to process FFmpeg for {platform_name}: {e}")

            # --- Process yt-dlp ---
            ytdlp_dest = os.path.join(platform_dir, config["ytdlp_filename"])
            ytdlp_url = config["ytdlp"]

            try:
                download_file(ytdlp_url, ytdlp_dest)
                print(f"Successfully saved yt-dlp to: {ytdlp_dest}")
                if platform_name != "windows-x64":
                    os.chmod(ytdlp_dest, 0o755)
            except Exception as e:
                print(f"Failed to download yt-dlp for {platform_name}: {e}")

    finally:
        shutil.rmtree(temp_dir)
        print("\n=== Done! ===")


if __name__ == "__main__":
    main()
