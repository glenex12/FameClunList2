import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import phonenumbers
from phonenumbers import timezone, carrier, geocoder
import requests

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего бота (получите у @BotFather)
API_TOKEN = '8398628163:AAFh_mQHTH--0hMnMJY64QYNO9UqSIGbB04'

# Инициализация бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Функция для получения социальных сетей (пример через API)
def get_social_media_info(phone_number):
    """Получение информации о привязанных соцсетях"""
    # ВНИМАНИЕ: Для реального использования нужны платные API
    # Это пример - используйте сервисы типа Truecaller, Numverify и т.д.
    
    social_info = []
    try:
        # Пример для Truecaller (нужен API ключ)
        # response = requests.get(f'https://api.truecaller.com/v1/{phone_number}')
        
        # Заглушка для примера
        social_info.append("🔍 Соцсети обычно требуют платных API")
        social_info.append("📱 Популярные сервисы для проверки:")
        social_info.append("• Truecaller")
        social_info.append("• Numverify")
        social_info.append("• Whitepages")
        
    except Exception as e:
        social_info.append(f"⚠️ Ошибка получения соцсетей: {str(e)}")
    
    return social_info

# Обработчик команды /start
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для проверки номеров телефонов.\n"
        "Отправьте мне номер в любом формате:\n"
        "• +79123456789\n"
        "• 89123456789\n"
        "• 79123456789\n\n"
        "Я покажу:\n"
        "✅ Активен ли номер\n"
        "📍 Город/регион\n"
        "👥 Возможные соцсети"
    )

# Обработчик команды /help
@dp.message(Command("help"))
async def send_help(message: types.Message):
    await message.answer(
        "📋 Доступные команды:\n"
        "/start - начать работу\n"
        "/help - эта справка\n"
        "/check номер - проверить номер\n\n"
        "Просто отправьте номер телефона в любом формате для проверки!"
    )

# Обработчик ввода номера
@dp.message()
async def check_phone_number(message: types.Message):
    text = message.text.strip()
    
    # Проверка на команды
    if text.startswith('/'):
        return
    
    # Извлекаем номер из текста
    phone = text
    for char in [' ', '-', '(', ')', '+']:
        phone = phone.replace(char, '')
    
    try:
        # Парсим номер
        parsed = phonenumbers.parse(phone, "RU")  # RU - для российских номеров
        
        if not phonenumbers.is_valid_number(parsed):
            await message.answer("❌ Неверный номер телефона")
            return
        
        # Форматируем номер
        formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        
        # Получаем информацию
        time_zones = timezone.time_zones_for_number(parsed)
        service = carrier.name_for_number(parsed, "ru")
        region = geocoder.description_for_number(parsed, "ru")
        is_possible = phonenumbers.is_possible_number(parsed)
        
        # Проверяем активность (упрощенная проверка)
        is_active = "✅ Вероятно активен" if is_possible else "❌ Возможно неактивен"
        
        # Получаем информацию о соцсетях
        social_info = get_social_media_info(formatted)
        
        # Формируем ответ
        response = (
            f"📱 Номер: {formatted}\n"
            f"📶 Статус: {is_active}\n"
            f"🏙️ Регион: {region or 'Не определен'}\n"
            f"📞 Оператор: {service or 'Не определен'}\n"
            f"🌐 Часовой пояс: {', '.join(time_zones) if time_zones else 'Не определен'}\n\n"
            f"🔍 Социальные сети:\n"
        )
        
        for info in social_info:
            response += f"• {info}\n"
        
        response += "\n⚠️ Примечание: Для получения точных данных о соцсетях требуются платные API-сервисы."
        
        await message.answer(response)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке номера: {str(e)}\nПопробуйте другой формат.")

# Главная функция
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
