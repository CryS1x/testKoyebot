import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import random
import time
from datetime import datetime
import os
import asyncio

# Конфигурация
CONFIG = {
    'TOKEN': 'MTQzMjM2MTcxMDg4MjEyODA3Nw.GquORF.kx_TO1GWRpfNRE2J77kuM0fkAdsLRFYBafMLuc',
    'MAX_LEVEL': 1000,
    'TEXT_XP_MIN': 5,
    'TEXT_XP_MAX': 10,
    'TEXT_COOLDOWN': 30,  # секунды
    'VOICE_XP_PER_MINUTE': 5,
    'XP_PER_LEVEL': 100
}

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище данных
user_data = {}
server_settings = {}
cooldowns = {}
voice_tracking = {}
DATA_FILE = 'userdata.json'
SETTINGS_FILE = 'settings.json'


# Загрузка данных
def load_data():
    global user_data, server_settings
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except:
            user_data = {}
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                server_settings = json.load(f)
        except:
            server_settings = {}


# Сохранение данных
def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, indent=2, ensure_ascii=False)


# Сохранение настроек
def save_settings():
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(server_settings, f, indent=2, ensure_ascii=False)


# Получение данных пользователя
def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {
            'text_xp': 0,
            'text_level': 1,
            'voice_xp': 0,
            'voice_level': 1,
            'total_xp': 0,
            'total_level': 1
        }
    return user_data[user_id]


# Получение канала уведомлений
def get_notification_channel(guild_id):
    guild_id = str(guild_id)
    if guild_id in server_settings:
        return server_settings[guild_id].get('notification_channel')
    return None


