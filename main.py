import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ⚠️ ВСТАВЬТЕ ВАШ ТОКЕН ЗДЕСЬ ⚠️
TELEGRAM_TOKEN = "8408558383:AAE0yfbiHfSB0CMetNIiSWp4f8iR-YAL5n4"  # Замените на ваш токен

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! 🎉\n"
        f"Я работаю на Koyeb и готов к работе!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "🤖 Доступные команды:\n"
        "/start - Начать работу\n" 
        "/help - Помощь\n"
        "/info - Информация\n\n"
        "Просто напиши мне что-нибудь!"
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /info"""
    user = update.effective_user
    await update.message.reply_text(
        f"👤 Ваш ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"🚀 Бот работает на Koyeb"
    )

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эхо-обработчик текстовых сообщений"""
    user_message = update.message.text
    await update.message.reply_text(f"🔁 Вы сказали: {user_message}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск Telegram бота...")
    
    # Проверка токена
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        logger.error("❌ ЗАМЕНИТЕ TELEGRAM_TOKEN на ваш настоящий токен!")
        return
    
    try:
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("✅ Бот запущен и работает!")
        logger.info("📱 Используется режим polling...")
        
        # Запускаем бота
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        logger.info("🔄 Перезапуск через 10 секунд...")
        asyncio.run(asyncio.sleep(10))
        main()

if __name__ == "__main__":
    main()