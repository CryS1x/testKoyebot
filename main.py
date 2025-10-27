import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import random
import time
from datetime import datetime
import os
import asyncio
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
CONFIG = {
    'TOKEN': os.getenv('DISCORD_BOT_TOKEN'),
    'MAX_LEVEL': 1000,
    'TEXT_XP_MIN': 5,
    'TEXT_XP_MAX': 10,
    'TEXT_COOLDOWN': 30,  # секунды
    'VOICE_XP_PER_MINUTE': 5,
    'XP_PER_LEVEL': 100
}

if not CONFIG['TOKEN']:
    raise ValueError("Токен бота не найден! Установите переменную DISCORD_BOT_TOKEN")

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.moderation = True
intents.integrations = True
intents.webhooks = True
intents.invites = True
intents.voice_states = True
intents.presences = True
intents.message_content = True
intents.reactions = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_typing = True
intents.dm_messages = True
intents.dm_reactions = True
intents.dm_typing = True
intents.guild_scheduled_events = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище данных
user_data = {}
server_settings = {}
cooldowns = {}
voice_tracking = {}
DATA_FILE = 'userdata.json'
SETTINGS_FILE = 'settings.json'

# Цвета для эмбедов
COLORS = {
    'INFO': discord.Color.blue(),
    'SUCCESS': discord.Color.green(),
    'WARNING': discord.Color.orange(),
    'ERROR': discord.Color.red(),
    'MODERATION': discord.Color.purple(),
    'LEVEL_UP': discord.Color.gold()
}

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

# Получение канала логов
def get_log_channel(guild_id):
    guild_id = str(guild_id)
    if guild_id in server_settings:
        return server_settings[guild_id].get('log_channel')
    return None

