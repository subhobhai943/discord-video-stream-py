"""Minimal example: stream a local file or online URL.

Usage::

    DISCORD_TOKEN=xxx GUILD_ID=yyy CHANNEL_ID=zzz python examples/stream_file.py

Optionally set VIDEO_FILE to a local path or a YouTube/Twitch URL.
"""

import asyncio
import os

import discord
from discord_video_stream import Streamer, VideoPlayer

async def main():
    token = os.environ["DISCORD_TOKEN"]
    guild_id = int(os.environ["GUILD_ID"])
    channel_id = int(os.environ["CHANNEL_ID"])
    source = os.environ.get("VIDEO_FILE", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    client = discord.Client()
    streamer = Streamer(client)

    @client.event
    async def on_ready():
        await streamer.join_voice(guild_id=guild_id, channel_id=channel_id)
        udp = await streamer.create_stream()
        player = VideoPlayer(source, udp)
        await player.play()
        await streamer.stop_stream()
        await client.close()

    await client.start(token)

asyncio.run(main())
