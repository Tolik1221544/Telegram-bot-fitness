from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, \
    CommandHandler
from bot.database import db_manager
from bot.api_client import api_client
from bot.config import config
import logging

logger = logging.getLogger(__name__)

USER_AWAITING_EMAIL = 200
USER_AWAITING_CODE = 201


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
        from datetime import datetime
        stats = await api_client.get_user_stats(db_user.api_token)

        text = f"""📊 **Ваша статистика**

🏋️ Тренировок: {stats.get('totalActivities', 0)}
🍽 Приемов пищи: {stats.get('totalMeals', 0)}
💰 Потрачено монет: {db_user.total_spent or 0}
📅 С нами: {(datetime.utcnow() - db_user.created_at).days} дней
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

    context.user_data.clear()

    logger.info(f"User {query.from_user.id} starting account linking")

    keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        "🔗 **Связывание аккаунта**\n\n"
        "Введите email, который используете в приложении Lightweight:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return USER_AWAITING_EMAIL


async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle email input"""
    email = update.message.text.strip()

    # Validate email
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Неверный формат email. Попробуйте снова:",
            reply_markup=reply_markup
        )
        return USER_AWAITING_EMAIL

    try:
        # Send verification code
        success = await api_client.send_verification_code(email)

        if success:
            context.user_data['linking_email'] = email

            keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ Код подтверждения отправлен на {email}\n\n"
                "Введите код из письма:",
                reply_markup=reply_markup
            )
            return USER_AWAITING_CODE
        else:
            keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "❌ Не удалось отправить код. Проверьте email:",
                reply_markup=reply_markup
            )
            return USER_AWAITING_EMAIL

    except Exception as e:
        logger.error(f"Error sending verification code: {e}")

        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Ошибка отправки кода. Попробуйте позже.",
            reply_markup=reply_markup
        )

        context.user_data.clear()
        return ConversationHandler.END


async def handle_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification code input"""
    code = update.message.text.strip()
    email = context.user_data.get('linking_email')

    if not email:
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Ошибка. Начните заново: /start",
            reply_markup=reply_markup
        )

        context.user_data.clear()
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
                db_user.api_user_id = result.get('user', {}).get('id')
                session.add(db_user)
                await session.commit()

            keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="start")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "✅ Аккаунт успешно связан!\n\n"
                "Теперь вы можете пользоваться всеми функциями бота.",
                reply_markup=reply_markup
            )

            context.user_data.clear()

            logger.info(f"User {user.id} successfully linked account")

            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "❌ Неверный код. Попробуйте снова:",
                reply_markup=reply_markup
            )
            return USER_AWAITING_CODE

    except Exception as e:
        logger.error(f"Error confirming code: {e}")

        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Ошибка подтверждения. Попробуйте позже.",
            reply_markup=reply_markup
        )

        context.user_data.clear()
        return ConversationHandler.END

async def handle_code_input_with_telegram_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification code input and link Telegram ID"""
    code = update.message.text.strip()
    email = context.user_data.get('linking_email')

    if not email:
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Ошибка. Начните заново: /start",
            reply_markup=reply_markup
        )

        context.user_data.clear()
        return ConversationHandler.END

    try:
        # Confirm email
        result = await api_client.confirm_email(email, code)

        if 'accessToken' in result:
            user = update.effective_user
            db_user = await db_manager.get_user(user.id)

            # Связываем Telegram ID с аккаунтом на сервере
            link_result = await api_client.link_telegram_account(
                result['accessToken'],
                user.id,
                user.username
            )

            if link_result.get('success'):
                logger.info(f"✅ Telegram ID {user.id} linked to server account")

            # Сохраняем токен в локальной БД бота
            async with db_manager.SessionLocal() as session:
                db_user.email = email
                db_user.api_token = result['accessToken']
                db_user.api_user_id = result.get('user', {}).get('id')
                session.add(db_user)
                await session.commit()

            # Проверяем последний платеж через Tribute
            try:
                payment_status = await api_client.check_tribute_payment(user.id)
                if payment_status.get('success') and payment_status.get('subscription'):
                    sub = payment_status['subscription']
                    if sub.get('isActive'):
                        await update.message.reply_text(
                            f"💳 Обнаружена активная подписка!\n"
                            f"Тип: {sub.get('type')}\n"
                            f"Действует до: {sub.get('expiresAt', 'н/д')[:10] if sub.get('expiresAt') else 'н/д'}"
                        )
            except Exception as e:
                logger.info(f"No active Tribute subscription found: {e}")

            keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="start")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Получаем баланс
            try:
                balance = await api_client.get_balance(result['accessToken'])
                balance_text = f"\n💰 Ваш баланс: {balance.get('balance', 0)} монет"

                if balance.get('hasActiveSubscription'):
                    expiry = balance.get('subscriptionExpiresAt', '')
                    if expiry and len(expiry) >= 10:
                        balance_text += f"\n📅 Подписка активна до: {expiry[:10]}"
            except:
                balance_text = ""

            await update.message.reply_text(
                f"✅ Аккаунт успешно связан!{balance_text}\n\n"
                "Теперь вы можете:\n"
                "• Покупать подписки через Tribute\n"
                "• Отслеживать баланс монет\n"
                "• Видеть статистику использования",
                reply_markup=reply_markup
            )

            context.user_data.clear()

            logger.info(f"User {user.id} successfully linked account with Telegram ID on server")

            return ConversationHandler.END
        else:
            keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data="cancel_linking")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "❌ Неверный код. Попробуйте снова:",
                reply_markup=reply_markup
            )
            return USER_AWAITING_CODE

    except Exception as e:
        logger.error(f"Error confirming code: {e}")

        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Ошибка подтверждения. Попробуйте позже.",
            reply_markup=reply_markup
        )

        context.user_data.clear()
        return ConversationHandler.END

