import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import time
from datetime import datetime, timedelta
import os
import asyncio
from dotenv import load_dotenv
import asyncpg

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
CONFIG = {
    'TOKEN': os.getenv('DISCORD_BOT_TOKEN'),
    'DATABASE_URL': os.getenv('DATABASE_URL'),
    'MAX_LEVEL': 1000,
    'TEXT_XP_MIN': 5,
    'TEXT_XP_MAX': 10,
    'TEXT_COOLDOWN': 30,
    'VOICE_XP_PER_MINUTE': 5,
    'XP_PER_LEVEL': 100,
    'ADMIN_ALERT_ENABLED': True
}

if not CONFIG['TOKEN']:
    raise ValueError("Токен бота не найден! Установите переменную DISCORD_BOT_TOKEN")

if not CONFIG['DATABASE_URL']:
    raise ValueError("URL базы данных не найден! Установите переменную DATABASE_URL")

# Инициализация бота
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Пул соединений с БД
db_pool = None

# Хранилище данных (для кэша)
cooldowns = {}
voice_tracking = {}

# Цвета для эмбедов
COLORS = {
    'INFO': discord.Color.blue(),
    'SUCCESS': discord.Color.green(),
    'WARNING': discord.Color.orange(),
    'ERROR': discord.Color.red(),
    'MODERATION': discord.Color.purple(),
    'LEVEL_UP': discord.Color.gold(),
    'CREATE': discord.Color.green(),
    'DELETE': discord.Color.red(),
    'UPDATE': discord.Color.blue(),
    'BAN': discord.Color.dark_red(),
    'KICK': discord.Color.orange(),
    'VOICE': discord.Color.purple(),
    'MESSAGE': discord.Color.blurple()
}

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========

