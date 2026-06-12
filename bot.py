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
from discord.ui import View, Button

JST = ZoneInfo("Asia/Tokyo")

load_dotenv()

ADMIN_ROLE_IDS = [
    1310906528517062770,
    1477647786135650387,
]
LIFE_BASE_URL = "https://jinseigame-production.up.railway.app"
API_BASE_URL = "https://yomiage-production.up.railway.app"

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

        # =========================
        # 人生パネル復元
        # =========================

        print("人生パネル復元")

        rows = await self.db.fetch("""

        SELECT *
        FROM life_panels

        """)

        for row in rows:

            self.add_view(
                LifeLinkView(
                    self,
                    row["room_id"]
                )
            )

            print(
               f"復元: {row['room_id']}"
            )

        # =========================
        # スラッシュ同期
        # =========================

        print("スラッシュ同期")

        await self.tree.sync()

        asyncio.create_task(
            self.start_api()
        )

    async def start_api(self):

        port = int(
            os.getenv("PORT", 8080)
        )

        print(f"API起動 PORT={port}")

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )

        server = uvicorn.Server(config)

        await server.serve()


bot = LifeBot()


def generate_room_id():

    return secrets.token_hex(3).upper()

def generate_session_token():

    return secrets.token_urlsafe(32)

def generate_board_tiles():

    prizes = [
        "思い出photo or イタズラ落書き 半額",
        "ボトルⓜⓔⓝⓤ無料",
        "特別席無料",
        "指名料無料",
    ]

    menus = [
        "語尾もふもふ",
        "叱咤激励",
        "セリフ読み",
        "甘えん坊",
        "ぷんぷん",
        "愛の告白",
        "イベント特典画像プレゼント",
        "イベントカードプレゼント",
        "オリシャンプレゼン",
        
    ]

    bads = [
        "1マス進む",
        "2マス戻る",
        "🎲1回休み",
        "語尾にゃんでお話する",
        "ドリンクを1つ頼む",
        "大好き〜と叫ぶ",
    ]

    tiles = []

    tiles.append({
        "type": "start",
        "text": "スタート"
    })

    import random

    for i in range(98):

        r = random.randint(1, 4)

        if r == 1:

            tiles.append({
                "type": "menu",
                "text": random.choice(menus)
            })

        elif r == 2:

            tiles.append({
                "type": "prize",
                "text": random.choice(prizes)
            })

        elif r == 3:

            tiles.append({
                "type": "bad",
                "text": random.choice(bads)
            })

        else:

            tiles.append({
                "type": "empty",
                "text": "何もなし"
            })

    tiles.append({
        "type": "goal",
        "text": "ゴール"
    })

    return tiles

