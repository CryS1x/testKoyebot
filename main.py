from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я простой бот 🤖")

# Основная функция запуска
def main():
    app = ApplicationBuilder().token("8408558383:AAE0yfbiHfSB0CMetNIiSWp4f8iR-YAL5n4").build()

    app.add_handler(CommandHandler("start", start))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
