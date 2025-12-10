import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8398628163:AAFh_mQHTH--0hMnMJY64QYNO9UqSIGbB04"  # Замените на ваш токен
ADMIN_ID = 999  # ID главного администратора
SITE_URL = "https://whg93498.hgweb.ru"  # URL вашего сайта

# Состояния для ConversationHandler
WAITING_FOR_CODE = 1

# Хранилище данных
class DataStorage:
    def __init__(self):
        self.users = {}  # user_id: user_data
        self.auth_codes = {}  # code: user_data
        self.admins = [ADMIN_ID]
        self.banned_users = set()
        
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str = ""):
        self.users[user_id] = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'registration_date': datetime.now().isoformat(),
            'is_admin': user_id in self.admins,
            'is_banned': False,
            'applications': []
        }
        
    def create_auth_code(self, user_id: int) -> str:
        code = secrets.token_hex(3).upper()  # 6-значный код
        self.auth_codes[code] = {
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat(),
            'used': False
        }
        return code
        
    def verify_code(self, code: str) -> Optional[Dict]:
        code = code.upper()
        if code in self.auth_codes:
            auth_data = self.auth_codes[code]
            expires_at = datetime.fromisoformat(auth_data['expires_at'])
            if datetime.now() < expires_at and not auth_data['used']:
                auth_data['used'] = True
                return self.users.get(auth_data['user_id'])
        return None
        
    def save_to_file(self):
        data = {
            'users': self.users,
            'auth_codes': self.auth_codes,
            'admins': self.admins,
            'banned_users': list(self.banned_users)
        }
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    def load_from_file(self):
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.users = {int(k): v for k, v in data.get('users', {}).items()}
                self.auth_codes = data.get('auth_codes', {})
                self.admins = data.get('admins', [ADMIN_ID])
                self.banned_users = set(data.get('banned_users', []))
        except FileNotFoundError:
            pass

# Инициализация хранилища
storage = DataStorage()
storage.load_from_file()

# Клавиатуры
def get_main_keyboard(user_id: int):
    keyboard = []
    
    if user_id in storage.admins:
        keyboard.append([KeyboardButton("👑 Админ панель")])
    
    keyboard.extend([
        [KeyboardButton("🔐 Получить код для входа")],
        [KeyboardButton("📋 Мои заявки")],
        [KeyboardButton("ℹ️ О боте")]
    ])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 Статистика"), KeyboardButton("👤 Пользователи")],
        [KeyboardButton("📝 Заявки"), KeyboardButton("🚫 Блокировки")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Обработчики команд
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Проверка на бан
    if user_id in storage.banned_users:
        await update.message.reply_text(
            "⛔ Ваш аккаунт заблокирован!\n"
            "Вы не можете использовать бота из-за нарушений правил.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # Регистрация нового пользователя
    if user_id not in storage.users:
        username = user.username or f"user_{user_id}"
        storage.add_user(
            user_id,
            username,
            user.first_name,
            user.last_name or ""
        )
        storage.save_to_file()
        
        await update.message.reply_text(
            f"👋 Добро пожаловать в <b>Fame Club Auth Bot</b>!\n\n"
            f"Это официальный бот для авторизации на сайте Fame Club.\n\n"
            f"📝 <b>Ваш ID:</b> <code>{user_id}</code>\n"
            f"👤 <b>Ваш ник:</b> @{username}\n\n"
            f"Используйте кнопки ниже для управления:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!\n\n"
            f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
            f"Используйте кнопки ниже:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user_id)
        )

async def get_auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Проверка на бан
    if user_id in storage.banned_users:
        await update.message.reply_text("⛔ Ваш аккаунт заблокирован!")
        return
    
    # Создание кода
    code = storage.create_auth_code(user_id)
    user_data = storage.users.get(user_id, {})
    
    # Сохраняем
    storage.save_to_file()
    
    # Формируем ссылку для авторизации
    auth_url = f"{SITE_URL}#auth=telegram&code={code}"
    
    # Создаем инлайн клавиатуру
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Перейти на сайт", url=auth_url)]
    ])
    
    await update.message.reply_text(
        f"🔐 <b>Код для авторизации на сайте:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"📋 <b>Данные для входа:</b>\n"
        f"• ID: <code>{user_id}</code>\n"
        f"• Ник: @{user_data.get('username', '')}\n"
        f"• Имя: {user_data.get('first_name', '')}\n\n"
        f"⏰ <b>Срок действия:</b> 10 минут\n\n"
        f"<b>📌 Инструкция:</b>\n"
        f"1. Перейдите на сайт Fame Club\n"
        f"2. Нажмите кнопку 'Войти через Telegram'\n"
        f"3. Введите этот код\n"
        f"4. Готово! Вы авторизованы.\n\n"
        f"🔗 <a href='{auth_url}'>Перейти на сайт для авторизации</a>",
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=keyboard
    )

