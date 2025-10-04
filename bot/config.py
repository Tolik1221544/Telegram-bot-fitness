import os
from typing import List
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
print(f"🔍 Loading .env from: {env_path}")
print(f"📁 .env exists: {env_path.exists()}")

load_dotenv(env_path)

# ✅ ПРОВЕРЯЕМ ЧТО ТОКЕН ЗАГРУЗИЛСЯ
bot_token = os.getenv('BOT_TOKEN')
print(f"🔑 BOT_TOKEN loaded: {bot_token[:10] if bot_token else 'NOT FOUND'}...")


class Config:
    """Bot configuration"""

    # Telegram
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN not found in .env file! Check your .env configuration.")

    BOT_USERNAME = os.getenv('BOT_USERNAME', '@LightweightPay_bot')

    # Admins
    ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

    # API
    API_BASE_URL = os.getenv('API_BASE_URL', 'http://api.lightweightfit.com:60170')
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', 30))

    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./bot_database.db')

    # Payment
    TRIBUTE_API_KEY = os.getenv('TRIBUTE_API_KEY')
    TRIBUTE_WEBHOOK_SECRET = os.getenv('TRIBUTE_WEBHOOK_SECRET')

    # Registration
    DEFAULT_REGISTRATION_COINS = int(os.getenv('DEFAULT_REGISTRATION_COINS', 50))

    # Tracking
    TRACKING_ENABLED = os.getenv('TRACKING_ENABLED', 'true').lower() == 'true'

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

    # Subscription packages
    SUBSCRIPTION_PACKAGES = [
        {
            'id': 'week_50',
            'name': '📅 Неделя (50 монет)',
            'coins': 50,
            'days': 7,
            'price': 99,  # рублей
            'description': '50 монет на 7 дней'
        },
        {
            'id': 'month_200',
            'name': '📆 Месяц (200 монет)',
            'coins': 200,
            'days': 30,
            'price': 299,
            'description': '200 монет на 30 дней'
        },
        {
            'id': 'month_500',
            'name': '💎 Премиум (500 монет)',
            'coins': 500,
            'days': 30,
            'price': 499,
            'description': '500 монет на 30 дней'
        }
    ]


config = Config()