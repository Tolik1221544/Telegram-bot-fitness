from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, \
    ConversationHandler
from bot.database import db_manager, User, Payment, ReferralLink
from bot.api_client import api_client
from bot.config import config
from bot.utils.charts import generate_spending_chart, generate_revenue_chart
from datetime import datetime, timedelta
import logging
import os
from sqlalchemy import select, func
import uuid

logger = logging.getLogger(__name__)

ADMIN_SET_REG_COINS = 100
ADMIN_SET_USER_EMAIL = 101
ADMIN_SET_USER_AMOUNT = 102
ADMIN_CREATE_REFERRAL = 103


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel command"""
    user = update.effective_user

    if user.id not in config.ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return

    keyboard = [
        [InlineKeyboardButton("💰 Установить бонус регистрации", callback_data="admin_set_reg_coins")],
        [InlineKeyboardButton("💸 Установить монеты пользователю", callback_data="admin_set_user_coins")],
        [InlineKeyboardButton("📊 График трат монет", callback_data="admin_spending_chart")],
        [InlineKeyboardButton("📈 График доходов", callback_data="admin_revenue_chart")],
        [InlineKeyboardButton("🔗 Создать реф. ссылку", callback_data="admin_create_referral")],
        [InlineKeyboardButton("📋 Список реф. ссылок", callback_data="admin_list_referrals")],
        [InlineKeyboardButton("👥 Статистика пользователей", callback_data="admin_user_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="start")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    stats_text = await get_admin_stats()

    await update.message.reply_text(
        f"⚙️ **Админ панель**\n\n{stats_text}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def get_admin_stats():
    """Get admin statistics"""
    async with db_manager.SessionLocal() as session:
        total_users = await session.execute(select(func.count(User.id)))
        total_users = total_users.scalar()

        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = await session.execute(
            select(func.count(User.id)).where(User.last_active >= week_ago)
        )
        active_users = active_users.scalar()

        total_payments = await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == 'completed')
        )
        total_revenue = total_payments.scalar() or 0

        today = datetime.utcnow().date()
        today_payments = await session.execute(
            select(func.sum(Payment.amount))
            .where(Payment.status == 'completed')
            .where(func.date(Payment.completed_at) == today)
        )
        today_revenue = today_payments.scalar() or 0

        return f"""📊 Статистика:
👥 Всего пользователей: {total_users}
🟢 Активных \\(7 дней\\): {active_users}
💰 Общий доход: {total_revenue:.2f} €
📅 Доход сегодня: {today_revenue:.2f} €"""


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callbacks"""
    query = update.callback_query
    user = query.from_user

    if user.id not in config.ADMIN_IDS:
        await query.answer("❌ Недостаточно прав", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    logger.info(f"Admin callback: {query.data} from user {user.id}")

    context.user_data.clear()

    if query.data == "admin_set_reg_coins":
        await query.message.reply_text(
            f"💰 Введите новое количество монет при регистрации\n"
            f"Текущее: {config.DEFAULT_REGISTRATION_COINS}\n\n"
            f"Или /cancel для отмены"
        )
        return ADMIN_SET_REG_COINS

    elif query.data == "admin_set_user_coins":
        await query.message.reply_text(
            "💸 Введите email пользователя:\n\n"
            "Или /cancel для отмены"
        )
        return ADMIN_SET_USER_EMAIL

    elif query.data == "admin_spending_chart":
        await send_spending_chart(query.message)
        return ConversationHandler.END

    elif query.data == "admin_revenue_chart":
        await send_revenue_chart(query.message)
        return ConversationHandler.END

    elif query.data == "admin_create_referral":
        await query.message.reply_text(
            "🔗 Введите название для реферальной ссылки\n"
            "Например: Фитнес-центр Москва\n\n"
            "Или /cancel для отмены"
        )
        return ADMIN_CREATE_REFERRAL

    elif query.data == "admin_list_referrals":
        await show_referral_links(query.message)
        return ConversationHandler.END

    elif query.data == "admin_user_stats":
        await show_user_stats(query.message)
        return ConversationHandler.END

    return ConversationHandler.END


async def set_registration_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coins = int(update.message.text)
        if coins < 0:
            raise ValueError("Negative coins")

        config.DEFAULT_REGISTRATION_COINS = coins

        keyboard = [[InlineKeyboardButton("🔙 В админ панель", callback_data="admin")]]

        await update.message.reply_text(
            f"✅ Бонус регистрации установлен: {coins} монет",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except ValueError:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="admin")]]
        await update.message.reply_text(
            "❌ Введите корректное число",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_SET_REG_COINS

    return ConversationHandler.END


async def set_user_coins_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()

    if '@' not in email or '.' not in email:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="admin")]]
        await update.message.reply_text(
            "❌ Неверный формат email. Попробуйте снова:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_SET_USER_EMAIL

    context.user_data['admin_target_email'] = email

    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="admin")]]

    await update.message.reply_text(
        f"📧 Email: {email}\n"
        "💰 Теперь введите количество монет:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_SET_USER_AMOUNT


async def set_user_coins_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coins = int(update.message.text)
        if coins < 0:
            raise ValueError("Negative")

        email = context.user_data.get('admin_target_email')
        if not email:
            await update.message.reply_text("❌ Ошибка: email не найден. Начните заново: /admin")
            return ConversationHandler.END

        keyboard = [[InlineKeyboardButton("🔙 В админ панель", callback_data="admin")]]

        # Send verification code
        success = await api_client.send_verification_code(email)
        if not success:
            await update.message.reply_text(
                f"❌ Пользователь {email} не найден",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END

        test_codes = {
            'test@lightweightfit.com': '123456',
            'demo@lightweightfit.com': '111111',
            'review@lightweightfit.com': '777777',
            'apple.review@lightweightfit.com': '999999',
            'dev@lightweightfit.com': '000000'
        }

        if email in test_codes:
            auth_result = await api_client.confirm_email(email, test_codes[email])
            token = auth_result['accessToken']

            # Set balance
            await api_client.set_balance(token, coins, 'admin')

            await update.message.reply_text(
                f"✅ Установлено {coins} монет для {email}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"📧 Код отправлен на {email}\n",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except ValueError:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="admin")]]
        await update.message.reply_text(
            "❌ Введите корректное число",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_SET_USER_AMOUNT
    except Exception as e:
        logger.error(f"Error setting user coins: {e}")
        keyboard = [[InlineKeyboardButton("🔙 В админ панель", callback_data="admin")]]
        await update.message.reply_text(
            f"❌ Ошибка: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        # Cleanup
        if 'admin_target_email' in context.user_data:
            del context.user_data['admin_target_email']

    return ConversationHandler.END


async def create_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new referral link"""
    name = update.message.text.strip()

    keyboard = [[InlineKeyboardButton("🔙 В админ панель", callback_data="admin")]]

    if not name:
        await update.message.reply_text(
            "❌ Название не может быть пустым",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    code = str(uuid.uuid4())[:8]

    async with db_manager.SessionLocal() as session:
        link = ReferralLink(
            code=code,
            name=name,
            creator_telegram_id=update.effective_user.id
        )
        session.add(link)
        await session.commit()

    bot_username = config.BOT_USERNAME.replace('@', '')
    link_url = f"https://t.me/{bot_username}?start={code}"

    await update.message.reply_text(
        f"✅ Реферальная ссылка создана!\n\n"
        f"📝 Название: {name}\n"
        f"🔗 Ссылка: `{link_url}`\n"
        f"📊 Код: {code}\n\n"
        f"Отправьте эту ссылку партнерам для отслеживания",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END


async def send_spending_chart(message):
    try:
        from bot.api_client import api_client

        # ✅ ИСПРАВЛЕНИЕ: Правильно получаем user_id в зависимости от типа message
        if hasattr(message, 'chat_id'):
            # Это callback_query.message
            user_id = message.chat_id
        elif hasattr(message, 'chat'):
            # Это обычное сообщение
            user_id = message.chat.id
        else:
            logger.error(f"❌ Cannot extract user_id from message object")
            await message.reply_text("❌ Ошибка определения пользователя")
            return

        logger.info(f"📊 Getting spending chart for admin user_id: {user_id}")

        # Получаем админа из БД
        admin_user = await db_manager.get_user(user_id)

        if not admin_user:
            logger.error(f"❌ Admin user {user_id} not found in DB")
            await message.reply_text("❌ Админ не найден. Сначала свяжите аккаунт через email")
            return

        if not admin_user.api_token:
            logger.error(f"❌ Admin user {user_id} has no API token")
            await message.reply_text(
                "❌ Аккаунт не привязан.\n"
                "Используйте кнопку '🔗 Связать аккаунт' в главном меню"
            )
            return

        logger.info(f"✅ Found admin with token, requesting data from server...")

        try:
            stats_response = await api_client._request(
                'GET',
                '/api/stats/coin-spending-daily?days=30',
                headers={'Authorization': f'Bearer {admin_user.api_token}'}
            )
        except Exception as api_error:
            logger.error(f"API request failed: {api_error}")
            await message.reply_text(f"❌ Ошибка API: {str(api_error)}")
            return

        if not stats_response:
            logger.warning("Empty response from API")
            await message.reply_text("📊 API вернул пустой ответ")
            return

        if 'data' in stats_response:
            daily_stats = stats_response['data']
        elif 'success' in stats_response and stats_response.get('data'):
            daily_stats = stats_response['data']
        elif isinstance(stats_response, list):
            daily_stats = stats_response
        else:
            logger.error(f"Unexpected API response structure: {stats_response}")
            await message.reply_text("❌ Неожиданный формат ответа от API")
            return

        if not daily_stats:
            await message.reply_text("📊 Нет данных о тратах за последние 30 дней")
            return

        logger.info(f"📊 Got {len(daily_stats)} days of data from server")

        # Генерируем график
        from bot.utils.charts import generate_spending_chart_from_server_data
        chart_path = await generate_spending_chart_from_server_data(daily_stats)

        with open(chart_path, 'rb') as photo:
            # Считаем общую сумму трат
            total_spent = sum(
                stat.get('TotalSpent', stat.get('totalSpent', 0))
                for stat in daily_stats
            )

            await message.reply_photo(
                photo=photo,
                caption=f"📊 График трат монет за 30 дней\n\n"
                        f"💸 Всего потрачено: {total_spent} монет\n"
                        f"📅 Дней с активностью: {len(daily_stats)}"
            )

        os.remove(chart_path)
        logger.info("✅ Spending chart sent successfully")

    except Exception as e:
        logger.error(f"Error generating spending chart: {e}")
        logger.exception("Full traceback:")
        await message.reply_text(f"❌ Ошибка генерации графика: {str(e)}")


async def send_revenue_chart(message):
    try:
        from bot.api_client import api_client

        if hasattr(message, 'chat_id'):
            user_id = message.chat_id
        elif hasattr(message, 'chat'):
            user_id = message.chat.id
        else:
            logger.error(f"❌ Cannot extract user_id from message object")
            await message.reply_text("❌ Ошибка определения пользователя")
            return

        logger.info(f"📈 Getting revenue chart for admin user_id: {user_id}")

        admin_user = await db_manager.get_user(user_id)

        if not admin_user:
            logger.error(f"❌ Admin user {user_id} not found in DB")
            await message.reply_text("❌ Админ не найден в БД. Используйте /start")
            return

        if not admin_user.api_token:
            logger.error(f"❌ Admin user {user_id} has no API token")
            await message.reply_text(
                "❌ Аккаунт не привязан.\n"
                "Используйте кнопку '🔗 Связать аккаунт' в главном меню"
            )
            return

        logger.info(f"✅ Found admin with token, requesting revenue data...")

        # Запрос к бэкенду
        try:
            revenue_response = await api_client._request(
                'GET',
                '/api/stats/revenue-daily?days=30',
                headers={'Authorization': f'Bearer {admin_user.api_token}'}
            )
        except Exception as api_error:
            logger.error(f"API request failed: {api_error}")
            await message.reply_text(f"❌ Ошибка API: {str(api_error)}")
            return

        if not revenue_response:
            logger.warning("Empty response from API")
            await message.reply_text("📈 API вернул пустой ответ")
            return

        if 'data' in revenue_response:
            daily_revenue = revenue_response['data']
        elif 'success' in revenue_response and revenue_response.get('data'):
            daily_revenue = revenue_response['data']
        elif isinstance(revenue_response, list):
            daily_revenue = revenue_response
        else:
            logger.error(f"Unexpected API response structure: {revenue_response}")
            await message.reply_text("❌ Неожиданный формат ответа от API")
            return

        if not daily_revenue:
            await message.reply_text("📈 Нет данных о доходах за последние 30 дней")
            return

        logger.info(f"📈 Got {len(daily_revenue)} days of revenue data")

        from bot.utils.charts import generate_revenue_chart_from_server_data
        chart_path = await generate_revenue_chart_from_server_data(daily_revenue, [])

        with open(chart_path, 'rb') as photo:
            total_revenue = sum(
                stat.get('TotalRevenue', stat.get('totalRevenue', 0))
                for stat in daily_revenue
            )

            await message.reply_photo(
                photo=photo,
                caption=f"📈 График доходов за 30 дней\n\n"
                        f"💰 Всего: {total_revenue:.2f} €\n"
                        f"📅 Дней с платежами: {len(daily_revenue)}"
            )

        os.remove(chart_path)
        logger.info("✅ Revenue chart sent successfully")

    except Exception as e:
        logger.error(f"Error generating revenue chart: {e}")
        logger.exception("Full traceback:")
        await message.reply_text(f"❌ Ошибка: {str(e)}")


async def show_referral_links(message):
    """Show all referral links with stats"""
    async with db_manager.SessionLocal() as session:
        result = await session.execute(
            select(ReferralLink)
            .where(ReferralLink.is_active == True)
            .order_by(ReferralLink.created_at.desc())
        )
        links = result.scalars().all()

    if not links:
        await message.reply_text("📋 Нет активных реферальных ссылок")
        return

    bot_username = config.BOT_USERNAME.replace('@', '')
    text = "📋 **Реферальные ссылки:**\n\n"

    for link in links[:10]:
        link_url = f"https://t.me/{bot_username}?start={link.code}"
        text += f"**{link.name}**\n"
        text += f"🔗 `{link_url}`\n"
        text += f"👁 Переходов: {link.clicks}\n"
        text += f"👤 Регистраций: {link.registrations}\n"
        text += f"💰 Покупок: {link.purchases}\n"
        text += f"💵 Доход: {link.total_revenue:.2f} €\n\n"

    await message.reply_text(text, parse_mode='Markdown')


async def show_user_stats(message):
    """Show detailed user statistics FROM BACKEND"""
    if hasattr(message, 'chat_id'):
        user_id = message.chat_id
    else:
        user_id = message.chat.id

    admin_user = await db_manager.get_user(user_id)

    if not admin_user or not admin_user.api_token:
        await message.reply_text("❌ Сначала привяжите аккаунт через /start")
        return

    try:
        from bot.api_client import api_client

        logger.info(f"📊 Getting user stats from backend for admin {user_id}")

        # 1. ✅ Используем /api/health/db-info
        db_info = await api_client._request(
            'GET',
            '/api/health/db-info'
        )

        total_users = db_info.get('users', 0)
        total_activities = db_info.get('activities', 0)
        total_food_intakes = db_info.get('foodIntakes', 0)
        total_steps_records = db_info.get('stepsRecords', 0)

        revenue_stats = await api_client._request(
            'GET',
            '/api/stats/revenue-by-source?days=30',
            headers={'Authorization': f'Bearer {admin_user.api_token}'}
        )

        tribute_count = revenue_stats.get('data', {}).get('tribute', {}).get('count', 0)
        mobile_count = revenue_stats.get('data', {}).get('mobile', {}).get('count', 0)
        total_active_subs = tribute_count + mobile_count

        tribute_revenue = revenue_stats.get('data', {}).get('tribute', {}).get('revenue', 0)
        mobile_revenue = revenue_stats.get('data', {}).get('mobile', {}).get('revenue', 0)
        total_revenue = revenue_stats.get('data', {}).get('total', {}).get('revenue', 0)

        text = "👥 **Статистика пользователей:**\n\n"
        text += f"📱 Всего пользователей: {total_users}\n"
        text += f"🔄 Активных подписок (30 дней): {total_active_subs}\n"
        text += f"  • 💳 Tribute: {tribute_count}\n"
        text += f"  • 📱 Mobile: {mobile_count}\n\n"

        text += f"**Активность пользователей:**\n"
        text += f"🏋️ Тренировок: {total_activities}\n"
        text += f"🍽 Приемов пищи: {total_food_intakes}\n"
        text += f"👣 Записей шагов: {total_steps_records}\n\n"

        text += f"**Доходы (30 дней):**\n"
        text += f"💰 Всего: {total_revenue:.2f} €\n"
        text += f"  • Tribute: {tribute_revenue:.2f} €\n"
        text += f"  • Mobile: {mobile_revenue:.2f} €\n"

        await message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        logger.exception("Full traceback:")
        await message.reply_text(f"❌ Ошибка получения статистики: {str(e)}")


async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    keyboard = [[InlineKeyboardButton("🔙 В админ панель", callback_data="admin")]]

    await update.message.reply_text(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def admin_callback_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin button click from main menu"""
    query = update.callback_query
    user = query.from_user

    if user.id not in config.ADMIN_IDS:
        await query.answer("❌ Недостаточно прав", show_alert=True)
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("💰 Установить бонус регистрации", callback_data="admin_set_reg_coins")],
        [InlineKeyboardButton("💸 Установить монеты пользователю", callback_data="admin_set_user_coins")],
        [InlineKeyboardButton("📊 График трат монет", callback_data="admin_spending_chart")],
        [InlineKeyboardButton("📈 График доходов", callback_data="admin_revenue_chart")],
        [InlineKeyboardButton("🔗 Создать реф. ссылку", callback_data="admin_create_referral")],
        [InlineKeyboardButton("📋 Список реф. ссылок", callback_data="admin_list_referrals")],
        [InlineKeyboardButton("👥 Статистика пользователей", callback_data="admin_user_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="start")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    stats_text = await get_admin_stats()

    await query.message.edit_text(
        f"⚙️ **Админ панель**\n\n{stats_text}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def register_admin_handlers(application):
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(admin_callback_button, pattern="^admin$"))

    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_admin_callback, pattern="^admin_")
        ],
        states={
            ADMIN_SET_REG_COINS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_registration_coins),
                CallbackQueryHandler(cancel_admin_action, pattern="^admin$")
            ],
            ADMIN_SET_USER_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_user_coins_email),
                CallbackQueryHandler(cancel_admin_action, pattern="^admin$")
            ],
            ADMIN_SET_USER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_user_coins_amount),
                CallbackQueryHandler(cancel_admin_action, pattern="^admin$")
            ],
            ADMIN_CREATE_REFERRAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_referral_link),
                CallbackQueryHandler(cancel_admin_action, pattern="^admin$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin_action),
            CommandHandler("start", cancel_admin_action),
            CallbackQueryHandler(cancel_admin_action, pattern="^admin$"),
            CallbackQueryHandler(admin_callback_button, pattern="^admin$")
        ],
        per_user=True,
        per_chat=True,
        per_message=False,
        allow_reentry=True,
        conversation_timeout=300
    )

    application.add_handler(admin_conv)