async def init_database():
    """Инициализация подключения к БД и создание таблиц"""
    global db_pool
    
    try:
        db_pool = await asyncpg.create_pool(
            CONFIG['DATABASE_URL'],
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        
        async with db_pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    text_xp INTEGER DEFAULT 0,
                    text_level INTEGER DEFAULT 1,
                    voice_xp INTEGER DEFAULT 0,
                    voice_level INTEGER DEFAULT 1,
                    total_xp INTEGER DEFAULT 0,
                    total_level INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Таблица настроек серверов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS server_settings (
                    guild_id BIGINT PRIMARY KEY,
                    notification_channel BIGINT,
                    log_channel BIGINT,
                    last_updated TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Индексы для оптимизации
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_total_xp ON users(total_xp DESC)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_text_xp ON users(text_xp DESC)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_voice_xp ON users(voice_xp DESC)')
            
        print("✅ База данных успешно инициализирована!")
        
    except Exception as e:
        print(f"⛔ Ошибка инициализации БД: {e}")
        raise

async def get_user_data(user_id):
    """Получение данных пользователя из БД"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                int(user_id)
            )
            
            if row:
                return dict(row)
            else:
                # Создаём нового пользователя
                await conn.execute('''
                    INSERT INTO users (user_id, text_xp, text_level, voice_xp, voice_level, total_xp, total_level)
                    VALUES ($1, 0, 1, 0, 1, 0, 1)
                ''', int(user_id))
                
                return {
                    'user_id': int(user_id),
                    'text_xp': 0,
                    'text_level': 1,
                    'voice_xp': 0,
                    'voice_level': 1,
                    'total_xp': 0,
                    'total_level': 1
                }
    except Exception as e:
        print(f"Ошибка получения данных пользователя: {e}")
        return {
            'user_id': int(user_id),
            'text_xp': 0,
            'text_level': 1,
            'voice_xp': 0,
            'voice_level': 1,
            'total_xp': 0,
            'total_level': 1
        }

async def save_user_data(user_id, data):
    """Сохранение данных пользователя в БД"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET text_xp = $2, text_level = $3, voice_xp = $4, voice_level = $5, 
                    total_xp = $6, total_level = $7, last_updated = NOW()
                WHERE user_id = $1
            ''', int(user_id), data['text_xp'], data['text_level'], 
                data['voice_xp'], data['voice_level'], data['total_xp'], data['total_level'])
    except Exception as e:
        print(f"Ошибка сохранения данных пользователя: {e}")

async def get_notification_channel(guild_id):
    """Получение канала уведомлений"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT notification_channel FROM server_settings WHERE guild_id = $1',
                int(guild_id)
            )
            return row['notification_channel'] if row else None
    except Exception as e:
        print(f"Ошибка получения канала уведомлений: {e}")
        return None

async def get_log_channel(guild_id):
    """Получение канала логов"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT log_channel FROM server_settings WHERE guild_id = $1',
                int(guild_id)
            )
            return row['log_channel'] if row else None
    except Exception as e:
        print(f"Ошибка получения канала логов: {e}")
        return None

async def set_notification_channel(guild_id, channel_id):
    """Установка канала уведомлений"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO server_settings (guild_id, notification_channel, last_updated)
                VALUES ($1, $2, NOW())
                ON CONFLICT (guild_id) 
                DO UPDATE SET notification_channel = $2, last_updated = NOW()
            ''', int(guild_id), int(channel_id))
    except Exception as e:
        print(f"Ошибка установки канала уведомлений: {e}")

async def set_log_channel(guild_id, channel_id):
    """Установка канала логов"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO server_settings (guild_id, log_channel, last_updated)
                VALUES ($1, $2, NOW())
                ON CONFLICT (guild_id) 
                DO UPDATE SET log_channel = $2, last_updated = NOW()
            ''', int(guild_id), int(channel_id))
    except Exception as e:
        print(f"Ошибка установки канала логов: {e}")

async def get_leaderboard(xp_type='total', limit=10):
    """Получение топа игроков"""
    try:
        field_map = {
            'text': 'text_xp',
            'voice': 'voice_xp',
            'total': 'total_xp'
        }
        
        field = field_map.get(xp_type, 'total_xp')
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                f'SELECT * FROM users ORDER BY {field} DESC LIMIT $1',
                limit
            )
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Ошибка получения топа: {e}")
        return []

# Расчет уровня по опыту
def calculate_level(xp):
    return min(xp // CONFIG['XP_PER_LEVEL'] + 1, CONFIG['MAX_LEVEL'])

# Добавление опыта
async def add_xp(user_id, xp, xp_type, guild=None):
    user_id = int(user_id)
    user = await get_user_data(user_id)
    
    old_level = user[f'{xp_type}_level']
    
    if xp_type == 'text':
        user['text_xp'] = max(0, user['text_xp'] + xp)
        user['text_level'] = calculate_level(user['text_xp'])
    elif xp_type == 'voice':
        user['voice_xp'] = max(0, user['voice_xp'] + xp)
        user['voice_level'] = calculate_level(user['voice_xp'])
    
    user['total_xp'] = user['text_xp'] + user['voice_xp']
    user['total_level'] = calculate_level(user['total_xp'])
    
    await save_user_data(user_id, user)
    
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
        
        notification_channel_id = await get_notification_channel(guild.id)
        if notification_channel_id:
            channel = bot.get_channel(int(notification_channel_id))
            if channel:
                await channel.send(embed=embed)
                return
        
        if guild.system_channel:
            await guild.system_channel.send(embed=embed)
            
    except Exception as e:
        print(f"Ошибка отправки уведомления о уровне: {e}")

# Улучшенная функция получения информации из аудит-логов
async def get_audit_log_info(guild, action, target=None):
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if target is None:
                return entry.user, entry.reason or "Не указана"
            elif hasattr(entry, 'target') and entry.target and entry.target.id == target.id:
                return entry.user, entry.reason or "Не указана"
    except Exception as e:
        print(f"Ошибка при получении аудит-лога: {e}")
    
    return None, "Не указана"

async def find_moderator_for_role_change(guild, target_user, role=None, is_add=True):
    """Улучшенная функция для поиска модератора при изменении ролей"""
    try:
        action = discord.AuditLogAction.member_role_update
        async for entry in guild.audit_logs(limit=5, action=action):
            if entry.target.id == target_user.id:
                time_diff = (datetime.now().astimezone() - entry.created_at).total_seconds()
                if time_diff < 10:
                    return entry.user, entry.reason or "Не указана"
    except Exception as e:
        print(f"Ошибка при поиске модератора для изменения ролей: {e}")
    
    return None, "Не указана"

async def send_admin_alert(guild, action, moderator, details):
    try:
        BOT_OWNER_ID = 852962557002252289
        
        owner = guild.owner
        bot_owner = await bot.fetch_user(BOT_OWNER_ID)
        
        alert_embed = discord.Embed(
            title="🚨 КРИТИЧЕСКОЕ СОБЫТИЕ",
            description=f"**Обнаружено подозрительное действие на сервере {guild.name}**",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        alert_embed.add_field(name="⚠️ Действие", value=action, inline=False)
        alert_embed.add_field(
            name="🤡 Уебан который тронул логи!",
            value=f"{moderator.mention} (`{moderator.name}` | ID: `{moderator.id}`)",
            inline=True
        )
        alert_embed.add_field(name="📋 Детали", value=details, inline=False)
        alert_embed.add_field(
            name="⏰ Время",
            value=f"<t:{int(datetime.now().timestamp())}:F>",
            inline=True
        )
        alert_embed.set_footer(text="Рекомендуется проверить действия администратора И ВЫЕБАТЬ ЕГО ЗА ЭТО!")
        
        if owner:
            try:
                await owner.send(embed=alert_embed)
                print(f"✅ Тревога отправлена владельцу сервера: {owner.name}")
            except discord.Forbidden:
                if guild.system_channel:
                    await guild.system_channel.send(f"{owner.mention}", embed=alert_embed)
        
        if bot_owner and bot_owner.id != owner.id:
            try:
                await bot_owner.send(embed=alert_embed)
                print(f"✅ Тревога отправлена создателю бота: {bot_owner.name}")
            except discord.Forbidden:
                print(f"⛔ Не удалось отправить тревогу создателю бота")
        
    except Exception as e:
        print(f"⛔ Ошибка отправки тревоги: {e}")

# Создание карточки уровня
def create_level_embed(user, member):
    data = user
    
    if data['total_level'] >= 500:
        color = discord.Color.gold()
        rank_emoji = "🏆"
        rank_name = "LEGEND"
    elif data['total_level'] >= 250:
        color = discord.Color.purple()
        rank_emoji = "⚡"
        rank_name = "MASTER"
    elif data['total_level'] >= 100:
        color = discord.Color.blue()
        rank_emoji = "🔥"
        rank_name = "EXPERT"
    elif data['total_level'] >= 50:
        color = discord.Color.green()
        rank_emoji = "⭐"
        rank_name = "ADVANCED"
    else:
        color = discord.Color.light_gray()
        rank_emoji = "🌱"
        rank_name = "BEGINNER"
    
    embed = discord.Embed(color=color, timestamp=datetime.now())
    embed.set_author(
        name=f"📊 Профиль {member.display_name}",
        icon_url=member.display_avatar.url
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    
    embed.add_field(
        name=f"`{rank_emoji} Ранг: {rank_name}`",
        value=f"-# **Общий уровень:** `{data['total_level']}`\n"
              f"-# **Всего опыта:** `{data['total_xp']:,} XP`\n"
              f"-# **Прогресс:** `{data['total_xp'] % CONFIG['XP_PER_LEVEL']}/{CONFIG['XP_PER_LEVEL']} XP`",
        inline=False
    )
    
    embed.add_field(
        name="`💬 Текстовый чат`",
        value=f"-# **Уровень:** `{data['text_level']}`\n"
              f"-# **Опыт:** `{data['text_xp']:,} XP`",
        inline=True
    )
    
    embed.add_field(
        name="`🎤 Голосовой чат`",
        value=f"-# **Уровень:** `{data['voice_level']}`\n"
              f"-# **Опыт:** `{data['voice_xp']:,} XP`",
        inline=True
    )
    
    embed.set_footer(text=f"by crysix | Обновлено", icon_url=bot.user.display_avatar.url)
    
    return embed

# Создание топа
async def create_leaderboard_embed(guild, top_type='total'):
    if top_type == 'text':
        title = "💬 Топ-10 по текстовому чату"
        field = 'text'
    elif top_type == 'voice':
        title = "🎤 Топ-10 по голосовому чату"
        field = 'voice'
    else:
        title = "⭐ Топ-10 общий рейтинг"
        field = 'total'
    
    sorted_users = await get_leaderboard(top_type, 10)
    
    embed = discord.Embed(title=title, color=discord.Color.gold(), timestamp=datetime.now())
    
    medals = ["🥇", "🥈", "🥉"]
    description = ""
    
    for idx, data in enumerate(sorted_users):
        try:
            member = guild.get_member(int(data['user_id']))
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
    embed.set_footer(text=f"Обновлено", icon_url=bot.user.display_avatar.url)
    
    return embed

# Создание embed статистики пользователя
async def create_user_stats_embed(member):
    joined_days = (datetime.now().replace(tzinfo=None) - member.joined_at.replace(tzinfo=None)).days
    created_days = (datetime.now().replace(tzinfo=None) - member.created_at.replace(tzinfo=None)).days
    
    roles = [role for role in member.roles if role != member.guild.default_role]
    top_role = member.top_role
    
    embed = discord.Embed(
        title=f"📈 Статистика {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    
    status_dict = {
        'online': '🟢 В сети',
        'idle': '🟡 Неактивен', 
        'dnd': '🔴 Не беспокоить',
        'offline': '⚫ Не в сети'
    }
    
    current_status = str(member.status)
    status_text = status_dict.get(current_status, '⚫ Не в сети')
    
    embed.add_field(
        name="👤 Основная информация",
        value=f"**Имя:** `{member.name}`\n"
              f"**ID:** `{member.id}`\n"
              f"**Статус:** {status_text}\n"
              f"**Бот:** {'✅' if member.bot else '⛔'}\n"
              f"**Отображаемое имя:** `{member.display_name}`",
        inline=False
    )
    
    embed.add_field(
        name="📅 Даты",
        value=f"**Присоединился:** <t:{int(member.joined_at.timestamp())}:R>\n"
              f"**На сервере:** `{joined_days}` дней\n"
              f"**Аккаунт создан:** <t:{int(member.created_at.timestamp())}:R>\n"
              f"**Возраст аккаунта:** `{created_days}` дней",
        inline=False
    )
    
    roles_text = f"**Главная роль:** {top_role.mention}\n**Всего ролей:** `{len(roles)}`"
    if roles:
        roles_text += f"\n**Роли:** {', '.join([role.mention for role in roles[:3]])}"
        if len(roles) > 3:
            roles_text += f" *... и еще {len(roles) - 3}*"
    
    embed.add_field(
        name="🎭 Роли",
        value=roles_text,
        inline=False
    )
    
    activity_text = "⛔ Не активно"
    if member.activity:
        activity = member.activity
        try:
            if isinstance(activity, discord.Game):
                activity_text = f"🎮 Играет в **{activity.name}**"
            elif isinstance(activity, discord.Streaming):
                activity_text = f"📺 Стримит **{activity.game}**"
            elif isinstance(activity, discord.Spotify):
                activity_text = f"🎵 Слушает **{activity.title}**"
            elif isinstance(activity, discord.CustomActivity):
                activity_text = f"💬 **{activity.name}**"
            else:
                activity_text = f"📱 **{activity.name}**"
        except:
            activity_text = "📱 Активность"
    
    embed.add_field(
        name="📊 Активность",
        value=activity_text,
        inline=True
    )
    
    # ИСПРАВЛЕНО: добавлен await
    user_level_data = await get_user_data(member.id)
    level_text = f"**Общий уровень:** `{user_level_data['total_level']}`\n"
    level_text += f"**Текстовый:** `{user_level_data['text_level']}`\n"
    level_text += f"**Голосовой:** `{user_level_data['voice_level']}`\n"
    level_text += f"**Всего опыта:** `{user_level_data['total_xp']:,} XP`"
    
    embed.add_field(
        name="📈 Уровни",
        value=level_text,
        inline=True
    )
    
    extra_info = ""
    if member.premium_since:
        boost_days = (datetime.now().replace(tzinfo=None) - member.premium_since.replace(tzinfo=None)).days
        extra_info += f"🚀 **Бустит сервер:** {boost_days} дней\n"
    
    if member.is_timed_out():
        timeout_until = member.timed_out_until
        if timeout_until:
            timeout_left = timeout_until - datetime.now().astimezone()
            hours_left = int(timeout_left.total_seconds() // 3600)
            minutes_left = int((timeout_left.total_seconds() % 3600) // 60)
            extra_info += f"⏰ **В таймауте:** {hours_left}ч {minutes_left}м\n"
    
    if member.guild_permissions.administrator:
        extra_info += "👑 **Администратор**\n"
    elif member.guild_permissions.manage_messages:
        extra_info += "🛡️ **Модератор**\n"
    
    if extra_info:
        embed.add_field(
            name="💎 Дополнительно",
            value=extra_info.strip(),
            inline=False
        )
    
    embed.set_footer(text=f"ID: {member.id} | Запрошено")
    
    return embed

# Событие: бот готов
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен!')
    
    await init_database()
    
    for guild in bot.guilds:
        perms = guild.me.guild_permissions
        if not perms.view_audit_log:
            print(f'⚠️ Внимание: Бот не имеет прав на просмотр аудит-логов на сервере {guild.name}')
    
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} команд')
    except Exception as e:
        print(f'Ошибка синхронизации команд: {e}')
    
    voice_xp_task.start()

# Обработка сообщений
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return await bot.process_commands(message)
    
    user_id = str(message.author.id)
    current_time = time.time()
    
    if user_id in cooldowns:
        if current_time - cooldowns[user_id] < CONFIG['TEXT_COOLDOWN']:
            return await bot.process_commands(message)
    
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
    
    if before.channel is None and after.channel is not None:
        voice_tracking[user_id] = {
            'start_time': time.time(),
            'guild_id': member.guild.id
        }
        await log_action(
            member.guild,
            "🎤 Вход в голосовой канал",
            f"**Канал:** {after.channel.mention}",
            COLORS['VOICE'],
            member
        )
    
    elif before.channel is not None and after.channel is None:
        if user_id in voice_tracking:
            tracking_data = voice_tracking[user_id]
            join_time = tracking_data['start_time']
            duration = time.time() - join_time
            minutes = int(duration / 60)
            
            if minutes > 0:
                xp = minutes * CONFIG['VOICE_XP_PER_MINUTE']
                await add_xp(user_id, xp, 'voice', member.guild)
            
            await log_action(
                member.guild,
                "🎤 Выход из голосового канала",
                f"**Канал:** {before.channel.mention}\n**Продолжительность:** `{minutes} минут`",
                COLORS['VOICE'],
                member
            )
            
            del voice_tracking[user_id]
    
    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        await log_action(
            member.guild,
            "🎤 Переход между каналами",
            f"**Из:** {before.channel.mention}\n**В:** {after.channel.mention}",
            COLORS['VOICE'],
            member
        )

@tasks.loop(minutes=1)
async def voice_xp_task():
    for user_id, tracking_data in list(voice_tracking.items()):
        try:
            guild = bot.get_guild(tracking_data['guild_id'])
            if guild:
                await add_xp(user_id, CONFIG['VOICE_XP_PER_MINUTE'], 'voice', guild)
        except Exception as e:
            print(f"Ошибка в voice_xp_task: {e}")

# ========== ПОЛНАЯ СИСТЕМА ЛОГИРОВАНИЯ ==========

@bot.event
async def on_member_join(member):
    account_age = (datetime.now().replace(tzinfo=None) - member.created_at.replace(tzinfo=None)).days
    await log_action(
        member.guild,
        "✅ Участник присоединился",
        f"**Аккаунт создан:** `{account_age}` дней назад",
        COLORS['SUCCESS'],
        target=member
    )

@bot.event
async def on_member_remove(member):
    await log_action(
        member.guild,
        "🚪 Участник покинул",
        f"**Присоединился:** <t:{int(member.joined_at.timestamp())}:R>",
        COLORS['WARNING'],
        target=member
    )

@bot.event
async def on_member_ban(guild, user):
    moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.ban, user)
    await log_action(
        guild,
        "🔨 Бан участника",
        f"**Пользователь забанен на сервере**",
        COLORS['BAN'],
        target=user,
        moderator=moderator,
        reason=reason
    )

@bot.event
async def on_member_unban(guild, user):
    moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.unban, user)
    await log_action(
        guild,
        "🔓 Разбан участника",
        f"**С пользователя снят бан**",
        COLORS['SUCCESS'],
        target=user,
        moderator=moderator,
        reason=reason
    )

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added_roles = [role for role in after.roles if role not in before.roles]
        removed_roles = [role for role in before.roles if role not in after.roles]
        
        for role in added_roles:
            moderator, reason = await find_moderator_for_role_change(after.guild, after, role, is_add=True)
            await log_action(
                after.guild,
                "✅ Роль выдана",
                f"**Роль:** {role.mention}",
                COLORS['SUCCESS'],
                target=after,
                moderator=moderator,
                reason=reason,
                extra_fields={"🎭 Роль": f"{role.mention} (`{role.name}`)"}
            )
        
        for role in removed_roles:
            moderator, reason = await find_moderator_for_role_change(after.guild, after, role, is_add=False)
            await log_action(
                after.guild,
                "⛔ Роль изъята",
                f"**Роль:** {role.mention}",
                COLORS['ERROR'],
                target=after,
                moderator=moderator,
                reason=reason,
                extra_fields={"🎭 Роль": f"{role.mention} (`{role.name}`)"}
            )
    
    if before.nick != after.nick:
        moderator, reason = await get_audit_log_info(after.guild, discord.AuditLogAction.member_update, after)
        await log_action(
            after.guild,
            "📝 Изменен никнейм",
            f"**Был:** `{before.nick or before.display_name}`\n**Стал:** `{after.nick or after.display_name}`",
            COLORS['UPDATE'],
            target=after,
            moderator=moderator,
            reason=reason
        )
    
    if before.timed_out_until != after.timed_out_until:
        moderator, reason = await get_audit_log_info(after.guild, discord.AuditLogAction.member_update, after)
        if after.timed_out_until:
            duration = (after.timed_out_until - datetime.now().astimezone()).total_seconds() / 60
            await log_action(
                after.guild,
                "⏰ Таймаут участника",
                f"**Длительность:** `{duration:.1f}` минут",
                COLORS['WARNING'],
                target=after,
                moderator=moderator,
                reason=reason
            )
        else:
            await log_action(
                after.guild,
                "🔊 Снятие таймаута",
                f"**Таймаут досрочно снят**",
                COLORS['SUCCESS'],
                target=after,
                moderator=moderator,
                reason=reason
            )

@bot.event
async def on_raw_message_delete(payload):
    # Проверяем, было ли удалено сообщение в гильдии
    if not payload.guild_id:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    # Получаем информацию о сообщении из кэша
    message = payload.cached_message
    
    # Если сообщение есть в кэше и это сообщение бота
    if message and message.author.id == bot.user.id:
        # Ищем кто удалил сообщение
        moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.message_delete)
        
        if moderator and moderator.guild_permissions.administrator:
            # Если администратор удалил лог - отправляем тревогу
            if CONFIG['ADMIN_ALERT_ENABLED']:
                await send_admin_alert(
                    guild,
                    "Удаление логов бота администратором",
                    moderator,
                    f"**Канал:** <#{payload.channel_id}>\n"
                    f"**Удаленное сообщение:** {message.content[:200] if message.content else 'Сообщение с вложениями'}\n"
                    f"**Причина:** {reason}\n\n"
                    f"🚨 **ВНИМАНИЕ:** Администратор удалил логи системы! Возможно, он пытается скрыть свои действия."
                )
        
        # Логируем удаление сообщения бота (логов)
        content = message.content or "*Сообщение без текста*"
        attachments_info = f"\n**Вложения:** {len(message.attachments)}" if message.attachments else ""
        
        await log_action(
            guild,
            "🗑️ Удаление логов бота",
            f"**Канал:** <#{payload.channel_id}>\n**Содержимое:** {content[:500]}{attachments_info}",
            COLORS['DELETE'],
            target=message.author,
            moderator=moderator,
            reason=reason,
            extra_fields={"💬 Канал": f"<#{payload.channel_id}>"}
        )
        return
    
    # Если сообщение не в кэше, но мы знаем что это был канал логов
    channel = bot.get_channel(payload.channel_id)
    if channel and hasattr(channel, 'name') and 'log' in channel.name.lower():
        # Это могло быть сообщение бота в канале логов
        moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.message_delete)
        
        if moderator and moderator.guild_permissions.administrator:
            if CONFIG['ADMIN_ALERT_ENABLED']:
                await send_admin_alert(
                    guild,
                    "Удаление логов бота администратором",
                    moderator,
                    f"**Канал:** {channel.mention}\n"
                    f"**Сообщение ID:** {payload.message_id}\n"
                    f"**Причина:** {reason}\n\n"
                    f"🚨 **ВНИМАНИЕ:** Администратор удалил логи системы! Сообщение не было в кэше."
                )

# Оставляем старую функцию для обычных сообщений
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    
    content = message.content or "*Сообщение без текста*"
    attachments_info = f"\n**Вложения:** {len(message.attachments)}" if message.attachments else ""
    
    moderator, reason = await get_audit_log_info(message.guild, discord.AuditLogAction.message_delete)
    
    await log_action(
        message.guild,
        "🗑️ Удаление сообщения",
        f"**Канал:** {message.channel.mention}\n**Содержимое:** {content[:500]}{attachments_info}",
        COLORS['DELETE'],
        target=message.author,
        moderator=moderator,
        reason=reason,
        extra_fields={"💬 Канал": message.channel.mention}
    )

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    
    try:
        before_content = before.content[:300] + "..." if len(before.content) > 300 else before.content or "*пустое*"
        after_content = after.content[:300] + "..." if len(after.content) > 300 else after.content or "*пустое*"
        
        description = f"**Канал:** {before.channel.mention}\n**Ссылка:** [Перейти]({after.jump_url})\n**Было:** {before_content}\n**Стало:** {after_content}"
        
        await log_action(
            before.guild,
            "✏️ Редактирование",
            description,
            COLORS['UPDATE'],
            target=before.author,
            moderator=before.author,
            extra_fields={"💬 Канал": before.channel.mention}
        )
    except Exception as e:
        print(f"Ошибка логирования редактирования: {e}")
        
@bot.event
async def on_raw_bulk_message_delete(payload):
    if not payload.guild_id:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    
    # Проверяем, были ли среди удаленных сообщения бота
    bot_messages = []
    for message in payload.cached_messages:
        if message.author.id == bot.user.id:
            bot_messages.append(message)
    
    if bot_messages:
        # Ищем кто удалил сообщения
        moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.message_bulk_delete)
        
        if moderator and moderator.guild_permissions.administrator:
            # Если администратор удалил логи - отправляем тревогу
            if CONFIG['ADMIN_ALERT_ENABLED']:
                await send_admin_alert(
                    guild,
                    "Массовое удаление логов бота администратором",
                    moderator,
                    f"**Канал:** {channel.mention}\n"
                    f"**Удалено сообщений бота:** {len(bot_messages)}\n"
                    f"**Всего удалено сообщений:** {len(payload.cached_messages)}\n"
                    f"**Причина:** {reason}\n\n"
                    f"🚨 **КРИТИЧЕСКАЯ СИТУАЦИЯ:** Администратор массово удаляет логи системы! Требуется немедленное вмешательство."
                )

@bot.event
async def on_bulk_message_delete(messages):
    if not messages:
        return
    
    guild = messages[0].guild
    channel = messages[0].channel
    
    # Проверяем, были ли среди удаленных сообщения бота
    bot_messages = [msg for msg in messages if msg.author.id == bot.user.id]
    
    if bot_messages:
        # Ищем кто удалил сообщения
        moderator, reason = await get_audit_log_info(guild, discord.AuditLogAction.message_bulk_delete)
        
        if moderator and moderator.guild_permissions.administrator:
            # Если администратор удалил логи - отправляем тревогу
            if CONFIG['ADMIN_ALERT_ENABLED']:
                await send_admin_alert(
                    guild,
                    "Массовое удаление логов бота администратором",
                    moderator,
                    f"**Канал:** {channel.mention}\n"
                    f"**Удалено сообщений бота:** {len(bot_messages)}\n"
                    f"**Всего удалено сообщений:** {len(messages)}\n"
                    f"**Причина:** {reason}\n\n"
                    f"🚨 **КРИТИЧЕСКАЯ СИТУАЦИЯ:** Администратор массово удаляет логи системы! Требуется немедленное вмешательство."
                )
    
    users = {}
    for msg in messages:
        if not msg.author.bot:
            users[msg.author.id] = users.get(msg.author.id, 0) + 1
    
    users_text = "\n".join([f"• <@{uid}>: `{count}` сообщений" for uid, count in list(users.items())[:5]])
    if len(users) > 5:
        users_text += f"\n• ... и еще {len(users) - 5} участников"
    
    await log_action(
        guild,
        "💥 Массовое удаление",
        f"**Канал:** {channel.mention}\n**Сообщений:** `{len(messages)}`\n**Затронутые участники:**\n{users_text}",
        COLORS['ERROR'],
        moderator=moderator,
        reason=reason,
        extra_fields={"💬 Канал": channel.mention}
    )

@bot.event
async def on_guild_channel_create(channel):
    moderator, reason = await get_audit_log_info(channel.guild, discord.AuditLogAction.channel_create)
    channel_type = "💬 Текстовый" if isinstance(channel, discord.TextChannel) else "🎤 Голосовой" if isinstance(channel, discord.VoiceChannel) else "📁 Категория"
    
    await log_action(
        channel.guild,
        "✅ Создание канала",
        f"**Тип:** {channel_type}\n**Название:** {channel.mention}",
        COLORS['CREATE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"📺 Канал": f"{channel.mention} (`{channel.name}`)"}
    )

@bot.event
async def on_guild_channel_delete(channel):
    moderator, reason = await get_audit_log_info(channel.guild, discord.AuditLogAction.channel_delete)
    channel_type = "💬 Текстовый" if isinstance(channel, discord.TextChannel) else "🎤 Голосовой" if isinstance(channel, discord.VoiceChannel) else "📁 Категория"
    
    await log_action(
        channel.guild,
        "⛔ Удаление канала",
        f"**Тип:** {channel_type}\n**Название:** `{channel.name}`",
        COLORS['DELETE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"📺 Канал": f"`{channel.name}`"}
    )

@bot.event
async def on_guild_channel_update(before, after):
    changes = []
    
    if before.name != after.name:
        changes.append(f"**Название:** `{before.name}` → `{after.name}`")
    
    if before.position != after.position:
        changes.append(f"**Позиция:** `{before.position}` → `{after.position}`")
    
    if hasattr(before, 'topic') and hasattr(after, 'topic') and before.topic != after.topic:
        changes.append(f"**Топик:** `{before.topic or 'Нет'}` → `{after.topic or 'Нет'}`")
    
    if hasattr(before, 'slowmode_delay') and hasattr(after, 'slowmode_delay') and before.slowmode_delay != after.slowmode_delay:
        changes.append(f"**Слоумод:** `{before.slowmode_delay}`с → `{after.slowmode_delay}`с")
    
    if changes:
        moderator, reason = await get_audit_log_info(after.guild, discord.AuditLogAction.channel_update)
        await log_action(
            after.guild,
            "⚙️ Обновление канала",
            "\n".join(changes),
            COLORS['UPDATE'],
            moderator=moderator,
            reason=reason,
            extra_fields={"📺 Канал": f"{after.mention} (`{after.name}`)"}
        )

@bot.event
async def on_guild_role_create(role):
    moderator, reason = await get_audit_log_info(role.guild, discord.AuditLogAction.role_create)
    
    perms = []
    if role.permissions.administrator:
        perms.append("Администратор")
    if role.permissions.manage_guild:
        perms.append("Управление сервером")
    if role.permissions.ban_members:
        perms.append("Баны")
    if role.permissions.kick_members:
        perms.append("Кики")
    
    perms_text = ", ".join(perms) if perms else "Обычные права"
    
    await log_action(
        role.guild,
        "✅ Создание роли",
        f"**Роль:** {role.mention}\n**Права:** {perms_text}",
        COLORS['CREATE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"🎭 Роль": f"{role.mention} (`{role.name}`)"}
    )

@bot.event
async def on_guild_role_delete(role):
    moderator, reason = await get_audit_log_info(role.guild, discord.AuditLogAction.role_delete)
    
    await log_action(
        role.guild,
        "⛔ Удаление роли",
        f"**Роль:** `{role.name}`\n**ID:** `{role.id}`",
        COLORS['DELETE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"🎭 Роль": f"`{role.name}`"}
    )

@bot.event
async def on_guild_role_update(before, after):
    changes = []
    
    if before.name != after.name:
        changes.append(f"**Название:** `{before.name}` → `{after.name}`")
    
    if before.color != after.color:
        changes.append(f"**Цвет:** `{before.color}` → `{after.color}`")
    
    if before.position != after.position:
        changes.append(f"**Позиция:** `{before.position}` → `{after.position}`")
    
    if before.permissions != after.permissions:
        changed_perms = []
        for perm, value in after.permissions:
            if getattr(before.permissions, perm) != value:
                changed_perms.append(f"{'✅' if value else '⛔'} {perm}")
        
        if changed_perms:
            changes.append("**Права:**\n" + "\n".join(changed_perms[:5]))
    
    if changes:
        moderator, reason = await get_audit_log_info(after.guild, discord.AuditLogAction.role_update)
        await log_action(
            after.guild,
            "⚙️ Обновление роли",
            "\n".join(changes),
            COLORS['UPDATE'],
            moderator=moderator,
            reason=reason,
            extra_fields={"🎭 Роль": f"{after.mention} (`{after.name}`)"}
        )

@bot.event
async def on_guild_update(before, after):
    changes = []
    
    if before.name != after.name:
        changes.append(f"**Название:** `{before.name}` → `{after.name}`")
    
    if before.afk_channel != after.afk_channel:
        changes.append(f"**AFK канал:** `{before.afk_channel}` → `{after.afk_channel}`")
    
    if before.icon != after.icon:
        changes.append("**Иконка сервера изменена**")
    
    if before.banner != after.banner:
        changes.append("**Баннер сервера изменен**")
    
    if changes:
        moderator, reason = await get_audit_log_info(after, discord.AuditLogAction.guild_update)
        await log_action(
            after,
            "⚙️ Обновление сервера",
            "\n".join(changes),
            COLORS['UPDATE'],
            moderator=moderator,
            reason=reason
        )

@bot.event
async def on_invite_create(invite):
    await log_action(
        invite.guild,
        "📨 Создание инвайта",
        f"**Канал:** {invite.channel.mention}\n**Код:** `{invite.code}`",
        COLORS['CREATE'],
        target=invite.inviter,
        extra_fields={"🔗 Инвайт": f"`{invite.code}`", "💬 Канал": invite.channel.mention}
    )

@bot.event
async def on_invite_delete(invite):
    moderator, reason = await get_audit_log_info(invite.guild, discord.AuditLogAction.invite_delete)
    
    await log_action(
        invite.guild,
        "📨 Удаление инвайта",
        f"**Код:** `{invite.code}`\n**Канал:** {invite.channel.mention}",
        COLORS['DELETE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"🔗 Инвайт": f"`{invite.code}`", "💬 Канал": invite.channel.mention}
    )

@bot.event
async def on_webhooks_update(channel):
    moderator, reason = await get_audit_log_info(channel.guild, discord.AuditLogAction.webhook_create)
    await log_action(
        channel.guild,
        "🔗 Обновление вебхуков",
        f"**Канал:** {channel.mention}",
        COLORS['UPDATE'],
        moderator=moderator,
        reason=reason,
        extra_fields={"💬 Канал": channel.mention}
    )

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    # Пользователь зашел в голосовой канал
    if before.channel is None and after.channel is not None:
        await log_action(
            member.guild,
            "🎤 Вход в голосовой канал",
            f"**Канал:** {after.channel.mention}\n**Категория:** `{after.channel.category.name if after.channel.category else 'Нет'}`",
            COLORS['VOICE'],
            member
        )
    
    # Пользователь вышел из голосового канала
    elif before.channel is not None and after.channel is None:
        await log_action(
            member.guild,
            "🎤 Выход из голосового канала",
            f"**Канал:** {before.channel.mention}",
            COLORS['VOICE'],
            member
        )
    
    # Пользователь перешел между каналами
    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        await log_action(
            member.guild,
            "🎤 Переход между каналами",
            f"**Из:** {before.channel.mention}\n**В:** {after.channel.mention}",
            COLORS['VOICE'],
            member
        )

# Улучшенная функция логирования
# Логирование действий
async def log_action(guild, action, description, color=COLORS['INFO'], target=None, moderator=None, reason=None, extra_fields=None):
    try:
        log_channel_id = await get_log_channel(guild.id)  # БЫЛО: get_log_channel(guild.id) БЕЗ await
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
            embed.add_field(
                name="```🎯 Объект действия```",
                value=f"{target.mention} (ID: {target.id})\nИмя: {target.name}",
                inline=True
            )
        
        if moderator:
            embed.add_field(
                name="```👑 Исполнитель```",
                value=f"{moderator.mention} (ID: {moderator.id})\nИмя: {moderator.name}", 
                inline=True
            )
        
        if reason and reason != "Не указана":
            embed.add_field(name="📋 Причина", value=reason, inline=False)
        
        if extra_fields:
            for field_name, field_value in extra_fields.items():
                embed.add_field(name=field_name, value=field_value, inline=False)
        
        embed.set_footer(text=f"ID: {target.id if target else 'DEMON'}")
        
        await asyncio.sleep(0.5)
        await channel.send(embed=embed)
        
    except Exception as e:
        print(f"Ошибка логирования: {e}")

# ========== КОМАНДЫ ==========

@bot.tree.command(name="уровень", description="Показать вашу карточку с уровнем")
async def level_command(interaction: discord.Interaction):
    try:
        data = await get_user_data(interaction.user.id)
        embed = create_level_embed(data, interaction.user)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде уровень: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="профиль", description="Посмотреть профиль пользователя")
@app_commands.describe(пользователь="Выберите пользователя")
async def profile_command(interaction: discord.Interaction, пользователь: discord.Member = None):
    try:
        target = пользователь or interaction.user
        data = await get_user_data(target.id)
        embed = create_level_embed(data, target)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде профиль: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="топ", description="Топ-10 игроков общий рейтинг")
async def top_command(interaction: discord.Interaction):
    try:
        embed = await create_leaderboard_embed(interaction.guild, 'total')
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде топ: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="топ_текст", description="Топ-10 игроков по текстовому чату")
async def top_text_command(interaction: discord.Interaction):
    try:
        embed = await create_leaderboard_embed(interaction.guild, 'text')
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде топ_текст: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="топ_войс", description="Топ-10 игроков по голосовому чату")
async def top_voice_command(interaction: discord.Interaction):
    try:
        embed = await create_leaderboard_embed(interaction.guild, 'voice')
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде топ_войс: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="статистика", description="Показать подробную статистику пользователя")
@app_commands.describe(пользователь="Выберите пользователя")
async def stats_command(interaction: discord.Interaction, пользователь: discord.Member = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔ У вас нет прав администратора!", ephemeral=True)
        return
    
    try:
        target = пользователь or interaction.user
        embed = await create_user_stats_embed(target)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде статистика: {e}")
        await interaction.response.send_message("⛔ Произошла ошибка", ephemeral=True)

@bot.tree.command(name="бан", description="Забанить пользователя")
@app_commands.describe(
    пользователь="Пользователь для бана",
    причина="Причина бана",
    удалить_сообщения="Удалить сообщения за последние дни"
)
@app_commands.choices(удалить_сообщения=[
    app_commands.Choice(name="Не удалять", value="0"),
    app_commands.Choice(name="1 день", value="1"),
    app_commands.Choice(name="7 дней", value="7"),
])
async def ban_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    причина: str = "Не указана",
    удалить_сообщения: app_commands.Choice[str] = None
):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("⛔ У вас нет прав для бана!", ephemeral=True)
        return
    
    if пользователь == interaction.user:
        await interaction.response.send_message("⛔ Вы не можете забанить себя!", ephemeral=True)
        return
    
    if пользователь == bot.user:
        await interaction.response.send_message("⛔ Я не могу забанить себя!", ephemeral=True)
        return
    
    try:
        delete_days = int(удалить_сообщения.value) if удалить_сообщения else 0
        
        await пользователь.ban(reason=причина, delete_message_days=delete_days)
        
        embed = discord.Embed(
            title="🔨 Пользователь забанен",
            color=COLORS['BAN'],
            timestamp=datetime.now()
        )
        embed.add_field(name="🎯 Объект действия", value=f"{пользователь.mention} (`{пользователь.id}`)", inline=True)
        embed.add_field(name="👑 Исполнитель", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Причина", value=причина, inline=False)
        if delete_days > 0:
            embed.add_field(name="🗑️ Удалено сообщений", value=f"За последние {delete_days} дней", inline=True)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"⛔ Ошибка при бане: {str(e)}", ephemeral=True)

@bot.tree.command(name="кик", description="Кикнуть пользователя")
@app_commands.describe(
    пользователь="Пользователь для кика",
    причина="Причина кика"
)
async def kick_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    причина: str = "Не указана"
):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("⛔ У вас нет прав для кика!", ephemeral=True)
        return
    
    if пользователь == interaction.user:
        await interaction.response.send_message("⛔ Вы не можете кикнуть себя!", ephemeral=True)
        return
    
    if пользователь == bot.user:
        await interaction.response.send_message("⛔ Я не могу кикнуть себя!", ephemeral=True)
        return
    
    try:
        await пользователь.kick(reason=причина)
        
        embed = discord.Embed(
            title="👢 Пользователь кикнут",
            color=COLORS['KICK'],
            timestamp=datetime.now()
        )
        embed.add_field(name="🎯 Объект действия", value=f"{пользователь.mention} (`{пользователь.id}`)", inline=True)
        embed.add_field(name="👑 Исполнитель", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Причина", value=причина, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"⛔ Ошибка при кике: {str(e)}", ephemeral=True)

@bot.tree.command(name="таймаут", description="Выдать таймаут пользователю")
@app_commands.describe(
    пользователь="Пользователь для таймаута",
    длительность="Длительность таймаута в минутах",
    причина="Причина таймаута"
)
async def timeout_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    длительность: int,
    причина: str = "Не указана"
):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("⛔ У вас нет прав для выдачи таймаута!", ephemeral=True)
        return
    
    if пользователь == interaction.user:
        await interaction.response.send_message("⛔ Вы не можете выдать таймаут себе!", ephemeral=True)
        return
    
    if пользователь == bot.user:
        await interaction.response.send_message("⛔ Я не могу выдать таймаут себе!", ephemeral=True)
        return
    
    try:
        duration = timedelta(minutes=длительность)
        await пользователь.timeout(duration, reason=причина)
        
        embed = discord.Embed(
            title="⏰ Пользователь в таймауте",
            color=COLORS['WARNING'],
            timestamp=datetime.now()
        )
        embed.add_field(name="🎯 Объект действия", value=f"{пользователь.mention} (`{пользователь.id}`)", inline=True)
        embed.add_field(name="👑 Исполнитель", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏱️ Длительность", value=f"{длительность} минут", inline=True)
        embed.add_field(name="📋 Причина", value=причина, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"⛔ Ошибка при выдаче таймаута: {str(e)}", ephemeral=True)

@bot.tree.command(name="размут", description="Снять таймаут с пользователя")
@app_commands.describe(
    пользователь="Пользователь для размута",
    причина="Причина размута"
)
async def unmute_command(
    interaction: discord.Interaction,
    пользователь: discord.Member,
    причина: str = "Не указана"
):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("⛔ У вас нет прав для снятия таймаута!", ephemeral=True)
        return
    
    try:
        await пользователь.timeout(None, reason=причина)
        
        embed = discord.Embed(
            title="🔊 Таймаут снят",
            color=COLORS['SUCCESS'],
            timestamp=datetime.now()
        )
        embed.add_field(name="🎯 Объект действия", value=f"{пользователь.mention} (`{пользователь.id}`)", inline=True)
        embed.add_field(name="👑 Исполнитель", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Причина", value=причина, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"⛔ Ошибка при снятии таймаута: {str(e)}", ephemeral=True)

@bot.tree.command(name="очистить", description="Очистить сообщения в канале")
@app_commands.describe(
    количество="Количество сообщений для удаления (макс. 100)",
    пользователь="Очистить сообщения только от этого пользователя"
)
async def clear_command(
    interaction: discord.Interaction,
    количество: int = 10,
    пользователь: discord.Member = None
):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("⛔ У вас нет прав для управления сообщениями!", ephemeral=True)
        return
    
    if количество < 1 or количество > 100:
        await interaction.response.send_message("⛔ Количество должно быть от 1 до 100!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        def check(msg):
            if пользователь:
                return msg.author == пользователь and not msg.pinned
            return not msg.pinned
        
        deleted = await interaction.channel.purge(limit=количество, check=check)
        
        embed = discord.Embed(
            title="🧹 Очистка сообщений",
            description=f"Удалено **{len(deleted)}** сообщений в {interaction.channel.mention}",
            color=COLORS['SUCCESS'],
            timestamp=datetime.now()
        )
        
        if пользователь:
            embed.add_field(name="👤 Фильтр", value=f"Только от {пользователь.mention}", inline=True)
        
        embed.add_field(name="👑 Исполнитель", value=interaction.user.mention, inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        await asyncio.sleep(5)
        await interaction.delete_original_response()
        
    except Exception as e:
        await interaction.followup.send(f"⛔ Ошибка при очистке: {str(e)}", ephemeral=True)

@bot.tree.command(name="установить_канал", description="Установить канал для уведомлений")
@app_commands.describe(канал="Выберите текстовый канал")
async def set_channel_command(interaction: discord.Interaction, канал: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔ У вас нет прав!", ephemeral=True)
        return
    
    await set_notification_channel(interaction.guild.id, канал.id)
    
    embed = discord.Embed(
        description=f"✅ Канал уведомлений установлен: {канал.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="установить_логи", description="Установить канал для логов")
@app_commands.describe(канал="Выберите текстовый канал")
async def set_logs_command(interaction: discord.Interaction, канал: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔ У вас нет прав!", ephemeral=True)
        return
    
    await set_log_channel(interaction.guild.id, канал.id)
    
    embed = discord.Embed(
        description=f"✅ Канал логов установлен: {канал.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="дать_уровень", description="Выдать опыт пользователю")
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
        await interaction.response.send_message("⛔ У вас нет прав!", ephemeral=True)
        return
    
    if количество < 1:
        await interaction.response.send_message("⛔ Количество должно быть положительным!", ephemeral=True)
        return
    
    await add_xp(пользователь.id, количество, тип.value, interaction.guild)
    
    type_name = "текстовый" if тип.value == "text" else "голосовой"
    
    embed = discord.Embed(
        description=f"✅ Выдано **{количество}** XP ({type_name}) пользователю {пользователь.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="логи_инфо", description="Показать информацию о настройках логов")
async def logs_info_command(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    embed = discord.Embed(
        title="📊 Информация о системе логов",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    notification_channel = await get_notification_channel(guild_id)
    log_channel = await get_log_channel(guild_id)
    
    embed.add_field(
        name="🔔 Канал уведомлений",
        value=f"<#{notification_channel}>" if notification_channel else "⛔ Не установлен",
        inline=True
    )
    
    embed.add_field(
        name="📝 Канал логов",
        value=f"<#{log_channel}>" if log_channel else "⛔ Не установлен",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="тревога", description="Управление системой оповещений (только для владельца сервера и создателя бота)")
@app_commands.describe(действие="Включить или выключить систему тревог")
@app_commands.choices(действие=[
    app_commands.Choice(name="Включить", value="enable"),
    app_commands.Choice(name="Выключить", value="disable"),
    app_commands.Choice(name="Статус", value="status"),
])
async def alert_command(interaction: discord.Interaction, действие: app_commands.Choice[str]):
    # ID создателя бота - замените на ваш реальный ID
    BOT_OWNER_ID = 852962557002252289  # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ ID
    
    # Проверяем права: владелец сервера ИЛИ создатель бота
    if interaction.user.id != interaction.guild.owner_id and interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("⛔ Эта команда доступна только владельцу сервера или создателю бота!", ephemeral=True)
        return
    
    if действие.value == "enable":
        CONFIG['ADMIN_ALERT_ENABLED'] = True
        embed = discord.Embed(
            title="✅ Система тревог включена",
            description="Теперь вы будете получать уведомления о подозрительных действиях администраторов.",
            color=discord.Color.green()
        )
    elif действие.value == "disable":
        CONFIG['ADMIN_ALERT_ENABLED'] = False
        embed = discord.Embed(
            title="✅ Система тревог выключена",
            description="Уведомления о подозрительных действиях администраторов отключены.",
            color=discord.Color.orange()
        )
    else:
        status = "ВКЛЮЧЕНА" if CONFIG['ADMIN_ALERT_ENABLED'] else "ВЫКЛЮЧЕНА"
        color = discord.Color.green() if CONFIG['ADMIN_ALERT_ENABLED'] else discord.Color.orange()
        
        embed = discord.Embed(
            title="📊 Статус системы тревог",
            description=f"Система мониторинга действий администраторов: **{status}**",
            color=color
        )
        
        embed.add_field(
            name="🔔 Отслеживаемые события",
            value="• Удаление логов бота\n• Массовое удаление логов\n• Попытки скрыть действия",
            inline=False
        )
    
    # Добавляем информацию о том, кто изменил настройки
    if interaction.user.id == BOT_OWNER_ID:
        embed.add_field(
            name="👑 Изменил",
            value="Создатель бота",
            inline=True
        )
    else:
        embed.add_field(
            name="👑 Изменил",
            value="Владелец сервера",
            inline=True
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Запуск бота
if __name__ == "__main__":
    bot.run(CONFIG['TOKEN'])