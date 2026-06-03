import os
import asyncio
import discord
import uvicorn
import secrets

from discord.ext import commands
from discord import app_commands

from dotenv import load_dotenv

from db import Database
from api import app

from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

load_dotenv()

ADMIN_ROLE_IDS = [
    1310906528517062770
]

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


class LifeBot(commands.Bot):

    def __init__(self):

        super().__init__(
            command_prefix="!",
            intents=intents
        )

        self.db = Database()

    async def setup_hook(self):

        print("DB接続")
        await self.db.connect()

        print("DB初期化")
        await self.db.init_db()

        print("スラッシュ同期")
        await self.tree.sync()

        asyncio.create_task(
            self.start_api()
        )

    async def start_api(self):

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )

        server = uvicorn.Server(config)

        await server.serve()


bot = LifeBot()


def generate_room_id():

    return secrets.token_hex(3).upper()


def has_admin_role(member):

    return any(
        role.id in ADMIN_ROLE_IDS
        for role in member.roles
    )


@bot.event
async def on_ready():

    print(f"ログイン: {bot.user}")


# =========================
# サイコロ付与
# =========================

@bot.tree.command(
    name="サイコロ付与",
    description="サイコロを付与"
)
async def add_dice(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int,
    memo: str = None
):

    if not has_admin_role(interaction.user):

        await interaction.response.send_message(
            "権限がありません",
            ephemeral=True
        )
        return

    await bot.db.execute("""

    INSERT INTO life_users (
        user_id,
        dice_count
    )

    VALUES ($1, $2)

    ON CONFLICT (user_id)

    DO UPDATE SET
    dice_count = life_users.dice_count + $2

    """,

        str(user.id),
        amount
    )

    await bot.db.execute("""

    INSERT INTO life_history (

        user_id,
        action_type,
        message,
        memo

    )

    VALUES ($1, $2, $3, $4)

    """,

        str(user.id),
        "dice_add",
        f"サイコロ {amount}個付与",
        memo
    )

    await interaction.response.send_message(

        f"{user.mention} に "
        f"サイコロ {amount}個付与しました"

    )


# =========================
# 人生パネル生成
# =========================

@bot.tree.command(
    name="人生パネル生成",
    description="人生ゲームパネル生成"
)
async def create_panel(
    interaction: discord.Interaction,
    title: str,
    description: str
):

    if not has_admin_role(interaction.user):

        await interaction.response.send_message(
            "権限がありません",
            ephemeral=True
        )
        return

    row = await bot.db.fetchrow("""
    room_id = generate_room_id()
    await bot.db.execute("""
    INSERT INTO life_rooms (
        room_id,
        title,
        description,
        created_by
    )
    VALUES ($1, $2, $3, $4)
    """,
        room_id,
        title,
        description,
        str(interaction.user.id)
    )
    site_url = (
        f"https://YOUR_SITE_URL/life/{room_id}"
    )
    await interaction.response.send_message(
        f"🎲 人生ゲームパネル生成完了\n\n"
        f"タイトル: {title}\n"
        f"ROOM ID: {room_id}\n\n"
        f"{site_url}"
    )


# =========================
# 履歴確認
# =========================

@bot.tree.command(
    name="人生ゲーム履歴確認",
    description="履歴確認"
)
async def history(
    interaction: discord.Interaction,
    user: discord.Member
):

    if not has_admin_role(interaction.user):

        await interaction.response.send_message(
            "権限がありません",
            ephemeral=True
        )
        return

    rows = await bot.db.fetch("""

    SELECT *
    FROM life_history
    WHERE user_id = $1
    ORDER BY created_at DESC
    LIMIT 10

    """,

        str(user.id)
    )

    if not rows:

        await interaction.response.send_message(
            "履歴なし"
        )
        return

    text = ""

    for row in rows:

        jst_time = row["created_at"].astimezone(JST)

        time_str = jst_time.strftime(
            "%m/%d %H:%M"
        )

        text += (
            f"{time_str}\n"
            f"{row['message']}\n"
        )

        if row["memo"]:
            text += f"メモ: {row['memo']}\n"

        text += "\n"

    await interaction.response.send_message(text)


bot.run(
    os.getenv("DISCORD_TOKEN")
)
