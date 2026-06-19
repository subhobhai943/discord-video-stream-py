\"\"\"Example: a standard Discord Bot (using a Bot Token) that streams a local video file.

This example runs with a standard bot token and standard discord.py library.
It utilizes the new VoiceStreamClient for voice channel video and audio streaming.

Usage::

    DISCORD_TOKEN=your_bot_token GUILD_ID=123 CHANNEL_ID=456 VIDEO_FILE=movie.mp4 python examples/bot_token_example.py

Requires:
    - ffmpeg installed and in PATH
    - pip install discord.py discord-video-stream-py
    - A valid Discord Bot Token
\"\"\"

import asyncio
import os
import discord
from discord.ext import commands
from discord_video_stream import VoiceStreamClient, VideoPlayer

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
VIDEO_FILE = os.environ.get("VIDEO_FILE", "movie.mp4")

# Standard bots require voice_states intent to connect to voice channels and receive voice updates
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"Guild {GUILD_ID} not found. Make sure the bot is invited to it.")
        await bot.close()
        return
        
    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Channel {CHANNEL_ID} not found in guild {guild.name}.")
        await bot.close()
        return

    print(f"Connecting to voice channel {channel.name} in guild {guild.name} using VoiceStreamClient...")
    try:
        # Connect to voice using VoiceStreamClient as the custom voice client class
        voice_client = await channel.connect(cls=VoiceStreamClient)
        print("Connected! Handshaking Go Live stream (720p, 30fps, H264)...")
        
        udp = await voice_client.create_stream(resolution="720p", fps=30, codec="h264")
        
        player = VideoPlayer(VIDEO_FILE, udp, resolution="720p", fps=30)
        
        @player.on("start")
        async def on_start():
            print(f"Streaming {VIDEO_FILE}...")

        @player.on("finish")
        async def on_finish():
            print("Stream finished. Disconnecting...")
            await voice_client.disconnect()
            await bot.close()

        @player.on("error")
        async def on_error(exc):
            print(f"Stream error: {exc}. Disconnecting...")
            await voice_client.disconnect()
            await bot.close()

        await player.play()
        
    except Exception as e:
        print(f"An error occurred: {e}")
        await bot.close()

if __name__ == "__main__":
    bot.run(TOKEN)
