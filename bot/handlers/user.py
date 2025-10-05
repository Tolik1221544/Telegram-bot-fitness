from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from bot.database import db_manager
from bot.api_client import api_client
from bot.config import config
import logging

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_EMAIL, AWAITING_CODE = range(2)


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user balance"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await db_manager.get_user(user.id)

    if not db_user or not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await query.message.edit_text(
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
            expiry = balance.get('subscriptionExpiresAt', 'Не указано')
            if expiry and len(expiry) >= 10:
                expiry = expiry[:10]
            text += f"\n📅 Подписка до: {expiry}"
        else:
            text += "\n📅 Подписка: не активна"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        await query.message.edit_text(
            "❌ Ошибка получения баланса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="start")]])
        )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await db_manager.get_user(user.id)

    if not db_user or not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await query.message.edit_text(
            "❌ Сначала свяжите аккаунт с приложением",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    try:
        stats = await api_client.get_user_stats(db_user.api_token)

        text = f"""📊 **Ваша статистика**

🏋️ Тренировок: {stats.get('workouts', 0)}
📸 Фото: {stats.get('photos', 0)}
🎤 Голосовых: {stats.get('voice', 0)}
💬 Текстовых: {stats.get('text', 0)}
💰 Потрачено монет: {stats.get('coinsSpent', 0)}
"""

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await query.message.edit_text(
            "❌ Ошибка получения статистики",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="start")]])
        )


async def start_link_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start account linking process"""
    query = update.callback_query
    await query.answer()

    await query.message.edit_text(
        "🔗 **Связывание аккаунта**\n\n"
        "Введите email, который используете в приложении Fitness Tracker:",
        parse_mode='Markdown'
    )

    return AWAITING_EMAIL


async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle email input"""
    email = update.message.text.strip()

    # Validate email
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await update.message.reply_text("❌ Неверный формат email. Попробуйте снова:")
        return AWAITING_EMAIL

    try:
        # Send verification code
        success = await api_client.send_verification_code(email)

        if success:
            context.user_data['linking_email'] = email
            await update.message.reply_text(
                f"✅ Код подтверждения отправлен на {email}\n\n"
                "Введите код из письма:"
            )
            return AWAITING_CODE
        else:
            await update.message.reply_text(
                "❌ Не удалось отправить код. Проверьте email и попробуйте снова:",
            )
            return AWAITING_EMAIL

    except Exception as e:
        logger.error(f"Error sending verification code: {e}")
        await update.message.reply_text(
            "❌ Ошибка отправки кода. Попробуйте позже.\n"
            "Используйте /start для возврата в меню."
        )
        return ConversationHandler.END


async def handle_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification code input"""
    code = update.message.text.strip()
    email = context.user_data.get('linking_email')

    if not email:
        await update.message.reply_text("❌ Ошибка. Начните заново с /start")
        return ConversationHandler.END

    try:
        # Confirm email
        result = await api_client.confirm_email(email, code)

        if 'accessToken' in result:
            # Save token to database
            user = update.effective_user
            db_user = await db_manager.get_user(user.id)

            async with db_manager.SessionLocal() as session:
                db_user.email = email
                db_user.api_token = result['accessToken']
                db_user.api_user_id = result.get('userId')
                session.add(db_user)
                await session.commit()

            await update.message.reply_text(
                "✅ Аккаунт успешно связан!\n\n"
                "Теперь вы можете пользоваться всеми функциями бота.\n"
                "Используйте /start для главного меню."
            )

            # Clear user data
            context.user_data.clear()

            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Неверный код. Попробуйте снова:"
            )
            return AWAITING_CODE

    except Exception as e:
        logger.error(f"Error confirming code: {e}")
        await update.message.reply_text(
            "❌ Ошибка подтверждения кода. Попробуйте позже.\n"
            "Используйте /start для возврата в меню."
        )
        return ConversationHandler.END


async def cancel_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel account linking"""
    await update.message.reply_text(
        "❌ Связывание аккаунта отменено.\n"
        "Используйте /start для возврата в меню."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def show_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show restore purchases"""
    query = update.callback_query
    await query.answer()

    await query.message.edit_text(
        "🔄 **Восстановление покупок**\n\n"
        "Эта функция автоматически синхронизирует ваши покупки "
        "между устройствами.\n\n"
        "Все ваши подписки и монеты будут восстановлены.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="start")]]),
        parse_mode='Markdown'
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    query = update.callback_query
    await query.answer()

    help_text = """ℹ️ **Помощь**

**Основные команды:**
/start - Главное меню
/help - Эта справка

**Как пользоваться:**
1️⃣ Свяжите аккаунт с приложением
2️⃣ Купите монеты или подписку
3️⃣ Используйте монеты в приложении

**Поддержка:**
Если у вас возникли проблемы, напишите @support
"""

    await query.message.edit_text(
        help_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="start")]]),
        parse_mode='Markdown'
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await db_manager.get_user(user.id)

    welcome_text = f"👋 С возвращением, {user.first_name}!\n\n"

    if db_user and db_user.api_token:
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

    if user.id in config.ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(welcome_text, reply_markup=reply_markup)


def register_user_handlers(application):
    """Register user handlers"""
    # Callback handlers
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^start$"))  # Добавили
    application.add_handler(CallbackQueryHandler(show_balance, pattern="^balance$"))
    application.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(show_restore, pattern="^restore$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern="^help$"))

    # Account linking conversation
    link_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_link_account, pattern="^link_account$")],
        states={
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_input)],
            AWAITING_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_input)],
        },
        fallbacks=[MessageHandler(filters.Regex('^/cancel$'), cancel_linking)],
        per_message=False  # Добавили
    )

    application.add_handler(link_conv_handler)