import os
import json
import pytz
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN が .env に設定されていません")

STARTUP_CHANNEL_ID = int(os.getenv("STARTUP_CHANNEL_ID"))
BASE_CHANNEL_ID = int(os.getenv("BASE_CHANNEL_ID"))

JST = ZoneInfo("Asia/Tokyo")
DATA_FILE = Path(__file__).with_name("run_records.json")
RUN_BUTTON_TIMEOUT_SECONDS = 10 * 60
WEEKLY_REPORT_TIME = time(hour=20, minute=0, tzinfo=JST)

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)


def load_run_records():
    if not DATA_FILE.exists():
        return {"daily_runs": {}, "weekly_reports": []}

    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data.setdefault("daily_runs", {})
    data.setdefault("weekly_reports", [])
    return data


def save_run_records(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_key():
    return datetime.now(JST).date().isoformat()


class RunButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=RUN_BUTTON_TIMEOUT_SECONDS)
        self.message = None

    @discord.ui.button(label="走る", style=discord.ButtonStyle.primary)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_run_records()
        date_key = today_key()
        user_id = str(interaction.user.id)
        today_runners = data["daily_runs"].setdefault(date_key, [])

        if user_id in today_runners:
            await interaction.response.send_message(
                "もう記録済みよ。継続する姿勢は悪くないわね！",
                ephemeral=True,
            )
            return

        today_runners.append(user_id)
        save_run_records(data)

        await interaction.response.send_message(
            "記録したわ！　その調子で行くわよ！",
            ephemeral=True,
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@bot.event
async def on_ready():
    jst = pytz.timezone("Asia/Tokyo")
    current_time = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

    print(f"{bot.user.name}が起動しました。")
    print(f"起動時間：{current_time}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 個を同期しました")
    except Exception as e:
        print(f"同期エラー: {e}")

    embed = discord.Embed(
        title = "Seirios_bot",
        description = f"未来のトップアイドル、花海咲季よ！\nbot起動時間：{current_time}",
        color = discord.Color.pink()
    )
    
    await STARTUP_CHANNEL_ID.send (embed=embed)


@tasks.loop(time=time(hour=4, minute=0, tzinfo=JST))
async def send_morning_message():
    channel = bot.get_channel(BASE_CHANNEL_ID)

    if channel is None:
        print("朝4時メッセージ用のチャンネルが見つかりませんでした")
        return

    view = RunButtonView()
    view.message = await channel.send(
        "朝4時よ！　これから走りに出るんでしょ？\n10分以内に「走る」を押した人を記録するわ！",
        view=view,
    )


@tasks.loop(time=WEEKLY_REPORT_TIME)
async def send_weekly_report():
    now = datetime.now(JST)
    if now.weekday() != 6:
        return

    data = load_run_records()
    iso_year, iso_week, _ = now.isocalendar()
    report_key = f"{iso_year}-W{iso_week:02d}"

    if report_key in data["weekly_reports"]:
        return

    weekly_counts = Counter()
    for date_text, user_ids in data["daily_runs"].items():
        run_date = datetime.fromisoformat(date_text).date()
        run_year, run_week, _ = run_date.isocalendar()
        if run_year == iso_year and run_week == iso_week:
            weekly_counts.update(user_ids)

    channel = bot.get_channel(BASE_CHANNEL_ID)
    if channel is None:
        print("週間レポート用のチャンネルが見つかりませんでした")
        return

    if not weekly_counts:
        await channel.send("今週はまだ誰も走ってないみたいね。来週こそ、気合い入れていくわよ！")
    else:
        max_count = max(weekly_counts.values())
        top_runner_ids = [
            user_id for user_id, count in weekly_counts.items() if count == max_count
        ]
        mentions = "、".join(f"<@{user_id}>" for user_id in top_runner_ids)
        await channel.send(
            f"今週一番多く走ったのは {mentions}！\n"
            f"記録は {max_count} 回よ。よくやったわね！"
        )

    data["weekly_reports"].append(report_key)
    save_run_records(data)


bot.run(TOKEN)