import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import aiohttp
import signal
import sys
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    ReplyKeyboardRemove,
    WebAppInfo
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
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
BOT_TOKEN = "8398628163:AAFh_mQHTH--0hMnMJY64QYNO9UqSIGbB04"  # Ваш токен
API_URL = "https://whg93498.hgweb.ru/api.php"  # URL вашего PHP API
SITE_URL = "https://whg93498.hgweb.ru"  # URL вашего сайта

# Инициализация базы данных SQLite
class Database:
    def __init__(self):
        self.db_name = 'анкеты.db'
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица для хранения пользователей бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                auth_code TEXT,
                code_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для кэширования заявок пользователя
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_applications_cache (
                telegram_id INTEGER,
                application_id INTEGER,
                nickname TEXT,
                username TEXT,
                status TEXT,
                category TEXT,
                submitted_at TIMESTAMP,
                PRIMARY KEY (telegram_id, application_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def add_or_update_user(self, telegram_id: int, username: str, first_name: str, last_name: str = ""):
        """Добавление или обновление пользователя в локальной БД"""
        def sync_add():
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bot_users 
                (telegram_id, username, first_name, last_name, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (telegram_id, username, first_name, last_name))
            conn.commit()
            conn.close()
        
        # Запускаем в отдельном потоке чтобы не блокировать event loop
        await asyncio.get_event_loop().run_in_executor(None, sync_add)
    
    async def save_auth_code(self, telegram_id: int, code: str):
        """Сохранение кода авторизации"""
        def sync_save():
            expires = datetime.now() + timedelta(minutes=10)
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bot_users 
                SET auth_code = ?, code_expires = ?
                WHERE telegram_id = ?
            ''', (code, expires.isoformat(), telegram_id))
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, sync_save)
    
    async def get_user(self, telegram_id: int):
        """Получение данных пользователя из локальной БД"""
        def sync_get():
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bot_users WHERE telegram_id = ?', (telegram_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # Получаем имена колонок
                cursor.description  # Это нужно чтобы получить описание
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
        
        return await asyncio.get_event_loop().run_in_executor(None, sync_get)
    
    def get_user_sync(self, telegram_id: int):
        """Синхронная версия получения пользователя (для быстрых операций)"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bot_users WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    
    async def clear_expired_codes(self):
        """Очистка просроченных кодов"""
        def sync_clear():
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE bot_users 
                SET auth_code = NULL, code_expires = NULL 
                WHERE code_expires < ?
            ''', (now,))
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, sync_clear)

# Инициализация базы данных
db = Database()

# Клавиатуры (остаются без изменений)
def get_main_keyboard(telegram_id: int, is_admin: bool = False):
    """Основная клавиатура"""
    keyboard = []
    
    if is_admin:
        keyboard.append([
            KeyboardButton("👑 Админ-панель"),
            KeyboardButton("📊 Статистика")
        ])
    
    keyboard.extend([
        [KeyboardButton("🔐 Получить код для входа")],
        [KeyboardButton("📋 Мои заявки")],
        [KeyboardButton("🌐 Перейти на сайт")],
        [KeyboardButton("ℹ️ Помощь")]
    ])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")

