from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.database import db_manager, User
from bot.api_client import api_client
from bot.config import config
from bot.utils.tracking import track_referral
import logging
import re
from datetime import datetime

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


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command"""
    user = update.effective_user
    db_user = await db_manager.get_user(user.id)

    if not db_user or not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await update.message.reply_text(
            "❌ Сначала свяжите аккаунт с приложением",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    try:
        balance = await api_client.get_balance(db_user.api_token)

        text = f"""💰 **Ваш баланс**

Монет: {balance.get('balance', 0)}
"""

        if balance.get('hasActiveSubscription'):
            expiry = balance.get('subscriptionExpiresAt', '')
            if expiry and len(expiry) >= 10:
                expiry = expiry[:10]
            text += f"\n📅 Подписка до: {expiry}"
        else:
            text += "\n📅 Подписка: не активна"

        keyboard = [[InlineKeyboardButton("💳 Купить подписку", callback_data="subscriptions")]]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        await update.message.reply_text("❌ Ошибка получения баланса. Попробуйте позже.")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command"""
    user = update.effective_user
    db_user = await db_manager.get_user(user.id)

    if not db_user:
        await update.message.reply_text("❌ Используйте /start для начала работы")
        return

    if not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await update.message.reply_text(
            "❌ Сначала свяжите аккаунт с приложением",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Show subscription packages
    from bot.handlers.payment import SUBSCRIPTION_PACKAGES

    keyboard = []

    for package in SUBSCRIPTION_PACKAGES:
        button_text = f"{package['name']} - {package['price']} {package['currency']}"
        if package.get('savings'):
            button_text += f" (скидка {package['savings']})"
        callback_data = f"buy_package_{package['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """💳 **LightWeight PAY**

Здесь вы можете купить LW coins со скидкой, оплатить картой любой страны и любым удобным способом

**Выберите период подписки:**"""

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """📖 **Помощь по боту**

**Основные команды:**
/start - Главное меню
/help - Эта справка
/balance - Проверить баланс
/subscribe - Купить подписку
/admin - Админ панель (для админов)

**Как связать аккаунт:**
1. Нажмите "🔗 Связать аккаунт"
2. Введите email от приложения
3. Введите код подтверждения

**Покупка подписки:**
1. Нажмите /subscribe или "💳 Подписки"
2. Выберите пакет
3. Оплатите через Tribute

**Проблемы?**
Напишите в поддержку @support"""

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def track_coin_usage(telegram_id: int, amount: int, feature: str, description: str = None):
    """Записать использование монет для статистики"""
    try:
        from bot.database import LwCoinTransaction
        async with db_manager.SessionLocal() as session:
            db_user = await db_manager.get_user(telegram_id)

            spending = LwCoinTransaction(
                telegram_id=telegram_id,
                api_user_id=db_user.api_user_id if db_user else None,
                amount=amount,
                type='spent',
                feature_used=feature,
                description=description,
                date=datetime.utcnow().strftime('%Y-%m-%d')
            )
            session.add(spending)
            await session.commit()

            logger.info(f"Tracked coin usage: {telegram_id} spent {amount} coins on {feature}")
    except Exception as e:
        logger.error(f"Error tracking coin usage: {e}")


# Register handlers
def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))