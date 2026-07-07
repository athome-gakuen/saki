import os
import json
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
RUN_BUTTON_TIMEOUT_SECONDS = 30 * 60
DAILY_RANKING_TIME = time(hour=8, minute=0, tzinfo=JST)
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


def daily_run_user_id(record):
    if isinstance(record, dict):
        return record.get("user_id")
    return record


def daily_run_pressed_at(record):
    if not isinstance(record, dict):
        return None

    pressed_at = record.get("pressed_at")
    if pressed_at is None:
        return None

    try:
        parsed_at = datetime.fromisoformat(pressed_at)
    except ValueError:
        return None

    if parsed_at.tzinfo is None:
        return parsed_at.replace(tzinfo=JST)
    return parsed_at


def daily_run_pressed_time_text(record):
    pressed_at = daily_run_pressed_at(record)
    if pressed_at is None:
        return "時刻不明"
    return pressed_at.astimezone(JST).strftime("%H:%M:%S")


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
        recorded_user_ids = {daily_run_user_id(record) for record in today_runners}

        if user_id in recorded_user_ids:
            await interaction.response.send_message(
                "もう記録済みよ。継続する姿勢は悪くないわね！",
                ephemeral=True,
            )
            return

        today_runners.append(
            {
                "user_id": user_id,
                "pressed_at": datetime.now(JST).isoformat(),
            }
        )
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
    current_time = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

    print(f"{bot.user.name}が起動しました。")
    print(f"起動時間：{current_time}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 個を同期しました")
    except Exception as e:
        print(f"同期エラー: {e}")

    embed = discord.Embed(
    title="saki",
    description=f"bot起動時間：{current_time}",
    color=discord.Color.red(),
)

    channel = bot.get_channel(STARTUP_CHANNEL_ID)
    if channel is not None:
        await channel.send(
            content="未来のトップアイドル、花海咲季よ！",
            embed=embed,
        )
    else:
        print("起動通知用のチャンネルが見つかりませんでした")

    if not send_morning_message.is_running():
        send_morning_message.start()

    if not send_weekly_report.is_running():
        send_weekly_report.start()

    if not send_daily_ranking.is_running():
        send_daily_ranking.start()


@tasks.loop(time=time(hour=4, minute=0, tzinfo=JST))
async def send_morning_message():
    channel = bot.get_channel(BASE_CHANNEL_ID)

    if channel is None:
        print("朝4時メッセージ用のチャンネルが見つかりませんでした")
        return

    view = RunButtonView()
    view.message = await channel.send(
        "朝4時よ！　これから走りに出るんでしょ？\n30分以内に「走る」を押した人を記録するわ！",
        view=view,
    )


@tasks.loop(time=DAILY_RANKING_TIME)
async def send_daily_ranking():
    date_key = today_key()
    data = load_run_records()
    today_runners = data["daily_runs"].get(date_key, [])

    channel = bot.get_channel(BASE_CHANNEL_ID)
    if channel is None:
        print("朝8時ランキング用のチャンネルが見つかりませんでした")
        return

    ranking_records = [
        record
        for record in today_runners
        if daily_run_user_id(record) is not None
    ]

    if not ranking_records:
        await channel.send(
            "今朝はまだ誰も押せてないみたいね。そういう日もあるわ。明日は切り替えていくわよ！"
        )
        return

    ranking_records.sort(
        key=lambda record: daily_run_pressed_at(record) or datetime.max.replace(tzinfo=JST)
    )

    ranking_lines = [
        f"{index}位：<@{daily_run_user_id(record)}>（{daily_run_pressed_time_text(record)}）"
        for index, record in enumerate(ranking_records, start=1)
    ]
    await channel.send(
        "今朝の「走る」ランキングよ！\n"
        + "\n".join(ranking_lines)
        + "\n速く動けたの、悪くないわね！"
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
            weekly_counts.update(
                user_id
                for user_id in (daily_run_user_id(record) for record in user_ids)
                if user_id is not None
            )

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
