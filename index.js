const {
    Client,
    GatewayIntentBits,
    SlashCommandBuilder,
    REST,
    Routes,
    Events,
    ActionRowBuilder,
    StringSelectMenuBuilder,
} = require("discord.js");

const {
    StreamType,
} = require("@discordjs/voice");

const {
    joinVoiceChannel,
    createAudioPlayer,
    createAudioResource,
    AudioPlayerStatus,
    NoSubscriberBehavior,
    entersState,
    VoiceConnectionStatus,
} = require("@discordjs/voice");

const axios = require("axios");
const fs = require("fs");
const os = require("os");
const path = require("path");
const ffmpeg = require("ffmpeg-static");
const { spawn } = require("child_process");

const TOKEN = process.env.DISCORD_TOKEN;

const CLIENT_ID = process.env.CLIENT_ID;

const GUILD_ID = "1310885590094450739";

const VOICEVOX_URL = "http://160.251.205.11:50021";

const MAX_READ_TEXT = 200;

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
    ],
});

const sessions = new Map();

const cooldowns = new Map();

const SPEAKERS = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
};

function sanitizeText(text) {

    text = text.replace(/https?:\/\/\S+/g, "URL省略");

    text = text.replace(/<@!?\d+>/g, "メンション");

    text = text.replace(/<a?:\w+:\d+>/g, "");

    text = text.replace(/:[^:\s]+:/g, "");

    text = text.replace(/[\u{1F300}-\u{1FAFF}]/gu, "");

    text = text.replace(/\n/g, " ");

    text = text.trim();

    if (text.length > MAX_READ_TEXT) {
        text = text.slice(0, MAX_READ_TEXT) + "、以下略";
    }

    return text;
}

async function generateTTS(text, speaker) {

    console.log("[VOICEVOX REQUEST]", text);

    // audio_query
    const queryRes = await axios.post(
        `${VOICEVOX_URL}/audio_query`,
        null,
        {
            params: {
                text: text,
                speaker: speaker
            }
        }
    );

    // synthesis
    const synthesisRes = await axios.post(
        `${VOICEVOX_URL}/synthesis`,
        queryRes.data,
        {
            params: {
                speaker: speaker
            },
            responseType: "arraybuffer"
        }
    );

    // wav保存
    const filePath = `/tmp/${Date.now()}.wav`;

    fs.writeFileSync(filePath, synthesisRes.data);

    console.log(
        "[VOICE FILE SIZE]",
        fs.statSync(filePath).size
    );

    return filePath;
}



async function processQueue(guildId) {

    const session = sessions.get(guildId);

    if (!session) return;

    while (true) {

        try {

            const item = session.queue.shift();

            if (!item) {
                await new Promise(r => setTimeout(r, 500));
                continue;
            }

            const wavPath = await generateTTS(
                item,
                session.speaker
            );

            const resource = createAudioResource(
                wavPath,
                {
                    inputType: StreamType.Arbitrary,
                }
            );

            session.player.play(resource);

            await entersState(
                session.player,
                AudioPlayerStatus.Playing,
                10000
            );

            await entersState(
                session.player,
                AudioPlayerStatus.Idle,
                60000
            );

            try {
                fs.unlinkSync(wavPath);
            } catch {}

        } catch (e) {
            console.error("[VOICE ERROR]", e);
        }
    }
}

client.once(Events.ClientReady, async () => {

    console.log(`ログイン完了: ${client.user.tag}`);

    const commands = [

        new SlashCommandBuilder()
            .setName("接続")
            .setDescription("VCへ接続"),

        new SlashCommandBuilder()
            .setName("切断")
            .setDescription("VCから切断"),

        new SlashCommandBuilder()
            .setName("話者変更")
            .setDescription("VOICEVOX話者変更"),
    ];

    const rest = new REST({ version: "10" })
        .setToken(TOKEN);

    await rest.put(
        Routes.applicationGuildCommands(
            CLIENT_ID,
            GUILD_ID
        ),
        {
            body: commands.map(c => c.toJSON()),
        }
    );

    console.log("[SYNC OK]");
});