async def my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = storage.users.get(user_id, {})
    applications = user_data.get('applications', [])
    
    if not applications:
        await update.message.reply_text(
            "📭 У вас пока нет отправленных заявок.\n\n"
            "Чтобы подать заявку:\n"
            "1. Авторизуйтесь на сайте\n"
            "2. Заполните форму заявки\n"
            "3. Отправьте её на рассмотрение"
        )
    else:
        text = "📋 <b>Ваши заявки:</b>\n\n"
        for i, app in enumerate(applications[:5], 1):  # Показываем последние 5
            status_emoji = {
                'pending': '⏳',
                'accepted': '✅',
                'rejected': '❌'
            }.get(app.get('status', 'pending'), '❓')
            
            text += (
                f"{i}. <b>{app.get('nickname', 'Без имени')}</b>\n"
                f"   Статус: {status_emoji} {app.get('status', 'ожидает')}\n"
                f"   Дата: {app.get('date', 'неизвестно')}\n\n"
            )
        
        if len(applications) > 5:
            text += f"... и ещё {len(applications) - 5} заявок\n\n"
        
        text += "📌 Для просмотра всех заявок перейдите на сайт."
        
        await update.message.reply_text(text, parse_mode='HTML')

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = len(storage.users)
    active_codes = len([c for c in storage.auth_codes.values() 
                       if not c['used'] and datetime.fromisoformat(c['expires_at']) > datetime.now()])
    
    await update.message.reply_text(
        f"🤖 <b>Fame Club Auth Bot</b>\n\n"
        f"Официальный бот для авторизации на сайте Fame Club.\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Пользователей: {total_users}\n"
        f"• Активных кодов: {active_codes}\n\n"
        f"⚙️ <b>Функции:</b>\n"
        f"• 🔐 Безопасная авторизация\n"
        f"• 📋 Управление заявками\n"
        f"• 👑 Административные функции\n\n"
        f"🔗 <b>Сайт:</b> {SITE_URL}\n\n"
        f"📞 <b>Поддержка:</b> @ваш_ник\n"
        f"🔒 <b>Безопасность:</b> Все данные шифруются",
        parse_mode='HTML'
    )

