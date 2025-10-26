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

# Получаем токен из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! 🎉\n"
        f"Я работаю на Koyeb и готов к работе!\n"
        f"Просто напиши мне что-нибудь."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
🤖 Доступные команды:
/start - Начать работу
/help - Получить справку
/about - О боте

Просто напиши мне сообщение, и я его повторю!
    """
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /about"""
    await update.message.reply_text(
        "🚀 Этот бот работает на платформе Koyeb!\n"
        "⚡ Быстрый и надежный хостинг для ботов."
    )

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эхо-обработчик текстовых сообщений"""
    user_message = update.message.text
    await update.message.reply_text(f"🔁 Вы сказали: {user_message}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке update {update}: {context.error}")

def create_bot_application(token):
    """Создание и настройка приложения бота"""
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    
    # Добавляем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    return application

def main():
    """Основная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА")
    logger.info("=" * 50)
    
    # Проверяем наличие токена
    if not TELEGRAM_TOKEN:
        logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        logger.info("💡 Как исправить:")
        logger.info("1. Зайдите в Koyeb Dashboard -> ваш сервис")
        logger.info("2. В разделе Environment Variables добавьте:")
        logger.info("   Name: TELEGRAM_BOT_TOKEN")
        logger.info("   Value: ваш_токен_от_BotFather")
        logger.info("3. Сохраните и перезапустите сервис")
        return
    
    logger.info("✅ TELEGRAM_BOT_TOKEN найден")
    
    try:
        # Создаем и запускаем бота
        application = create_bot_application(TELEGRAM_TOKEN)
        
        logger.info("🤖 Бот запускается...")
        logger.info("📱 Используется режим polling...")
        
        # Запускаем бота
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        logger.info("🔄 Перезапуск через 5 секунд...")
        asyncio.run(asyncio.sleep(5))
        main()  # Рекурсивный перезапуск

if __name__ == "__main__":
    main()