def get_admin_keyboard():
    """Клавиатура администратора"""
    keyboard = [
        [KeyboardButton("📊 Статистика"), KeyboardButton("👥 Пользователи")],
        [KeyboardButton("📝 Управление заявками"), KeyboardButton("⚙️ Настройки")],
        [KeyboardButton("⬅️ На главную")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_web_app_keyboard():
    """Клавиатура с Web App кнопкой"""
    keyboard = [[
        KeyboardButton(
            text="🌐 Открыть сайт",
            web_app=WebAppInfo(url=SITE_URL)
        )
    ]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# API функции (остаются без изменений)
async def api_request(action: str, method: str = "GET", data: Dict = None) -> Dict:
    """Отправка запроса к PHP API"""
    url = f"{API_URL}?action={action}"
    
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url) as response:
                    result = await response.json()
            else:
                async with session.post(url, json=data) as response:
                    result = await response.json()
            
            logger.info(f"API {action}: {result}")
            return result
        except Exception as e:
            logger.error(f"API request error: {e}")
            return {'success': False, 'error': str(e)}

async def telegram_auth(telegram_id: int, username: str, first_name: str, last_name: str = "") -> Dict:
    """Авторизация через Telegram API"""
    data = {
        'telegram_id': str(telegram_id),
        'username': username or '',
        'first_name': first_name or '',
        'last_name': last_name or ''
    }
    return await api_request('telegram_auth', 'POST', data)

async def check_auth(telegram_id: int) -> Dict:
    """Проверка авторизации"""
    return await api_request(f'check_auth&telegram_id={telegram_id}')

async def get_user_applications(telegram_id: int) -> Dict:
    """Получение заявок пользователя"""
    return await api_request(f'get_my_applications&telegram_id={telegram_id}')

async def get_all_applications(status: str = None, category: str = None) -> Dict:
    """Получение всех заявок (для админа)"""
    url = 'get_applications'
    if status:
        url += f'&status={status}'
    if category:
        url += f'&category={category}'
    return await api_request(url)

async def get_stats(telegram_id: int) -> Dict:
    """Получение статистики"""
    return await api_request(f'get_stats&telegram_id={telegram_id}')

async def update_application_status(app_id: int, status: str, processed_by: int) -> Dict:
    """Обновление статуса заявки"""
    data = {
        'id': app_id,
        'status': status,
        'processed_by': str(processed_by)
    }
    return await api_request('update_application', 'POST', data)

async def delete_application(app_id: int, telegram_id: int) -> Dict:
    """Удаление заявки"""
    data = {
        'id': app_id,
        'telegram_id': str(telegram_id)
    }
    return await api_request('delete_application', 'POST', data)

# Обработчики команд (остаются без изменений)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    telegram_id = user.id
    
    # Регистрация в локальной БД
    await db.add_or_update_user(
        telegram_id,
        user.username or f"user_{telegram_id}",
        user.first_name,
        user.last_name or ""
    )
    
    # Авторизация через API
    auth_result = await telegram_auth(
        telegram_id,
        user.username or '',
        user.first_name,
        user.last_name or ''
    )
    
    if auth_result.get('success'):
        user_data = auth_result.get('user', {})
        is_admin = user_data.get('is_admin', False)
        
        welcome_text = (
            f"👋 <b>Добро пожаловать в Fame Club Auth Bot!</b>\n\n"
            f"📋 <b>Ваши данные:</b>\n"
            f"• ID: <code>{telegram_id}</code>\n"
            f"• Имя: {user.first_name}\n"
            f"• Ник: @{user.username or 'не указан'}\n"
            f"• Статус: {'👑 Администратор' if is_admin else '👤 Пользователь'}\n\n"
            f"<b>Доступные функции:</b>\n"
            f"• 🔐 Авторизация на сайте\n"
            f"• 📋 Просмотр заявок\n"
            f"• 🌐 Быстрый переход на сайт\n"
            f"• ℹ️ Полная информация"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=get_main_keyboard(telegram_id, is_admin)
        )
    else:
        await update.message.reply_text(
            "❌ <b>Ошибка авторизации!</b>\n\n"
            "Пожалуйста, попробуйте позже или обратитесь к администратору.",
            parse_mode='HTML'
        )

async def get_auth_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерация кода для авторизации на сайте"""
    user = update.effective_user
    telegram_id = user.id
    
    # Проверяем авторизацию через API
    auth_result = await check_auth(telegram_id)
    
    if not auth_result.get('success'):
        await update.message.reply_text(
            "❌ <b>Ошибка авторизации!</b>\n\n"
            "Пожалуйста, начните с команды /start",
            parse_mode='HTML'
        )
        return
    
    # Создаем уникальный код
    import hashlib
    import time
    code = hashlib.md5(f"{telegram_id}{time.time()}".encode()).hexdigest()[:8].upper()
    
    # Сохраняем код в локальной БД
    await db.save_auth_code(telegram_id, code)
    
    # Создаем URL для авторизации
    auth_url = f"{SITE_URL}/#auth=telegram&code={code}&id={telegram_id}"
    
    # Создаем инлайн клавиатуру
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Авторизоваться на сайте", url=auth_url)],
        [InlineKeyboardButton("📋 Мои заявки", callback_data="my_apps")]
    ])
    
    await update.message.reply_text(
        f"🔐 <b>Код для авторизации:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"📋 <b>Инструкция:</b>\n"
        f"1. Перейдите на сайт\n"
        f"2. Нажмите 'Войти через Telegram'\n"
        f"3. Введите этот код\n"
        f"4. Или нажмите кнопку ниже\n\n"
        f"⏰ <b>Срок действия:</b> 10 минут\n"
        f"🔗 <a href='{auth_url}'>Ссылка для авторизации</a>",
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

async def my_applications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ заявок пользователя"""
    user = update.effective_user
    telegram_id = user.id
    
    # Получаем заявки через API
    result = await get_user_applications(telegram_id)
    
    if not result.get('success'):
        await update.message.reply_text(
            "❌ <b>Не удалось загрузить заявки!</b>\n\n"
            "Попробуйте позже или обратитесь к администратору.",
            parse_mode='HTML'
        )
        return
    
    applications = result.get('applications', [])
    
    if not applications:
        await update.message.reply_text(
            "📭 <b>У вас пока нет заявок</b>\n\n"
            "Чтобы подать заявку:\n"
            "1. Авторизуйтесь на сайте\n"
            "2. Заполните форму заявки\n"
            "3. Отправьте её на рассмотрение\n\n"
            f"🌐 <a href='{SITE_URL}'>Перейти на сайт</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return
    
    # Формируем сообщение с заявками
    text = f"📋 <b>Ваши заявки ({len(applications)}):</b>\n\n"
    
    for i, app in enumerate(applications[:10], 1):  # Показываем первые 10
        status_emoji = {
            'pending': '⏳',
            'accepted': '✅',
            'rejected': '❌'
        }.get(app.get('status', 'pending'), '❓')
        
        date = app.get('submitted_at', '').split()[0] if app.get('submitted_at') else 'N/A'
        
        text += (
            f"{i}. <b>{app.get('nickname', 'Без имени')}</b>\n"
            f"   📌 Категория: {app.get('category', 'Не указана')}\n"
            f"   📅 Дата: {date}\n"
            f"   🏷️ Статус: {status_emoji} {app.get('status', 'ожидает')}\n\n"
        )
    
    if len(applications) > 10:
        text += f"<i>... и ещё {len(applications) - 10} заявок</i>\n\n"
    
    text += "🌐 Для просмотра всех заявок перейдите на сайт."
    
    # Клавиатура с действиями
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Перейти на сайт", url=SITE_URL)],
        [InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_apps")]
    ])
    
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель администратора"""
    user = update.effective_user
    telegram_id = user.id
    
    # Проверяем права через API
    result = await api_request(f'check_admin&telegram_id={telegram_id}')
    
    if not result.get('is_admin'):
        await update.message.reply_text(
            "⛔ <b>Доступ запрещен!</b>\n\n"
            "У вас нет прав администратора.",
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text(
        "👑 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        parse_mode='HTML',
        reply_markup=get_admin_keyboard()
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика системы"""
    user = update.effective_user
    telegram_id = user.id
    
    # Проверяем права через API
    result = await api_request(f'check_admin&telegram_id={telegram_id}')
    
    if not result.get('is_admin'):
        await update.message.reply_text("⛔ У вас нет прав администратора!")
        return
    
    # Получаем статистику
    stats_result = await get_stats(telegram_id)
    
    if not stats_result.get('success'):
        await update.message.reply_text("❌ Не удалось получить статистику!")
        return
    
    stats = stats_result.get('stats', {})
    
    text = (
        f"📊 <b>Статистика Fame Club</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {stats.get('users', 0)}\n"
        f"• Админов: {stats.get('admins', 0)}\n\n"
        f"📝 <b>Заявки:</b>\n"
        f"• Всего: {stats.get('total', 0)}\n"
        f"• ✅ Принято: {stats.get('accepted', 0)}\n"
        f"• ⏳ Ожидает: {stats.get('pending', 0)}\n"
        f"• ❌ Отклонено: {stats.get('rejected', 0)}\n\n"
        f"🔄 <b>Обновлено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats")]
    ])
    
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