class LifeLinkView(View):

    def __init__(self, bot, room_id):

        super().__init__(timeout=None)

        self.bot = bot
        self.room_id = room_id

        button = Button(
            label="🎲 人生ゲームサイト",
            style=discord.ButtonStyle.green,
            custom_id=f"life:open:{room_id}"
        )

        button.callback = self.open_life

        self.add_item(button)

    async def open_life(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        session_token = generate_session_token()

        await self.bot.db.execute("""

        INSERT INTO life_sessions (
            session_token,
            user_id,
            guild_id
        )

        VALUES ($1, $2, $3)

        """,

            session_token,
            str(interaction.user.id),
            str(interaction.guild.id)

        )

        url = (
            f"{LIFE_BASE_URL}"
            f"?room={self.room_id}"
            f"&session={session_token}"
        )

        await interaction.followup.send(
            f"🎲 人生ゲームはこちら\n{url}",
            ephemeral=True
        )


def has_admin_role(member):

    return any(
        role.id in ADMIN_ROLE_IDS
        for role in member.roles
    )


@bot.event
async def on_ready():

    print(f"ログイン: {bot.user}")


# =========================
# 人生ゲームサイコロ付与
# =========================

@bot.tree.command(
    name="人生ゲームサイコロ付与",
    description="最新の人生ゲームにサイコロを1個付与"
)
async def add_life_dice(
    interaction: discord.Interaction,
    user: discord.Member
):

    if not has_admin_role(interaction.user):

        await interaction.response.send_message(
            "権限がありません",
            ephemeral=True
        )
        return

    latest_room = await bot.db.fetchrow("""

    SELECT room_id
    FROM life_rooms
    ORDER BY created_at DESC
    LIMIT 1

    """)

    if not latest_room:

        await interaction.response.send_message(
            "人生ゲームのパネルがまだ生成されていません。",
            ephemeral=True
        )
        return

    room_id = latest_room["room_id"]

    progress = await bot.db.fetchrow("""

    SELECT dice_count
    FROM life_user_progress
    WHERE user_id = $1
    AND room_id = $2

    """,
        str(user.id),
        room_id
    )

    if progress and progress["dice_count"] >= 1:

        await interaction.response.send_message(
            f"{user.mention} はサイコロをすでに1個持ってます。"
        )
        return

    await bot.db.execute("""

    INSERT INTO life_user_progress (
        user_id,
        room_id,
        dice_count,
        position
    )

    VALUES ($1, $2, 2, 0)

    ON CONFLICT (user_id, room_id)

    DO UPDATE SET
        dice_count = 2,
        updated_at = NOW()

    """,
        str(user.id),
        room_id
    )

    await bot.db.execute("""

    INSERT INTO life_history (
        user_id,
        room_id,
        action_type,
        message,
        memo
    )

    VALUES ($1, $2, $3, $4, $5)

    """,
        str(user.id),
        room_id,
        "dice_add",
        "サイコロ 2個付与",
        None
    )

    await interaction.response.send_message(
        f"{user.mention} にサイコロを2個付与しました。"
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

    # =========================
    # 前回データ削除
    # =========================

    await bot.db.execute("""
    DELETE FROM life_history
    """)

    await bot.db.execute("""
    DELETE FROM life_user_progress
    """)

    await bot.db.execute("""
    DELETE FROM life_tiles
    """)

    await bot.db.execute("""
    DELETE FROM life_rooms
    """)

    await bot.db.execute("""
    DELETE FROM life_panels
    """)

    room_id = generate_room_id()
    tiles = generate_board_tiles()

    for i, tile in enumerate(tiles):
        await bot.db.execute("""
        INSERT INTO life_tiles (
            room_id,
            tile_index,
            tile_type,
            tile_text
        )
        VALUES ($1, $2, $3, $4)
        """,
            room_id,
            i,
            tile["type"],
            tile["text"]
        )

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
    await bot.db.execute("""

    INSERT INTO life_panels (

        room_id

    )

    VALUES ($1)

    ON CONFLICT DO NOTHING

    """,

        room_id
    )



    embed = discord.Embed(
        title="🎲 人生ゲーム",
        description=description,
        color=0xffd54f
    )

    embed.add_field(
        name="タイトル",
        value=title,
        inline=False
    )

    embed.add_field(
        name="ROOM ID",
        value=room_id,
        inline=False
    )

    view = LifeLinkView(bot, room_id)

    bot.add_view(view)

    await interaction.response.send_message(
       embed=embed,
        view=view
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

    latest_room = await bot.db.fetchrow("""

    SELECT room_id
    FROM life_rooms
    ORDER BY created_at DESC
    LIMIT 1

    """)

    if not latest_room:

        await interaction.response.send_message(
            "人生ゲームが開始されていません。"
        )
        return

    room_id = latest_room["room_id"]

    progress = await bot.db.fetchrow("""

    SELECT dice_count
    FROM life_user_progress
    WHERE user_id = $1
    AND room_id = $2

    """,

        str(user.id),
        room_id
    )

    dice_count = 0

    if progress:
        dice_count = progress["dice_count"]

    rows = await bot.db.fetch("""

    SELECT *
    FROM life_history
    WHERE user_id = $1
    AND room_id = $2
    ORDER BY created_at DESC
    LIMIT 10

    """,

        str(user.id),
        room_id
    )

    text = (
        f"🎲現在のサイコロ所持数: "
        f"{dice_count}\n\n"
    )

    if not rows:

        text += "履歴なし"

        await interaction.response.send_message(
            text
        )
        return

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
            text += (
                f"メモ: {row['memo']}\n"
            )

        text += "\n"

    await interaction.response.send_message(
        text
    )


bot.run(
    os.getenv("DISCORD_TOKEN")
)
