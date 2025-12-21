import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен вашего бота (замените на свой)
TOKEN = "8398628163:AAFh_mQHTH--0hMnMJY64QYNO9UqSIGbB04"

# Ссылки (замените на реальные)
CHANNEL_LINK = "https://t.me/+dfpuM8fKxCkyNmM0"
SHOP_LINK = "https://t.me/fizshopglenex"
SITE1_LINK = "http://fameclub.hgweb.ru"
SITE2_LINK = "http://osintsearch.hgweb.ru"
EXTRA_LINK = "https://t.me/pripiskaybiistvenii"
REVIEWS_LINK = "https://t.me/repaglenexa"  # Замените на реальную ссылку
CHAT_LINK = "https://t.me/chatglenex"  # Замените на реальную ссылку

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    # Создаем кнопки
    keyboard = [
        [InlineKeyboardButton("📢 Телеграм канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🛍️ Физ шоп", url=SHOP_LINK)],
        [InlineKeyboardButton("🌐 Фейм лист", url=SITE1_LINK)],
        [InlineKeyboardButton("🌐 Осинт поиск", url=SITE2_LINK)],
        [InlineKeyboardButton("ℹ️ Приписка", url=EXTRA_LINK)],
        [InlineKeyboardButton("⭐ Отзывы", url=REVIEWS_LINK)],
        [InlineKeyboardButton("💬 Мой чат", url=CHAT_LINK)],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Текст сообщения
    message_text = (
        "🔗 *Добро пожаловать в бота-переходник!*\n\n"
        "Выберите нужный раздел из списка ниже:"
    )
    
    await update.message.reply_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📋 *Доступные команды:*\n"
        "/start - Запустить бота и получить меню\n"
        "/help - Получить справку по командам\n\n"
        "Просто нажмите /start для получения меню с ссылками!"
    )
    
    await update.message.reply_text(
        text=help_text,
        parse_mode='Markdown'
    )

def main():
    """Основная функция запуска бота"""
    # Создаем Application
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