# Расчет уровня по опыту
def calculate_level(xp):
    return min(xp // CONFIG['XP_PER_LEVEL'] + 1, CONFIG['MAX_LEVEL'])

# Добавление опыта
async def add_xp(user_id, xp, xp_type, guild=None):
    user_id = str(user_id)
    user = get_user_data(user_id)
    
    old_level = user[f'{xp_type}_level']
    
    if xp_type == 'text':
        user['text_xp'] = max(0, user['text_xp'] + xp)
        user['text_level'] = calculate_level(user['text_xp'])
    elif xp_type == 'voice':
        user['voice_xp'] = max(0, user['voice_xp'] + xp)
        user['voice_level'] = calculate_level(user['voice_xp'])
    
    user['total_xp'] = user['text_xp'] + user['voice_xp']
    user['total_level'] = calculate_level(user['total_xp'])
    
    save_data()
    
    # Проверка повышения уровня
    new_level = user[f'{xp_type}_level']
    if new_level > old_level and guild:
        await send_level_up_notification(user_id, xp_type, old_level, new_level, guild)
    
    return user

# Отправка уведомления о повышении уровня
async def send_level_up_notification(user_id, xp_type, old_level, new_level, guild):
    try:
        member = guild.get_member(int(user_id))
        if not member:
            return
        
        type_name = "текстовом" if xp_type == "text" else "голосовом"
        type_emoji = "💬" if xp_type == "text" else "🎤"
        
        embed = discord.Embed(
            title="🎉 Повышение уровня!",
            description=f"{member.mention} достиг **{new_level}** уровня в {type_name} чате!",
            color=COLORS['LEVEL_UP'],
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name=f"{type_emoji} Уровень повышен",
            value=f"**Был:** `{old_level}`\n**Стал:** `{new_level}`",
            inline=True
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Поздравляем! 🎊")
        
        # Отправка в канал уведомлений
        notification_channel_id = get_notification_channel(guild.id)
        if notification_channel_id:
            channel = bot.get_channel(int(notification_channel_id))
            if channel:
                await channel.send(embed=embed)
                return
        
        # Если канал уведомлений не установлен, отправляем в системный канал
        if guild.system_channel:
            await guild.system_channel.send(embed=embed)
            
    except Exception as e:
        print(f"Ошибка отправки уведомления о уровне: {e}")

# Логирование действий
async def log_action(guild, action, description, color=COLORS['INFO'], target=None, moderator=None, reason=None):
    try:
        log_channel_id = get_log_channel(guild.id)
        if not log_channel_id:
            return
        
        channel = bot.get_channel(int(log_channel_id))
        if not channel:
            return
        
        embed = discord.Embed(
            title=f"📝 {action}",
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        if target:
            embed.add_field(name="👤 Участник", value=f"{target.mention} (`{target.id}`)", inline=True)
        
        if moderator:
            embed.add_field(name="🛡️ Модератор", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
        
        if reason:
            embed.add_field(name="📋 Причина", value=reason, inline=False)
        
        embed.set_footer(text=f"ID: {target.id if target else 'Система'}")
        
        await channel.send(embed=embed)
        
    except Exception as e:
        print(f"Ошибка логирования: {e}")

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
        name=f"📊 Профиль {member.display_name}",
        icon_url=user.display_avatar.url
    )
    
    embed.set_thumbnail(url=user.display_avatar.url)
    
    # Общая информация
    embed.add_field(
        name="👤 Общая информация",
        value=f"**Уровень:** `{data['total_level']}`\n"
              f"**Опыт:** `{data['total_xp']:,}` XP\n"
              f"**Прогресс:** {total_bar}\n"
              f"**{total_pct}%** ({total_current}/{total_needed} XP)",
        inline=False
    )
    
    # Текстовый чат
    text_status = "🏆 МАКСИМУМ" if data['text_level'] >= CONFIG['MAX_LEVEL'] else f"{text_current}/{text_needed} XP"
    embed.add_field(
        name="💬 Текстовый чат",
        value=f"**Уровень:** `{data['text_level']}`\n"
              f"**Опыт:** `{data['text_xp']:,}` XP\n"
              f"**Прогресс:** {text_bar}\n"
              f"**{text_pct}%** ({text_status})",
        inline=True
    )
    
    # Голосовой чат
    voice_status = "🏆 МАКСИМУМ" if data['voice_level'] >= CONFIG['MAX_LEVEL'] else f"{voice_current}/{voice_needed} XP"
    embed.add_field(
        name="🎤 Голосовой чат",
        value=f"**Уровень:** `{data['voice_level']}`\n"
              f"**Опыт:** `{data['voice_xp']:,}` XP\n"
              f"**Прогресс:** {voice_bar}\n"
              f"**{voice_pct}%** ({voice_status})",
        inline=True
    )
    
    # Достижения
    next_milestone = ((data['total_level'] // 100) + 1) * 100
    if next_milestone <= CONFIG['MAX_LEVEL']:
        xp_needed_total = next_milestone * CONFIG['XP_PER_LEVEL'] - data['total_xp']
        embed.add_field(
            name="🎯 Следующая цель",
            value=f"**Уровень {next_milestone}**\n"
                  f"Осталось: `{xp_needed_total:,}` XP",
            inline=False
        )
    
    embed.set_footer(
        text=f"by crysix | Обновлено",
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
            description += f"　├ Уровень: `{level}`\n"
            description += f"　└ Опыт: `{xp:,}` XP\n\n"
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
    xp = random.randint(CONFIG['TEXT_XP_MIN'], CONFIG['TEXT_XP_MAX'])
    await add_xp(user_id, xp, 'text', message.guild)
    
    cooldowns[user_id] = current_time
    
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
                xp = minutes * CONFIG['VOICE_XP_PER_MINUTE']
                await add_xp(user_id, xp, 'voice', member.guild)
            
            del voice_tracking[user_id]

# Периодическое начисление опыта в голосовых каналах
@tasks.loop(minutes=1)
async def voice_xp_task():
    for user_id in list(voice_tracking.keys()):
        guild_id = user_id  # Здесь нужно определить guild_id из voice_tracking
        # Для простоты начисляем без уведомлений в этой задаче
        add_xp(user_id, CONFIG['VOICE_XP_PER_MINUTE'], 'voice')

# События для логирования
@bot.event
async def on_member_join(member):
    await log_action(
        member.guild,
        "Участник присоединился",
        f"Новый участник присоединился к серверу",
        COLORS['SUCCESS'],
        member
    )

@bot.event
async def on_member_remove(member):
    await log_action(
        member.guild,
        "Участник покинул",
        f"Участник покинул сервер",
        COLORS['WARNING'],
        member
    )

@bot.event
async def on_member_ban(guild, user):
    await log_action(
        guild,
        "Участник забанен",
        f"Участник был забанен на сервере",
        COLORS['ERROR'],
        user
    )

@bot.event
async def on_member_unban(guild, user):
    await log_action(
        guild,
        "Участник разбанен",
        f"С участника снят бан",
        COLORS['SUCCESS'],
        user
    )

@bot.event
async def on_member_update(before, after):
    # Изменение ролей
    if before.roles != after.roles:
        added_roles = [role for role in after.roles if role not in before.roles]
        removed_roles = [role for role in before.roles if role not in after.roles]
        
        if added_roles:
            for role in added_roles:
                await log_action(
                    after.guild,
                    "Роль выдана",
                    f"Участнику выдана роль {role.mention}",
                    COLORS['MODERATION'],
                    after
                )
        
        if removed_roles:
            for role in removed_roles:
                await log_action(
                    after.guild,
                    "Роль изъята",
                    f"С участника снята роль {role.mention}",
                    COLORS['MODERATION'],
                    after
                )
    
    # Изменение ника
    if before.nick != after.nick:
        await log_action(
            after.guild,
            "Изменен никнейм",
            f"**Был:** `{before.nick or before.display_name}`\n**Стал:** `{after.nick or after.display_name}`",
            COLORS['INFO'],
            after
        )

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    
    await log_action(
        message.guild,
        "Сообщение удалено",
        f"**Канал:** {message.channel.mention}\n**Содержимое:** {message.content[:1000]}",
        COLORS['WARNING'],
        message.author
    )

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    
    await log_action(
        before.guild,
        "Сообщение изменено",
        f"**Канал:** {before.channel.mention}\n**Было:** {before.content[:500]}\n**Стало:** {after.content[:500]}",
        COLORS['INFO'],
        before.author
    )

@bot.event
async def on_guild_channel_create(channel):
    await log_action(
        channel.guild,
        "Канал создан",
        f"**Тип:** {'💬 Текстовый' if isinstance(channel, discord.TextChannel) else '🎤 Голосовой'}\n**Название:** {channel.mention}",
        COLORS['SUCCESS']
    )

@bot.event
async def on_guild_channel_delete(channel):
    await log_action(
        channel.guild,
        "Канал удален",
        f"**Тип:** {'💬 Текстовый' if isinstance(channel, discord.TextChannel) else '🎤 Голосовой'}\n**Название:** `{channel.name}`",
        COLORS['ERROR']
    )

@bot.event
async def on_guild_role_create(role):
    await log_action(
        role.guild,
        "Роль создана",
        f"**Роль:** {role.mention}\n**Цвет:** `{role.color}`",
        COLORS['SUCCESS']
    )

@bot.event
async def on_guild_role_delete(role):
    await log_action(
        role.guild,
        "Роль удалена",
        f"**Роль:** `{role.name}`\n**Цвет:** `{role.color}`",
        COLORS['ERROR']
    )

@bot.event
async def on_guild_role_update(before, after):
    if before.name != after.name:
        await log_action(
            after.guild,
            "Роль переименована",
            f"**Было:** `{before.name}`\n**Стало:** `{after.name}`",
            COLORS['INFO'],
            target=None
        )
    
    if before.permissions != after.permissions:
        await log_action(
            after.guild,
            "Изменены права роли",
            f"**Роль:** {after.mention}",
            COLORS['MODERATION'],
            target=None
        )

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

# Команда: установить канал логов
@bot.tree.command(name="установить_логи", description="Установить канал для логирования действий (только для админов)")
@app_commands.describe(канал="Выберите текстовый канал для логов")
async def set_logs_command(interaction: discord.Interaction, канал: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ У вас нет прав администратора!", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    if guild_id not in server_settings:
        server_settings[guild_id] = {}
    
    server_settings[guild_id]['log_channel'] = str(канал.id)
    save_settings()
    
    embed = discord.Embed(
        description=f"✅ Канал логов установлен: {канал.mention}",
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
    
    await add_xp(пользователь.id, количество, тип.value, interaction.guild)
    
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
    
    await add_xp(пользователь.id, -количество, тип.value, interaction.guild)
    
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
    
    await interaction.response.send_message(f"🧹 Очищаю последние {количество} сообщений бота...", ephemeral=True)
    
    try:
        def is_bot_message(msg):
            return msg.author == bot.user
        
        deleted = await channel.purge(limit=количество, check=is_bot_message, before=interaction.created_at)
        
        report = await interaction.followup.send(
            f"✅ Удалено {len(deleted)} сообщений бота в {channel.mention}",
            ephemeral=True
        )
        
        await asyncio.sleep(5)
        await report.delete()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при очистке: {str(e)}", ephemeral=True)

# Команда: информация о логах
@bot.tree.command(name="логи_инфо", description="Показать информацию о настройках логов")
async def logs_info_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    
    embed = discord.Embed(
        title="📊 Информация о системе логов",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    notification_channel = get_notification_channel(guild_id)
    log_channel = get_log_channel(guild_id)
    
    embed.add_field(
        name="🔔 Канал уведомлений",
        value=f"<#{notification_channel}>" if notification_channel else "❌ Не установлен",
        inline=True
    )
    
    embed.add_field(
        name="📝 Канал логов",
        value=f"<#{log_channel}>" if log_channel else "❌ Не установлен",
        inline=True
    )
    
    embed.add_field(
        name="📋 Логируемые события",
        value="• Сообщения (удаление/изменение)\n• Участники (вход/выход/бан)\n• Роли и права\n• Каналы\n• Голосовые каналы",
        inline=False
    )
    
    if not log_channel:
        embed.add_field(
            name="💡 Совет",
            value="Используйте `/установить_логи` чтобы настроить канал для логов",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

# Запуск бота
if __name__ == "__main__":
    bot.run(CONFIG['TOKEN'])