async def check_subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Tribute subscription status"""
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
        # Проверяем статус платежа на сервере
        payment_status = await api_client.check_tribute_payment(user.id)

        if payment_status.get('success') and payment_status.get('subscription'):
            sub = payment_status['subscription']

            status_text = f"""💳 **Статус подписки Tribute**

📦 Тип: {sub.get('type', 'н/д')}
💵 Стоимость: {sub.get('price', 0):.2f} €
📅 Куплена: {sub.get('purchasedAt', 'н/д')[:10] if sub.get('purchasedAt') else 'н/д'}
⏰ Истекает: {sub.get('expiresAt', 'н/д')[:10] if sub.get('expiresAt') else 'н/д'}
✅ Статус: {'Активна' if sub.get('isActive') else 'Неактивна'}"""

            balance = await api_client.get_balance(db_user.api_token)
            if balance:
                status_text += f"\n\n💰 Текущий баланс: {balance.get('balance', 0)} монет"

                if balance.get('hasActiveSubscription'):
                    status_text += f"\n📊 Подписочных монет: {balance.get('subscriptionCoinsRemaining', 0)}"

        else:
            status_text = """💳 **Статус подписки**

❌ Активная подписка не найдена

Купите подписку через Tribute для получения монет."""

        keyboard = [
            [InlineKeyboardButton("💳 Купить подписку", callback_data="subscriptions")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]

        await query.message.edit_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error checking subscription status: {e}")
        await query.message.edit_text(
            "❌ Ошибка проверки статуса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="start")]])
        )
async def cancel_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel account linking"""
    query = update.callback_query

    logger.info(f"User {update.effective_user.id} cancelled account linking")

    if query:
        await query.answer("❌ Отменено")

        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "❌ Связывание отменено.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Связывание отменено.",
            reply_markup=reply_markup
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
/balance - Проверить баланс
/admin - Админ панель (для админов)

**Как пользоваться:**
1️⃣ Свяжите аккаунт с приложением
2️⃣ Купите монеты или подписку
3️⃣ Используйте монеты в приложении

**Поддержка:**
Если у вас проблемы, напишите @support
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

    context.user_data.clear()

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
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^start$"))

    application.add_handler(CallbackQueryHandler(show_balance, pattern="^balance$"))
    application.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(show_restore, pattern="^restore$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern="^help$"))

    link_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_link_account, pattern="^link_account$")
        ],
        states={
            USER_AWAITING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_input),
                CallbackQueryHandler(cancel_linking, pattern="^cancel_linking$")
            ],
            USER_AWAITING_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_input),
                CallbackQueryHandler(cancel_linking, pattern="^cancel_linking$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_linking),
            CommandHandler("start", cancel_linking),
            CallbackQueryHandler(cancel_linking, pattern="^cancel_linking$"),
            CallbackQueryHandler(back_to_start, pattern="^start$")
        ],

        per_user=True,
        per_chat=True,
        per_message=False,
        allow_reentry=True
    )

    application.add_handler(link_conv)