async def go_to_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход на сайт"""
    await update.message.reply_text(
        f"🌐 <b>Сайт Fame Club</b>\n\n"
        f"🔗 <a href='{SITE_URL}'>Нажмите для перехода</a>\n\n"
        f"📱 <b>Доступные функции:</b>\n"
        f"• 📝 Подача заявок\n"
        f"• 👥 Просмотр участников\n"
        f"• ⚙️ Настройки профиля\n"
        f"• 📊 Статистика клуба",
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=get_web_app_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
    help_text = (
        f"🤖 <b>Fame Club Auth Bot - Справка</b>\n\n"
        f"📋 <b>Основные команды:</b>\n"
        f"/start - Запустить бота\n"
        f"/help - Эта справка\n\n"
        f"🔧 <b>Основные функции:</b>\n"
        f"• <b>🔐 Получить код для входа</b> - Создать код для авторизации на сайте\n"
        f"• <b>📋 Мои заявки</b> - Просмотреть статус ваших заявок\n"
        f"• <b>🌐 Перейти на сайт</b> - Быстрый переход на сайт клуба\n"
        f"• <b>👑 Админ-панель</b> - Панель управления (для админов)\n\n"
        f"🔗 <b>Сайт:</b> {SITE_URL}\n"
        f"📞 <b>Поддержка:</b> Обращайтесь к администраторам\n\n"
        f"⚙️ <b>Техническая информация:</b>\n"
        f"• Бот работает на Python 3.10+\n"
        f"• Использует официальный Telegram API\n"
        f"• Интегрирован с сайтом через REST API"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на inline-кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    telegram_id = user.id
    
    if query.data == "my_apps":
        # Создаем обновление из callback query
        context.user_data['from_callback'] = True
        await my_applications_command(update, context)
    elif query.data == "refresh_apps":
        await query.edit_message_text("🔄 Обновление списка заявок...")
        await my_applications_command(update, context)
    elif query.data == "refresh_stats":
        await query.edit_message_text("🔄 Обновление статистики...")
        await stats_command(update, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user = update.effective_user
    telegram_id = user.id
    text = update.message.text
    
    # Проверяем авторизацию
    auth_result = await check_auth(telegram_id)
    is_admin = False
    
    if auth_result.get('success'):
        user_data = auth_result.get('user', {})
        is_admin = user_data.get('is_admin', False)
    
    # Обработка команд из клавиатуры
    if text == "🔐 Получить код для входа":
        await get_auth_code_command(update, context)
    elif text == "📋 Мои заявки":
        await my_applications_command(update, context)
    elif text == "🌐 Перейти на сайт":
        await go_to_site_command(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "👑 Админ-панель" and is_admin:
        await admin_panel_command(update, context)
    elif text == "📊 Статистика" and is_admin:
        await stats_command(update, context)
    elif text == "👥 Пользователи" and is_admin:
        await update.message.reply_text(
            "👥 <b>Управление пользователями</b>\n\n"
            "Эта функция доступна только на сайте.\n\n"
            f"🔗 <a href='{SITE_URL}/admin/users'>Перейти к управлению пользователями</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    elif text == "📝 Управление заявками" and is_admin:
        await update.message.reply_text(
            "📝 <b>Управление заявками</b>\n\n"
            "Для управления заявками перейдите на сайт.\n\n"
            f"🔗 <a href='{SITE_URL}/admin/applications'>Перейти к управлению заявками</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    elif text == "⬅️ На главную":
        await start_command(update, context)
    else:
        await update.message.reply_text(
            "🤖 <b>Неизвестная команда</b>\n\n"
            "Используйте кнопки меню или команды:\n"
            "/start - Главное меню\n"
            "/help - Справка\n\n"
            "Если у вас возникли проблемы, обратитесь к администратору.",
            parse_mode='HTML'
        )

# Функция для периодической очистки устаревших кодов
async def cleanup_task():
    """Периодическая очистка устаревших кодов"""
    while True:
        try:
            await db.clear_expired_codes()
            logger.info("Очищены просроченные коды авторизации")
        except Exception as e:
            logger.error(f"Ошибка при очистке кодов: {e}")
        
        # Ждем 5 минут перед следующей очисткой
        await asyncio.sleep(300)

# Глобальная переменная для хранения задачи очистки
cleanup_task_obj = None

# Основная функция
async def main():
    """Основная функция запуска бота"""
    global cleanup_task_obj
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчик callback-запросов
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Запускаем задачу очистки
    cleanup_task_obj = asyncio.create_task(cleanup_task())
    
    # Запускаем бота
    logger.info("Бот запущен и готов к работе!")
    
    try:
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        # Останавливаем задачу очистки
        if cleanup_task_obj and not cleanup_task_obj.done():
            cleanup_task_obj.cancel()
            try:
                await cleanup_task_obj
            except asyncio.CancelledError:
                pass
        
        # Закрываем соединения
        await application.shutdown()
        await application.stop()

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"Получен сигнал {signum}, завершаем работу...")
    # Завершаем event loop
    loop = asyncio.get_event_loop()
    for task in asyncio.all_tasks(loop):
        task.cancel()
    loop.stop()

if __name__ == '__main__':
    # Настраиваем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запускаем асинхронный цикл
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}")
    finally:
        logger.info("Бот завершил работу")
