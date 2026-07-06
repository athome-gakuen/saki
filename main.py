import os
from datetime import time
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN が .env に設定されていません")

CHANNEL_ID = int(os.getenv("STARTUP_CHANNEL_ID"))

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        await channel.send("未来のトップアイドル、花海咲季よ！")
    else:
        print("起動通知用のチャンネルが見つかりませんでした")

    if not send_morning_message.is_running():
        send_morning_message.start()


@tasks.loop(time=time(hour=4, minute=0, tzinfo=ZoneInfo("Asia/Tokyo")))
async def send_morning_message():
    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        print("チャンネルが見つかりませんでした")
        return

    await channel.send("朝4時よ！　これから走りに出るんでしょ？")


bot.run(TOKEN)