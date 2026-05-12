import os
import re
import asyncio
import tempfile
import traceback

import discord
import aiohttp

from discord.ext import commands
from discord import app_commands

# =========================
# opus
# =========================

print("opus loaded:", discord.opus.is_loaded())

# =========================
# 環境変数
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN が設定されていません")

# =========================
# 設定
# =========================

GUILD_ID = 1310885590094450739

# VPS側VOICEVOX
VOICEVOX_URL = "http://160.251.205.11:50021"


MAX_READ_TEXT = 200

# =========================
# intents
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# 正規表現
# =========================

URL_PATTERN = re.compile(r"https?://\S+")
MENTION_PATTERN = re.compile(r"<@!?(\d+)>")
EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
CUSTOM_EMOJI_PATTERN = re.compile(r":[^:\s]+:")
UNICODE_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE
)

# =========================
# 話者一覧
# =========================

VOICE_SPEAKERS = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
}

# =========================
# セッション
# =========================

tts_sessions = {}
user_cooldowns = {}

# =========================
# 話者Select
# =========================

class SpeakerSelect(discord.ui.Select):

    def __init__(self):

        options = [
            discord.SelectOption(
                label=name,
                value=str(speaker_id)
            )
            for name, speaker_id in VOICE_SPEAKERS.items()
        ]

        super().__init__(
            placeholder="話者を選択",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        guild_id = interaction.guild.id

        session = tts_sessions.get(guild_id)

        if not session:
            return await interaction.response.send_message(
                "❌ 読み上げ接続されていません。",
                ephemeral=True
            )

        session["speaker"] = int(self.values[0])

        speaker_name = next(
            k for k, v in VOICE_SPEAKERS.items()
            if v == int(self.values[0])
        )

        await interaction.response.send_message(
            f"✅ 話者を「{speaker_name}」へ変更しました。",
            ephemeral=True
        )

class SpeakerView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=60)

        self.add_item(SpeakerSelect())

# =========================
# テキスト整形
# =========================

def sanitize_text(text: str):

    text = URL_PATTERN.sub("URL省略", text)

    text = MENTION_PATTERN.sub("メンション", text)

    text = EMOJI_PATTERN.sub("", text)

    text = CUSTOM_EMOJI_PATTERN.sub("", text)

    text = UNICODE_EMOJI_PATTERN.sub("", text)

    text = text.replace("\n", " ")

    text = text.strip()

    if len(text) > MAX_READ_TEXT:
        text = text[:MAX_READ_TEXT] + "、以下略"

    return text

# =========================
# VOICEVOX生成
# =========================

async def generate_tts(
    text: str,
    speaker: int
):

    print(
        f"[VOICEVOX REQUEST] "
        f"text={text} "
        f"speaker={speaker}"
    )

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".wav"
    )

    path = temp_file.name
    temp_file.close()

    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        # audio_query
        async with session.post(
            f"{VOICEVOX_URL}/audio_query",
            params={
                "text": text,
                "speaker": speaker
            }
        ) as r:

            print(
                f"[VOICEVOX audio_query] "
                f"status={r.status}"
            )

            query = await r.json()

        # synthesis
        async with session.post(
            f"{VOICEVOX_URL}/synthesis",
            params={
                "speaker": speaker
            },
            json=query
        ) as r:

            print(
                f"[VOICEVOX synthesis] "
                f"status={r.status}"
            )

            audio = await r.read()

    with open(path, "wb") as f:
        f.write(audio)

    print(
        f"[VOICE FILE SAVED] "
        f"{path}"
    )

    return path

# =========================
# キュー処理
# =========================

async def process_queue(guild_id: int):

    while True:

        session = tts_sessions.get(guild_id)

        if not session:
            return

        queue: asyncio.Queue = session["queue"]

        vc: discord.VoiceClient = session["voice_client"]

        speaker = session["speaker"]

        try:
            text = await queue.get()

        except asyncio.CancelledError:
            break

        if not vc.is_connected():
            break

        try:

            print(f"[VOICEVOX GENERATE] {text}")

            path = await generate_tts(
                text,
                speaker
            )

            finished = asyncio.Event()

            def after_play(error):

                if error:
                    print("[VOICE PLAY ERROR]", error)

                print("[VOICE PLAY END]")

                try:
                    os.remove(path)
                except:
                    pass

                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(finished.set)

            source = discord.FFmpegPCMAudio(path)

            print("[VOICE PLAY START]")

            vc.play(source, after=after_play)

            await asyncio.wait_for(
                finished.wait(),
                timeout=60
            )

        except Exception:

            print("[VOICE ERROR]")
            traceback.print_exc()