client.on(Events.InteractionCreate, async interaction => {

    if (interaction.isChatInputCommand()) {

        if (interaction.commandName === "接続") {

            await interaction.deferReply({
                ephemeral: true,
            });

            const member = interaction.member;

            if (!member.voice.channel) {
                return interaction.editReply(
                    "❌ VCへ参加してください。"
                );
            }

            const guildId = interaction.guild.id;

            if (sessions.has(guildId)) {
                return interaction.editReply(
                    "⚠️ すでに接続中です。"
                );
            }

            try {

                console.log("[VOICE CONNECT START]");

                const connection = joinVoiceChannel({
                    channelId: member.voice.channel.id,
                    guildId: guildId,
                    adapterCreator:
                        interaction.guild.voiceAdapterCreator,
                    selfDeaf: true,
                    selfMute: false,
                });

                connection.on("stateChange", (oldState, newState) => {
                    console.log(
                        `[VOICE STATE] ${oldState.status} -> ${newState.status}`
                    );
                });
                
                // await entersState(
                //     connection,
                //     VoiceConnectionStatus.Ready,
                //     30000
                // );

                const player = createAudioPlayer({
                    behaviors: {
                        noSubscriber:
                            NoSubscriberBehavior.Pause,
                    },
                });

                // ===== ログ追加 =====

                player.on("error", error => {
                    console.error("[PLAYER ERROR]", error);
                });

                player.on(AudioPlayerStatus.Playing, () => {
                    console.log("[PLAYER STATUS] Playing");
                });

                player.on(AudioPlayerStatus.Idle, () => {
                    console.log("[PLAYER STATUS] Idle");
                });

                // ====================

                connection.subscribe(player);

                sessions.set(guildId, {
                    connection,
                    player,
                    queue: [],
                    textChannelId: interaction.channel.id,
                    speaker: 3,
                });

                processQueue(guildId);

                await interaction.editReply(
                    `✅ ${member.voice.channel} に接続しました。`
                );

            } catch (e) {

                console.error("[CONNECT ERROR]", e);

                sessions.delete(guildId);

                await interaction.editReply(
                    `❌ 接続失敗\n${e}`
                );
            }
        }

        if (interaction.commandName === "切断") {

            const session = sessions.get(
                interaction.guild.id
            );

            if (!session) {
                return interaction.reply({
                    content:
                        "❌ 接続されていません。",
                    ephemeral: true,
                });
            }

            session.connection.destroy();

            sessions.delete(interaction.guild.id);

            return interaction.reply({
                content: "👋 切断しました。",
                ephemeral: true,
            });
        }

        if (interaction.commandName === "話者変更") {

            const menu =
                new StringSelectMenuBuilder()
                    .setCustomId("speaker_select")
                    .setPlaceholder("話者を選択")
                    .addOptions(
                        Object.entries(SPEAKERS).map(
                            ([name, id]) => ({
                                label: name,
                                value: String(id),
                            })
                        )
                    );

            const row =
                new ActionRowBuilder()
                    .addComponents(menu);

            return interaction.reply({
                content: "🎤 話者を選択してください",
                components: [row],
                ephemeral: true,
            });
        }
    }

    if (interaction.isStringSelectMenu()) {

        if (interaction.customId === "speaker_select") {

            const session = sessions.get(
                interaction.guild.id
            );

            if (!session) {
                return interaction.reply({
                    content:
                        "❌ 読み上げ接続されていません。",
                    ephemeral: true,
                });
            }

            session.speaker = parseInt(
                interaction.values[0]
            );

            const speakerName = Object.keys(
                SPEAKERS
            ).find(
                k => SPEAKERS[k] === session.speaker
            );

            await interaction.reply({
                content:
                    `✅ 話者を「${speakerName}」へ変更しました。`,
                ephemeral: true,
            });
        }
    }
});

client.on(Events.MessageCreate, async message => {

    if (message.author.bot) return;

    if (!message.guild) return;

    const session = sessions.get(
        message.guild.id
    );

    if (!session) return;

    if (
        message.channel.id !==
        session.textChannelId
    ) return;

    const now = Date.now();

    const last =
        cooldowns.get(message.author.id) || 0;

    if (now - last < 2000) return;

    cooldowns.set(message.author.id, now);

    const text = sanitizeText(message.content);

    if (!text) return;

    console.log("[QUEUE PUT]", text);

    session.queue.push(text);
});

client.on(
    Events.VoiceStateUpdate,
    async (oldState, newState) => {

        const guildId =
            oldState.guild.id;

        const session =
            sessions.get(guildId);

        if (!session) return;

        const channel =
            oldState.guild.channels.cache.get(
                session.connection.joinConfig.channelId
            );

        if (!channel) return;

        const humans =
            channel.members.filter(
                m => !m.user.bot
            );

        if (humans.size === 0) {

            console.log(
                "[VOICE AUTO DISCONNECT]"
            );

            session.connection.destroy();

            sessions.delete(guildId);
        }
    }
);

client.login(TOKEN);
