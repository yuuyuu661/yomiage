import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import tempfile
import os
import re
import aiohttp

# =========================
# 設定
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1310885590094450739

# Railway internal URL 推奨
VOICEVOX_URL = "http://voicevox_engine.railway.internal:50021"

MAX_READ_TEXT = 200

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.message_content = True
intents.messages = True

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
# セッション
# =========================

tts_sessions = {}

user_cooldowns = {}

# =========================
# 話者一覧
# =========================

VOICE_SPEAKERS = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
}

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

            query = await r.json()

        # synthesis
        async with session.post(
            f"{VOICEVOX_URL}/synthesis",
            params={
                "speaker": speaker
            },
            json=query
        ) as r:

            audio = await r.read()

    with open(path, "wb") as f:
        f.write(audio)

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

        if not vc:

            await asyncio.sleep(1)
            continue

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

                try:
                    os.remove(path)
                except:
                    pass

                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(finished.set)

            source = discord.FFmpegPCMAudio(path)

            vc.play(source, after=after_play)

            await asyncio.wait_for(
                finished.wait(),
                timeout=60
            )

        except Exception as e:

            print("[VOICE ERROR]", e)

# =========================
# 話者変更Select
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
# 移動確認View
# =========================

class MoveConfirmView(discord.ui.View):

    def __init__(self, target_channel):
        super().__init__(timeout=30)

        self.target_channel = target_channel

    @discord.ui.button(label="移動", style=discord.ButtonStyle.green)
    async def move_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild_id = interaction.guild.id

        session = tts_sessions.get(guild_id)

        if not session:
            return await interaction.response.edit_message(
                content="❌ 接続情報が見つかりません。",
                view=None
            )

        vc: discord.VoiceClient = session["voice_client"]

        await vc.move_to(self.target_channel)

        session["text_channel_id"] = interaction.channel.id

        await interaction.response.edit_message(
            content=f"✅ {self.target_channel.mention} に移動しました。",
            view=None
        )

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.gray)
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="キャンセルしました。",
            view=None
        )

# =========================
# /接続
# =========================

@bot.tree.command(name="接続")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def connect(interaction: discord.Interaction):

    # ← 超重要
    await interaction.response.defer(ephemeral=True)

    if interaction.guild.id != GUILD_ID:
        return

    if not interaction.user.voice:

        return await interaction.followup.send(
            "❌ VCへ参加してください。",
            ephemeral=True
        )

    target_channel = interaction.user.voice.channel

    guild_id = interaction.guild.id

    if guild_id in tts_sessions:

        session = tts_sessions[guild_id]

        vc = session["voice_client"]

        if vc and vc.channel.id != target_channel.id:

            humans = len([
                m for m in vc.channel.members
                if not m.bot
            ])

            embed = discord.Embed(
                title="⚠️ 別VCで読み上げ中",
                description=(
                    f"現在 {vc.channel.mention} で読み上げ中\n"
                    f"人数：{humans}名"
                ),
                color=discord.Color.orange()
            )

            return await interaction.followup.send(
                embed=embed,
                view=MoveConfirmView(target_channel),
                ephemeral=True
            )

        return await interaction.followup.send(
            "⚠️ すでに接続中です。",
            ephemeral=True
        )

    queue = asyncio.Queue()

    tts_sessions[guild_id] = {
        "voice_client": None,
        "text_channel_id": interaction.channel.id,
        "queue": queue,
        "task": None,
        "speaker": 3,
    }

    task = asyncio.create_task(
        process_queue(guild_id)
    )

    tts_sessions[guild_id]["task"] = task

    try:

        vc = await asyncio.wait_for(
            target_channel.connect(
                reconnect=True,
                self_deaf=True
            ),
            timeout=20
        )

        tts_sessions[guild_id]["voice_client"] = vc

        # warmup
        try:

            warmup = await generate_tts(
                "接続しました",
                3
            )

            os.remove(warmup)

            print("[VOICEVOX WARMUP OK]")

        except Exception as e:

            print("[VOICEVOX WARMUP ERROR]", e)

        await interaction.followup.send(
            f"✅ {target_channel.mention} に接続しました。",
            ephemeral=True
        )

    except Exception as e:

        tts_sessions.pop(guild_id, None)

        print("[VOICE CONNECT ERROR]", e)

        await interaction.followup.send(
            f"❌ 接続失敗\n{e}",
            ephemeral=True
        )

# =========================
# /切断
# =========================

@bot.tree.command(name="切断")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def disconnect(interaction: discord.Interaction):

    if interaction.guild.id != GUILD_ID:
        return

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

@bot.tree.command(name="話者変更")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def speaker_change(interaction: discord.Interaction):

    if interaction.guild.id != GUILD_ID:
        return

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

        try:
            session["task"].cancel()
        except:
            pass

        try:
            await vc.disconnect(force=True)
        except:
            pass

        tts_sessions.pop(guild_id, None)

        print(f"[VOICE AUTO DISCONNECT] {guild_id}")

# =========================
# 起動
# =========================

@bot.event
async def on_ready():

    try:

        guild = discord.Object(id=GUILD_ID)

        synced = await bot.tree.sync(guild=guild)

        print(f"Slash Command 同期完了: {len(synced)}")

    except Exception as e:

        print("[SYNC ERROR]", e)

    print(f"ログイン完了: {bot.user}")

bot.run(TOKEN)