# Расчет уровня по опыту
def calculate_level(xp):
    return min(xp // CONFIG['XP_PER_LEVEL'] + 1, CONFIG['MAX_LEVEL'])


# Добавление опыта
def add_xp(user_id, xp, xp_type):
    user_id = str(user_id)
    user = get_user_data(user_id)
    
    if xp_type == 'text':
        user['text_xp'] = max(0, user['text_xp'] + xp)
        user['text_level'] = calculate_level(user['text_xp'])
    elif xp_type == 'voice':
        user['voice_xp'] = max(0, user['voice_xp'] + xp)
        user['voice_level'] = calculate_level(user['voice_xp'])
    
    user['total_xp'] = user['text_xp'] + user['voice_xp']
    user['total_level'] = calculate_level(user['total_xp'])
    
    save_data()
    return user


# Получение прогресс-бара
def get_progress_bar(current_xp, level, length=20):
    xp_for_current_level = (level - 1) * CONFIG['XP_PER_LEVEL']
    xp_for_next_level = level * CONFIG['XP_PER_LEVEL']
    xp_in_level = current_xp - xp_for_current_level
    xp_needed = xp_for_next_level - xp_for_current_level
    
    if level >= CONFIG['MAX_LEVEL']:
        filled = length
    else:
        filled = int((xp_in_level / xp_needed) * length)
    
    bar = '█' * filled + '░' * (length - filled)
    percentage = int((xp_in_level / xp_needed) * 100) if level < CONFIG['MAX_LEVEL'] else 100
    
    return bar, percentage, xp_in_level, xp_needed


# Создание улучшенной карточки уровня
def create_level_embed(user, member):
    data = get_user_data(user.id)
    
    # Прогресс-бары
    text_bar, text_pct, text_current, text_needed = get_progress_bar(data['text_xp'], data['text_level'])
    voice_bar, voice_pct, voice_current, voice_needed = get_progress_bar(data['voice_xp'], data['voice_level'])
    total_bar, total_pct, total_current, total_needed = get_progress_bar(data['total_xp'], data['total_level'])
    
    # Определение цвета по общему уровню
    if data['total_level'] >= 500:
        color = discord.Color.gold()
    elif data['total_level'] >= 250:
        color = discord.Color.purple()
    elif data['total_level'] >= 100:
        color = discord.Color.blue()
    else:
        color = discord.Color.green()
    
    embed = discord.Embed(
        color=color,
        timestamp=datetime.now()
    )
    
    embed.set_author(
        name=f"Профиль {member.display_name}",
        icon_url=user.display_avatar.url
    )
    
    embed.set_thumbnail(url=user.display_avatar.url)
    
    # Текстовый чат
    text_status = "🏆 МАКСИМУМ" if data['text_level'] >= CONFIG['MAX_LEVEL'] else f"{text_current}/{text_needed} XP"
    embed.add_field(
        name="",
        value=f"```md\n# 💬 Текстовый Чат\n```"
              f"**Уровень:** `{data['text_level']}`\n"
              f"**Опыт:** `{data['text_xp']:,}` XP\n"
              f"{text_bar} `{text_pct}%`\n"
              f"{text_status}",
        inline=False
    )
    
    # Голосовой чат
    voice_status = "🏆 МАКСИМУМ" if data['voice_level'] >= CONFIG['MAX_LEVEL'] else f"{voice_current}/{voice_needed} XP"
    embed.add_field(
        name="",
        value=f"```md\n# 🎤 Голосовой Чат\n```"
              f"**Уровень:** `{data['voice_level']}`\n"
              f"**Опыт:** `{data['voice_xp']:,}` XP\n"
              f"{voice_bar} `{voice_pct}%`\n"
              f"{voice_status}",
        inline=False
    )
    
    # Общий уровень
    total_status = "🏆 МАКСИМУМ" if data['total_level'] >= CONFIG['MAX_LEVEL'] else f"{total_current}/{total_needed} XP"
    embed.add_field(
        name="",
        value=f"```md\n# ⭐ Общий Уровень\n```"
              f"**Уровень:** `{data['total_level']}`\n"
              f"**Всего опыта:** `{data['total_xp']:,}` XP\n"
              f"{total_bar} `{total_pct}%`\n"
              f"{total_status}",
        inline=False
    )
    
    embed.set_footer(
        text=f"by crysix",
        icon_url=bot.user.display_avatar.url
    )
    
    return embed


# Создание топа
def create_leaderboard_embed(guild, top_type='total'):
    if top_type == 'text':
        sorted_users = sorted(user_data.items(), key=lambda x: x[1]['text_xp'], reverse=True)[:10]
        title = "💬 Топ-10 по текстовому чату"
        emoji = "💬"
        field = 'text'
    elif top_type == 'voice':
        sorted_users = sorted(user_data.items(), key=lambda x: x[1]['voice_xp'], reverse=True)[:10]
        title = "🎤 Топ-10 по голосовому чату"
        emoji = "🎤"
        field = 'voice'
    else:
        sorted_users = sorted(user_data.items(), key=lambda x: x[1]['total_xp'], reverse=True)[:10]
        title = "⭐ Топ-10 общий рейтинг"
        emoji = "⭐"
        field = 'total'
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    medals = ["🥇", "🥈", "🥉"]
    description = ""
    
    for idx, (user_id, data) in enumerate(sorted_users):
        try:
            member = guild.get_member(int(user_id))
            if not member:
                continue
            
            medal = medals[idx] if idx < 3 else f"`#{idx + 1}`"
            level = data[f'{field}_level']
            xp = data[f'{field}_xp']
            
            description += f"{medal} **{member.display_name}**\n"
            description += f"　└ Уровень: `{level}` • Опыт: `{xp:,}` XP\n\n"
        except:
            continue
    
    if not description:
        description = "*Пока нет данных*"
    
    embed.description = description
    embed.set_footer(
        text=f"Обновлено",
        icon_url=bot.user.display_avatar.url
    )
    
    return embed


# Событие: бот готов
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен!')
    load_data()
    
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} команд')
    except Exception as e:
        print(f'Ошибка синхронизации команд: {e}')
    
    voice_xp_task.start()


