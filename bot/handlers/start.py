from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.database import db_manager, User
from bot.api_client import api_client
from bot.config import config
from bot.utils.tracking import track_referral
import logging
import re

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    args = context.args

    # Check for referral code
    referral_code = None
    if args:
        referral_code = args[0]

    # Get or create user in bot database
    db_user = await db_manager.get_user(user.id)

    if not db_user:
        # New user registration
        db_user = await db_manager.create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            registration_coins=config.DEFAULT_REGISTRATION_COINS,
            referred_by=referral_code
        )

        # Track referral
        if referral_code:
            await track_referral(referral_code, user.id)

        welcome_text = f"""🎉 Добро пожаловать в LightweightPay Bot!

Что умеет этот бот:
💰 Управление монетами и подписками
📊 Просмотр статистики
🔄 Восстановление покупок
💳 Покупка подписок из России

Для начала работы свяжите аккаунт с приложением."""
    else:
        welcome_text = f"👋 С возвращением, {user.first_name}!\n\n"

        # Update balance if user is linked
        if db_user.api_token:
            try:
                balance = await api_client.get_balance(db_user.api_token)
                welcome_text += f"💰 Ваш баланс: {balance.get('balance', 0)} монет\n"

                if balance.get('hasActiveSubscription'):
                    expiry = balance.get('subscriptionExpiresAt', '')
                    if expiry and len(expiry) >= 10:
                        expiry = expiry[:10]
                        welcome_text += f"📅 Подписка до: {expiry}\n"
            except Exception as e:
                logger.error(f"Error getting balance: {e}")
                welcome_text += "Ваш баланс: загружается...\n"
        else:
            welcome_text += "Ваш баланс: загружается...\n"

    # Main menu keyboard
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance"),
         InlineKeyboardButton("💳 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats"),
         InlineKeyboardButton("🔄 Восстановить", callback_data="restore")],
        [InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]

    # Add admin button for admins
    if user.id in config.ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """📖 Помощь по боту

Основные команды:
/start - Главное меню
/help - Эта справка
/balance - Проверить баланс
/subscribe - Купить подписку
/stats - Статистика использования

Как связать аккаунт:
1. Нажмите "🔗 Связать аккаунт"
2. Введите email от приложения
3. Введите код подтверждения

Покупка подписки:
1. Нажмите "💳 Подписки"
2. Выберите пакет
3. Оплатите через Tribute (работает из РФ)

Проблемы?
Напишите в поддержку"""

    await update.message.reply_text(help_text)


# Register handlers
def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))