# =========================
# /接続
# =========================

@bot.tree.command(
    name="接続",
    guild=discord.Object(id=GUILD_ID)
)
async def connect(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    if not interaction.user.voice:

        return await interaction.followup.send(
            "❌ VCへ参加してください。",
            ephemeral=True
        )

    target_channel = interaction.user.voice.channel

    guild_id = interaction.guild.id

    if guild_id in tts_sessions:

        return await interaction.followup.send(
            "⚠️ すでに接続中です。",
            ephemeral=True
        )

    try:

        queue = asyncio.Queue()

        print("[VOICE CONNECT START]")

        vc = await target_channel.connect(
            timeout=60,
            reconnect=False,
            self_deaf=True
        )

        print("[VOICE CONNECT SUCCESS]")

        tts_sessions[guild_id] = {
            "voice_client": vc,
            "text_channel_id": interaction.channel.id,
            "queue": queue,
            "task": None,
            "speaker": 3,
        }

        task = asyncio.create_task(
            process_queue(guild_id)
        )

        tts_sessions[guild_id]["task"] = task

        await interaction.followup.send(
            f"✅ {target_channel.mention} に接続しました。",
            ephemeral=True
        )

    except Exception as e:

        print("[CONNECT ERROR]")
        traceback.print_exc()

        tts_sessions.pop(guild_id, None)

        try:
            await interaction.followup.send(
                f"❌ 接続失敗\n{e}",
                ephemeral=True
            )
        except:
            pass

# =========================
# /切断
# =========================

@bot.tree.command(
    name="切断",
    guild=discord.Object(id=GUILD_ID)
)
async def disconnect(interaction: discord.Interaction):

    guild_id = interaction.guild.id

    session = tts_sessions.get(guild_id)

    if not session:
        return await interaction.response.send_message(
            "❌ 接続されていません。",
            ephemeral=True
        )

    try:
        session["task"].cancel()
    except:
        pass

    try:
        await session["voice_client"].disconnect(force=True)
    except:
        pass

    tts_sessions.pop(guild_id, None)

    await interaction.response.send_message(
        "👋 切断しました。",
        ephemeral=True
    )

# =========================
# /話者変更
# =========================

@bot.tree.command(
    name="話者変更",
    guild=discord.Object(id=GUILD_ID)
)
async def speaker_change(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🎤 話者を選択してください",
        view=SpeakerView(),
        ephemeral=True
    )

# =========================
# メッセージ読み上げ
# =========================

@bot.event
async def on_message(message: discord.Message):

    if message.author.bot:
        return

    if not message.guild:
        return

    guild_id = message.guild.id

    session = tts_sessions.get(guild_id)

    if not session:
        return

    if message.channel.id != session["text_channel_id"]:
        return

    now = asyncio.get_event_loop().time()

    last = user_cooldowns.get(message.author.id, 0)

    if now - last < 2:
        return

    user_cooldowns[message.author.id] = now

    text = sanitize_text(message.content)

    if not text:
        return

    print(f"[QUEUE PUT] {text}")

    await session["queue"].put(text)

# =========================
# VC退出検知
# =========================

@bot.event
async def on_voice_state_update(
    member,
    before,
    after
):

    if member.bot:
        return

    guild_id = member.guild.id

    session = tts_sessions.get(guild_id)

    if not session:
        return

    vc = session["voice_client"]

    if not vc:
        return

    humans = [
        m for m in vc.channel.members
        if not m.bot
    ]

    if len(humans) == 0:

        print("[VOICE AUTO DISCONNECT]")

        try:
            session["task"].cancel()
        except:
            pass

        try:
            await vc.disconnect(force=True)
        except:
            pass

        tts_sessions.pop(guild_id, None)

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"ログイン完了: {bot.user}")

    guild_obj = discord.Object(id=GUILD_ID)

    synced = await bot.tree.sync(
        guild=guild_obj
    )

    print(f"[SYNC OK] {len(synced)} commands")

# =========================
# 起動
# =========================

bot.run(TOKEN)