# Обработка сообщений для текстового опыта
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    user_id = str(message.author.id)
    current_time = time.time()
    
    # Проверка кулдауна
    if user_id in cooldowns:
        if current_time - cooldowns[user_id] < CONFIG['TEXT_COOLDOWN']:
            return
    
    # Добавление опыта
    old_data = get_user_data(user_id).copy()
    xp = random.randint(CONFIG['TEXT_XP_MIN'], CONFIG['TEXT_XP_MAX'])
    new_data = add_xp(user_id, xp, 'text')
    
    cooldowns[user_id] = current_time
    
    # Уведомление о повышении уровня
    if new_data['text_level'] > old_data['text_level']:
        embed = discord.Embed(
            title="🎉 Повышение уровня!",
            description=f"{message.author.mention} достиг **{new_data['text_level']}** уровня в текстовом чате!",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        
        # Отправка в канал уведомлений
        notification_channel_id = get_notification_channel(message.guild.id)
        if notification_channel_id:
            channel = bot.get_channel(int(notification_channel_id))
            if channel:
                await channel.send(embed=embed)
            else:
                await message.channel.send(embed=embed)
        else:
            await message.channel.send(embed=embed)
    
    await bot.process_commands(message)


# Отслеживание голосовых каналов
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    user_id = str(member.id)
    
    # Пользователь зашел в голосовой канал
    if before.channel is None and after.channel is not None:
        voice_tracking[user_id] = time.time()
    
    # Пользователь вышел из голосового канала
    elif before.channel is not None and after.channel is None:
        if user_id in voice_tracking:
            join_time = voice_tracking[user_id]
            duration = time.time() - join_time
            minutes = int(duration / 60)
            
            if minutes > 0:
                old_data = get_user_data(user_id).copy()
                xp = minutes * CONFIG['VOICE_XP_PER_MINUTE']
                new_data = add_xp(user_id, xp, 'voice')
                
                # Уведомление о повышении уровня
                if new_data['voice_level'] > old_data['voice_level']:
                    embed = discord.Embed(
                        title="🎉 Повышение уровня!",
                        description=f"{member.mention} достиг **{new_data['voice_level']}** уровня в голосовом чате!",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    # Отправка в канал уведомлений
                    notification_channel_id = get_notification_channel(member.guild.id)
                    if notification_channel_id:
                        channel = bot.get_channel(int(notification_channel_id))
                        if channel:
                            await channel.send(embed=embed)
            
            del voice_tracking[user_id]


# Периодическое начисление опыта в голосовых каналах
@tasks.loop(minutes=1)
async def voice_xp_task():
    for user_id in list(voice_tracking.keys()):
        add_xp(user_id, CONFIG['VOICE_XP_PER_MINUTE'], 'voice')


# Команда: показать свой уровень
@bot.tree.command(name="уровень", description="Показать вашу карточку с уровнем")
async def level_command(interaction: discord.Interaction):
    embed = create_level_embed(interaction.user, interaction.user)
    await interaction.response.send_message(embed=embed)


# Команда: посмотреть профиль
@bot.tree.command(name="профиль", description="Посмотреть профиль пользователя")
@app_commands.describe(пользователь="Выберите пользователя")
async def profile_command(interaction: discord.Interaction, пользователь: discord.Member = None):
    target = пользователь or interaction.user
    embed = create_level_embed(target, target)
    await interaction.response.send_message(embed=embed)


# Команда: топ по текстовому
@bot.tree.command(name="топ_текст", description="Топ-10 игроков по текстовому чату")
async def top_text_command(interaction: discord.Interaction):
    embed = create_leaderboard_embed(interaction.guild, 'text')
    await interaction.response.send_message(embed=embed)


# Команда: топ по голосовому
@bot.tree.command(name="топ_войс", description="Топ-10 игроков по голосовому чату")
async def top_voice_command(interaction: discord.Interaction):
    embed = create_leaderboard_embed(interaction.guild, 'voice')
    await interaction.response.send_message(embed=embed)


# Команда: общий топ
@bot.tree.command(name="топ", description="Топ-10 игроков общий рейтинг")
async def top_total_command(interaction: discord.Interaction):
    embed = create_leaderboard_embed(interaction.guild, 'total')
    await interaction.response.send_message(embed=embed)


# Команда: установить канал уведомлений
@bot.tree.command(name="установить_канал", description="Установить канал для уведомлений о повышении уровня (только для админов)")
@app_commands.describe(канал="Выберите текстовый канал")
async def set_channel_command(interaction: discord.Interaction, канал: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    if guild_id not in server_settings:
        server_settings[guild_id] = {}
    
    server_settings[guild_id]['notification_channel'] = str(канал.id)
    save_settings()
    
    embed = discord.Embed(
        description=f"✅ Канал уведомлений установлен: {канал.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# Команда: выдать уровень (только админы)
@bot.tree.command(name="дать_уровень", description="Выдать уровень пользователю (только для админов)")
@app_commands.describe(
    пользователь="Выберите пользователя",
    тип="Тип опыта",
    количество="Количество опыта"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="Текстовый", value="text"),
    app_commands.Choice(name="Голосовой", value="voice"),
])
async def give_level_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    тип: app_commands.Choice[str],
    количество: int
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1:
        await interaction.response.send_message("❌ Количество должно быть положительным!", ephemeral=True)
        return
    
    add_xp(пользователь.id, количество, тип.value)
    
    type_name = "текстовый" if тип.value == "text" else "голосовой"
    
    embed = discord.Embed(
        description=f"✅ Выдано **{количество}** XP ({type_name}) пользователю {пользователь.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# Команда: убрать уровень (только админы)
@bot.tree.command(name="убрать_уровень", description="Убрать уровень у пользователя (только для админов)")
@app_commands.describe(
    пользователь="Выберите пользователя",
    тип="Тип опыта",
    количество="Количество опыта"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="Текстовый", value="text"),
    app_commands.Choice(name="Голосовой", value="voice"),
])
async def remove_level_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    тип: app_commands.Choice[str],
    количество: int
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1:
        await interaction.response.send_message("❌ Количество должно быть положительным!", ephemeral=True)
        return
    
    add_xp(пользователь.id, -количество, тип.value)
    
    type_name = "текстовый" if тип.value == "text" else "голосовой"
    
    embed = discord.Embed(
        description=f"✅ Убрано **{количество}** XP ({type_name}) у пользователя {пользователь.mention}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


# Команда: сбросить уровень (только админы)
@bot.tree.command(name="сбросить_уровень", description="Полностью сбросить уровни пользователя (только для админов)")
@app_commands.describe(
    пользователь="Выберите пользователя",
    тип="Что сбросить"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="Всё", value="all"),
    app_commands.Choice(name="Только текстовый", value="text"),
    app_commands.Choice(name="Только голосовой", value="voice"),
])
async def reset_level_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    тип: app_commands.Choice[str]
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    user_id = str(пользователь.id)
    user = get_user_data(user_id)
    
    if тип.value == "all":
        user['text_xp'] = 0
        user['text_level'] = 1
        user['voice_xp'] = 0
        user['voice_level'] = 1
        user['total_xp'] = 0
        user['total_level'] = 1
        reset_text = "все"
    elif тип.value == "text":
        user['text_xp'] = 0
        user['text_level'] = 1
        user['total_xp'] = user['voice_xp']
        user['total_level'] = calculate_level(user['total_xp'])
        reset_text = "текстовый"
    elif тип.value == "voice":
        user['voice_xp'] = 0
        user['voice_level'] = 1
        user['total_xp'] = user['text_xp']
        user['total_level'] = calculate_level(user['total_xp'])
        reset_text = "голосовой"
    
    save_data()
    
    embed = discord.Embed(
        description=f"✅ Уровни пользователя {пользователь.mention} были сброшены ({reset_text})",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


# Команда: очистить сообщения бота (только админы)
@bot.tree.command(name="очистить_бота", description="Очистить сообщения бота в канале (только для админов)")
@app_commands.describe(
    количество="Количество сообщений для очистки (макс. 100)",
    канал="Канал для очистки (по умолчанию текущий)"
)
async def clear_bot_command(
    interaction: discord.Interaction,
    количество: int = 50,
    канал: discord.TextChannel = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1 or количество > 100:
        await interaction.response.send_message("❌ Количество должно быть от 1 до 100!", ephemeral=True)
        return
    
    channel = канал or interaction.channel
    
    # Отправляем сообщение о начале очистки
    await interaction.response.send_message(f"🧹 Очищаю последние {количество} сообщений бота...", ephemeral=True)
    
    try:
        # Получаем сообщения и фильтруем только от бота
        def is_bot_message(msg):
            return msg.author == bot.user
        
        deleted = await channel.purge(limit=количество, check=is_bot_message, before=interaction.created_at)
        
        # Отправляем отчет
        report = await interaction.followup.send(
            f"✅ Удалено {len(deleted)} сообщений бота в {channel.mention}",
            ephemeral=True
        )
        
        # Удаляем отчет через 5 секунд
        await asyncio.sleep(5)
        await report.delete()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при очистке: {str(e)}", ephemeral=True)


# Команда: очистить все сообщения в канале (только админы)
@bot.tree.command(name="очистить_канал", description="Очистить все сообщения в канале (только для админов)")
@app_commands.describe(
    количество="Количество сообщений для очистки (макс. 100)",
    канал="Канал для очистки (по умолчанию текущий)",
    удалить_пользовательские="Удалить также сообщения пользователей"
)
async def clear_channel_command(
    interaction: discord.Interaction,
    количество: int = 50,
    канал: discord.TextChannel = None,
    удалить_пользовательские: bool = False
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1 or количество > 100:
        await interaction.response.send_message("❌ Количество должно быть от 1 до 100!", ephemeral=True)
        return
    
    channel = канал or interaction.channel
    
    # Отправляем сообщение о начале очистки
    await interaction.response.send_message(f"🧹 Очищаю последние {количество} сообщений в канале...", ephemeral=True)
    
    try:
        if удалить_пользовательские:
            # Удаляем все сообщения
            deleted = await channel.purge(limit=количество, before=interaction.created_at)
            message_type = "всех сообщений"
        else:
            # Удаляем только сообщения бота
            def is_bot_message(msg):
                return msg.author == bot.user
            
            deleted = await channel.purge(limit=количество, check=is_bot_message, before=interaction.created_at)
            message_type = "сообщений бота"
        
        # Отправляем отчет
        report = await interaction.followup.send(
            f"✅ Удалено {len(deleted)} {message_type} в {channel.mention}",
            ephemeral=True
        )
        
        # Удаляем отчет через 5 секунд
        await asyncio.sleep(5)
        await report.delete()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при очистке: {str(e)}", ephemeral=True)


# Команда: очистить команды пользователей (только админы)
@bot.tree.command(name="очистить_команды", description="Очистить слеши-команды пользователей (только для админов)")
@app_commands.describe(
    количество="Количество сообщений для очистки (макс. 100)",
    канал="Канал для очистки (по умолчанию текущий)"
)
async def clear_commands_command(
    interaction: discord.Interaction,
    количество: int = 50,
    канал: discord.TextChannel = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1 or количество > 100:
        await interaction.response.send_message("❌ Количество должно быть от 1 до 100!", ephemeral=True)
        return
    
    channel = канал or interaction.channel
    
    # Отправляем сообщение о начале очистки
    await interaction.response.send_message(f"🧹 Очищаю последние {количество} команд пользователей...", ephemeral=True)
    
    try:
        # Фильтруем только слеши-команды пользователей
        def is_user_command(msg):
            return (not msg.author.bot and 
                   msg.content and 
                   (msg.content.startswith('/') or 'application.command' in str(msg.type)))
        
        deleted = await channel.purge(limit=количество, check=is_user_command, before=interaction.created_at)
        
        # Отправляем отчет
        report = await interaction.followup.send(
            f"✅ Удалено {len(deleted)} команд пользователей в {channel.mention}",
            ephemeral=True
        )
        
        # Удаляем отчет через 5 секунд
        await asyncio.sleep(5)
        await report.delete()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при очистке: {str(e)}", ephemeral=True)


# Команда: массовая очистка (только админы)
@bot.tree.command(name="массовая_очистка", description="Массовая очистка разных типов сообщений (только для админов)")
@app_commands.describe(
    тип_очистки="Что очищать",
    количество="Количество сообщений (макс. 100)",
    канал="Канал для очистки"
)
@app_commands.choices(тип_очистки=[
    app_commands.Choice(name="Все сообщения бота", value="bot_all"),
    app_commands.Choice(name="Только команды бота", value="bot_commands"),
    app_commands.Choice(name="Сообщения пользователей", value="user_messages"),
    app_commands.Choice(name="Команды пользователей", value="user_commands"),
    app_commands.Choice(name="Всё подряд", value="everything"),
])
async def mass_clear_command(
    interaction: discord.Interaction,
    тип_очистки: app_commands.Choice[str],
    количество: int = 50,
    канал: discord.TextChannel = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    if количество < 1 or количество > 100:
        await interaction.response.send_message("❌ Количество должно быть от 1 до 100!", ephemeral=True)
        return
    
    channel = канал or interaction.channel
    
    # Определяем функцию проверки в зависимости от типа очистки
    if тип_очистки.value == "bot_all":
        def check(msg):
            return msg.author == bot.user
        type_name = "всех сообщений бота"
    elif тип_очистки.value == "bot_commands":
        def check(msg):
            return (msg.author == bot.user and 
                   (msg.embeds or "Уровень" in msg.content or "Топ" in msg.content))
        type_name = "команд бота"
    elif тип_очистки.value == "user_messages":
        def check(msg):
            return not msg.author.bot
        type_name = "сообщений пользователей"
    elif тип_очистки.value == "user_commands":
        def check(msg):
            return (not msg.author.bot and 
                   (msg.content.startswith('/') or 'application.command' in str(msg.type)))
        type_name = "команд пользователей"
    else:  # everything
        def check(msg):
            return True
        type_name = "всех сообщений"
    
    # Отправляем сообщение о начале очистки
    await interaction.response.send_message(f"🧹 Очищаю {количество} {type_name}...", ephemeral=True)
    
    try:
        deleted = await channel.purge(limit=количество, check=check, before=interaction.created_at)
        
        # Отправляем отчет
        report = await interaction.followup.send(
            f"✅ Удалено {len(deleted)} {type_name} в {channel.mention}",
            ephemeral=True
        )
        
        # Удаляем отчет через 5 секунд
        await asyncio.sleep(5)
        await report.delete()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при очистке: {str(e)}", ephemeral=True)


# Запуск бота
if __name__ == "__main__":
    bot.run(CONFIG['TOKEN'])