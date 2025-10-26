import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ⚠️ ВАШ ТОКЕН ЗДЕСЬ ⚠️
BOT_TOKEN = "8408558383:AAE0yfbiHfSB0CMetNIiSWp4f8iR-YAL5n4"

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("🎉 Бот запущен! Напиши что-нибудь.")

async def echo(update: Update, context: CallbackContext):
    await update.message.reply_text(f"Ты сказал: {update.message.text}")

def main():
    if BOT_TOKEN == "8408558383:AAE0yfbiHfSB0CMetNIiSWp4f8iR-YAL5n4":
        print("❌ ЗАМЕНИТЕ BOT_TOKEN на ваш токен!")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ Бот запускается...")
    app.run_polling()

if __name__ == "__main__":
    main()