"""Example: a simple Discord bot that streams a local video file to a voice channel.

This is a selfbot example using discord.py-self.

Usage::

    python examples/movie_bot.py

Requires:
    - ffmpeg installed and in PATH
    - pip install discord-video-stream-py
    - A valid Discord user token (set as DISCORD_TOKEN env variable)
    - GUILD_ID and CHANNEL_ID set as env variables

WARNING: Selfbots violate Discord’s Terms of Service. Use only for testing
on private servers or with accounts you own. This example is for educational
purposes only.
"""

import asyncio
import os

import discord
from discord_video_stream import Streamer, VideoPlayer

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
VIDEO_FILE = os.environ.get("VIDEO_FILE", "movie.mp4")

client = discord.Client()
streamer = Streamer(client)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")

    print(f"Joining voice channel {CHANNEL_ID} in guild {GUILD_ID}...")
    await streamer.join_voice(guild_id=GUILD_ID, channel_id=CHANNEL_ID)

    print("Creating Go Live stream (720p, 30fps, H264)...")
    udp = await streamer.create_stream(resolution="720p", fps=30, codec="h264")

    player = VideoPlayer(VIDEO_FILE, udp, resolution="720p", fps=30)

    @player.on("start")
    async def on_start():
        print(f"Streaming {VIDEO_FILE}...")

    @player.on("finish")
    async def on_finish():
        print("Stream finished.")
        await streamer.stop_stream()
        await client.close()

    @player.on("error")
    async def on_error(exc):
        print(f"Stream error: {exc}")
        await streamer.stop_stream()
        await client.close()

    await player.play()


client.run(TOKEN)