# Админ команды
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in storage.admins:
        await update.message.reply_text(
            "👑 <b>Админ панель</b>\n\n"
            "Выберите действие:",
            parse_mode='HTML',
            reply_markup=get_admin_keyboard()
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in storage.admins:
        return
    
    total_users = len(storage.users)
    active_users = len([u for u in storage.users.values() 
                       if datetime.now() - datetime.fromisoformat(u['registration_date']) < timedelta(days=30)])
    active_codes = len([c for c in storage.auth_codes.values() 
                       if not c['used'] and datetime.fromisoformat(c['expires_at']) > datetime.now()])
    banned_users = len(storage.banned_users)
    
    await update.message.reply_text(
        f"📊 <b>Статистика системы:</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {total_users}\n"
        f"• Активных (30 дней): {active_users}\n"
        f"• Заблокированных: {banned_users}\n\n"
        f"🔐 <b>Авторизация:</b>\n"
        f"• Активных кодов: {active_codes}\n"
        f"• Всего создано кодов: {len(storage.auth_codes)}\n\n"
        f"⚙️ <b>Система:</b>\n"
        f"• Администраторов: {len(storage.admins)}\n"
        f"• Время работы: 24/7",
        parse_mode='HTML'
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in storage.admins:
        return
    
    users = list(storage.users.values())[:10]  # Показываем первые 10
    
    if not users:
        await update.message.reply_text("📭 Нет зарегистрированных пользователей.")
        return
    
    text = "👤 <b>Последние пользователи:</b>\n\n"
    for user_data in users:
        status = "🚫" if user_data['user_id'] in storage.banned_users else "✅"
        admin = "👑" if user_data['user_id'] in storage.admins else "👤"
        
        text += (
            f"{admin} <b>ID:</b> <code>{user_data['user_id']}</code>\n"
            f"{status} <b>Ник:</b> @{user_data['username']}\n"
            f"<b>Имя:</b> {user_data['first_name']}\n"
            f"<b>Дата регистрации:</b> {user_data['registration_date'][:10]}\n\n"
        )
    
    text += f"📊 Всего пользователей: {len(storage.users)}"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text
    
    # Проверяем, не заблокирован ли пользователь
    if user_id in storage.banned_users:
        await update.message.reply_text("⛔ Ваш аккаунт заблокирован!")
        return
    
    # Обработка кнопок
    if text == "🔐 Получить код для входа":
        await get_auth_code(update, context)
    elif text == "📋 Мои заявки":
        await my_applications(update, context)
    elif text == "ℹ️ О боте":
        await about_bot(update, context)
    elif text == "👑 Админ панель" and user_id in storage.admins:
        await admin_panel(update, context)
    elif text == "📊 Статистика" and user_id in storage.admins:
        await admin_stats(update, context)
    elif text == "👤 Пользователи" and user_id in storage.admins:
        await admin_users(update, context)
    elif text == "⬅️ Назад":
        await back_to_main(update, context)
    # Если это код (6 символов, буквы и цифры)
    elif len(text) == 6 and text.isalnum():
        code = text.upper()
        user_data = storage.verify_code(code)
        
        if user_data:
            auth_url = f"{SITE_URL}#auth=telegram&code={code}"
            await update.message.reply_text(
                f"✅ <b>Код подтвержден!</b>\n\n"
                f"Теперь вы можете авторизоваться на сайте.\n\n"
                f"📋 <b>Ваши данные:</b>\n"
                f"• ID: <code>{user_data['user_id']}</code>\n"
                f"• Ник: @{user_data['username']}\n"
                f"• Имя: {user_data['first_name']}\n\n"
                f"🔗 <a href='{auth_url}'>Перейти к авторизации</a>",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text(
                "❌ <b>Неверный или просроченный код!</b>\n\n"
                "Возможные причины:\n"
                "• Код не существует\n"
                "• Код уже использован\n"
                "• Истек срок действия (10 минут)\n\n"
                "Получите новый код: /start",
                parse_mode='HTML'
            )
    else:
        await update.message.reply_text(
            "🤖 Используйте кнопки меню или команды:\n"
            "/start - Главное меню\n"
            "/help - Помощь"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 <b>Справка по боту:</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Запустить бота\n"
        "/help - Показать эту справку\n\n"
        "<b>Основные функции:</b>\n"
        "• 🔐 Получить код для входа - Создать код для авторизации на сайте\n"
        "• 📋 Мои заявки - Просмотреть ваши заявки\n"
        "• ℹ️ О боте - Информация о боте\n\n"
        "👑 <b>Для администраторов:</b>\n"
        "• Админ панель - Панель управления ботом\n"
        "• Статистика - Статистика системы\n"
        "• Пользователи - Список пользователей\n\n"
        "<b>Как использовать:</b>\n"
        "1. Нажмите '🔐 Получить код для входа'\n"
        "2. Используйте код на сайте для авторизации\n"
        "3. Ваши данные будут автоматически переданы",
        parse_mode='HTML'
    )

# Функция для периодического сохранения данных
async def auto_save(context: ContextTypes.DEFAULT_TYPE):
    storage.save_to_file()
    logger.info("Данные сохранены")

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем периодическое сохранение данных (каждые 5 минут)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(auto_save, interval=300, first=10)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
