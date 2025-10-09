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

    if query.data == "admin_set_reg_coins":
        await query.message.reply_text(
            f"💰 Введите новое количество монет при регистрации\n"
            f"Текущее: {config.DEFAULT_REGISTRATION_COINS}"
        )
        return ADMIN_SET_REG_COINS

    elif query.data == "admin_set_user_coins":
        await query.message.reply_text(
            "💸 Введите email пользователя:"
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
            "Например: Фитнес-центр Москва"
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
    """Set registration bonus coins"""
    try:
        coins = int(update.message.text)
        if coins < 0:
            raise ValueError("Negative coins")

        config.DEFAULT_REGISTRATION_COINS = coins
        await update.message.reply_text(f"✅ Бонус регистрации: {coins} монет")
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")

    return ConversationHandler.END


async def set_user_coins_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Get email"""
    email = update.message.text.strip()
    context.user_data['admin_target_email'] = email

    await update.message.reply_text(
        f"📧 Email: {email}\n"
        "💰 Теперь введите количество монет:"
    )
    return ADMIN_SET_USER_AMOUNT


async def set_user_coins_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Get amount and set coins"""
    try:
        coins = int(update.message.text)
        if coins < 0:
            raise ValueError("Negative")

        email = context.user_data.get('admin_target_email')
        if not email:
            await update.message.reply_text("❌ Ошибка: email не найден")
            return ConversationHandler.END

        # Send verification code
        success = await api_client.send_verification_code(email)
        if not success:
            await update.message.reply_text(f"❌ Пользователь {email} не найден")
            return ConversationHandler.END

        # Auto-confirm for test accounts
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
                f"✅ Установлено {coins} монет для {email}"
            )
        else:
            await update.message.reply_text(
                f"📧 Код отправлен на {email}\n"
                f"Пользователь должен подтвердить в приложении"
            )

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Error setting user coins: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")
    finally:
        # Cleanup
        if 'admin_target_email' in context.user_data:
            del context.user_data['admin_target_email']

    return ConversationHandler.END


async def create_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new referral link"""
    name = update.message.text.strip()

    if not name:
        await update.message.reply_text("❌ Название не может быть пустым")
        return ConversationHandler.END

    # Generate unique code
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
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def send_spending_chart(message):
    """Send coin spending chart"""
    try:
        async with db_manager.SessionLocal() as session:
            # Получаем транзакции за последние 30 дней
            start_date = datetime.utcnow() - timedelta(days=30)

            # Импортируем здесь, чтобы избежать циклических импортов
            from bot.database import LwCoinTransaction

            result = await session.execute(
                select(
                    func.date(LwCoinTransaction.created_at).label('date'),
                    func.sum(LwCoinTransaction.amount).label('total')
                )
                .where(LwCoinTransaction.created_at >= start_date)
                .where(LwCoinTransaction.amount < 0)  # Только траты
                .group_by(func.date(LwCoinTransaction.created_at))
                .order_by(func.date(LwCoinTransaction.created_at))
            )

            data = result.all()

        if not data:
            await message.reply_text("📊 Нет данных о тратах за последние 30 дней")
            return

        # Generate chart
        chart_path = await generate_spending_chart(data)

        with open(chart_path, 'rb') as photo:
            await message.reply_photo(
                photo=photo,
                caption="📊 График трат монет за 30 дней"
            )

        # Cleanup
        os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating spending chart: {e}")
        logger.exception("Full traceback:")
        await message.reply_text("❌ Ошибка генерации графика")


async def send_revenue_chart(message):
    """Send revenue chart"""
    try:
        async with db_manager.SessionLocal() as session:
            start_date = datetime.utcnow() - timedelta(days=30)

            result = await session.execute(
                select(
                    func.date(Payment.completed_at).label('date'),
                    func.sum(Payment.amount).label('total')
                )
                .where(Payment.status == 'completed')
                .where(Payment.completed_at >= start_date)
                .group_by(func.date(Payment.completed_at))
                .order_by(func.date(Payment.completed_at))
            )

            data = result.all()

        if not data:
            await message.reply_text("📈 Нет данных о доходах за последние 30 дней")
            return

        # Generate chart
        chart_path = await generate_revenue_chart(data)

        with open(chart_path, 'rb') as photo:
            await message.reply_photo(
                photo=photo,
                caption="📈 График доходов за 30 дней"
            )

        os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating revenue chart: {e}")
        logger.exception("Full traceback:")
        await message.reply_text("❌ Ошибка генерации графика")


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
    """Show detailed user statistics"""
    async with db_manager.SessionLocal() as session:
        result = await session.execute(
            select(
                User.referred_by,
                func.count(User.id).label('count')
            )
            .group_by(User.referred_by)
        )
        referral_stats = result.all()

        result = await session.execute(
            select(func.count(Payment.id))
            .where(Payment.status == 'completed')
            .where(Payment.completed_at >= datetime.utcnow() - timedelta(days=30))
        )
        active_subs = result.scalar()

    text = "👥 **Статистика пользователей:**\n\n"
    text += f"🔄 Активных подписок: {active_subs}\n\n"
    text += "**Источники регистраций:**\n"

    for source, count in referral_stats[:10]:
        if source:
            text += f"• {source}: {count} чел\\.\n"
        else:
            text += f"• Прямые: {count} чел\\.\n"

    await message.reply_text(text, parse_mode='Markdown')


async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel admin action"""
    await update.message.reply_text("❌ Отменено\n/admin - вернуться в панель")
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
    """Register admin handlers"""
    application.add_handler(CommandHandler("admin", admin_command))

    application.add_handler(CallbackQueryHandler(admin_callback_button, pattern="^admin$"))

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_admin_callback, pattern="^admin_")],
        states={
            ADMIN_SET_REG_COINS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_registration_coins)
            ],
            ADMIN_SET_USER_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_user_coins_email)
            ],
            ADMIN_SET_USER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_user_coins_amount)
            ],
            ADMIN_CREATE_REFERRAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_referral_link)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_admin_action)]
    )

    application.add_handler(admin_conv)