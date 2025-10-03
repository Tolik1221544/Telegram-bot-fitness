from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, \
    ConversationHandler
from bot.database import db_manager, User, Payment, CoinSpending
from bot.api_client import api_client
from bot.config import config
from bot.utils.charts import generate_spending_chart, generate_revenue_chart
from datetime import datetime, timedelta
import logging
import re
from sqlalchemy import select, func
import uuid

logger = logging.getLogger(__name__)

# Conversation states
SET_REGISTRATION_COINS, SET_USER_COINS, CREATE_REFERRAL = range(3)

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
        # User stats
        total_users = await session.execute(select(func.count(User.id)))
        total_users = total_users.scalar()

        # Active users (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = await session.execute(
            select(func.count(User.id)).where(User.last_active >= week_ago)
        )
        active_users = active_users.scalar()

        # Payment stats
        total_payments = await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == 'completed')
        )
        total_revenue = total_payments.scalar() or 0

        # Today's revenue
        today = datetime.utcnow().date()
        today_payments = await session.execute(
            select(func.sum(Payment.amount))
            .where(Payment.status == 'completed')
            .where(func.date(Payment.completed_at) == today)
        )
        today_revenue = today_payments.scalar() or 0

        return f"""
📊 **Статистика:**
👥 Всего пользователей: {total_users}
🟢 Активных (7 дней): {active_users}
💰 Общий доход: {total_revenue:.2f} ₽
📅 Доход сегодня: {today_revenue:.2f} ₽
"""

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callbacks"""
    query = update.callback_query
    user = query.from_user

    if user.id not in config.ADMIN_IDS:
        await query.answer("❌ Недостаточно прав", show_alert=True)
        return

    await query.answer()

    if query.data == "admin_set_reg_coins":
        await query.message.reply_text(
            "💰 Введите новое количество монет при регистрации (текущее: {})".format(
                config.DEFAULT_REGISTRATION_COINS
            )
        )
        return SET_REGISTRATION_COINS

    elif query.data == "admin_set_user_coins":
        await query.message.reply_text(
            "💸 Введите email пользователя и количество монет через пробел\n"
            "Например: user@example.com 100"
        )
        return SET_USER_COINS

    elif query.data == "admin_spending_chart":
        await send_spending_chart(query.message)

    elif query.data == "admin_revenue_chart":
        await send_revenue_chart(query.message)

    elif query.data == "admin_create_referral":
        await query.message.reply_text(
            "🔗 Введите название для реферальной ссылки\n"
            "Например: Фитнес-центр Москва"
        )
        return CREATE_REFERRAL

    elif query.data == "admin_list_referrals":
        await show_referral_links(query.message)

    elif query.data == "admin_user_stats":
        await show_user_stats(query.message)

async def set_registration_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set registration bonus coins"""
    try:
        coins = int(update.message.text)
        if coins < 0:
            raise ValueError("Coins must be positive")

        # Update config (in real app, save to database/file)
        config.DEFAULT_REGISTRATION_COINS = coins

        await update.message.reply_text(
            f"✅ Бонус регистрации установлен: {coins} монет"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")

    return ConversationHandler.END

async def set_user_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set user coins by email"""
    try:
        parts = update.message.text.split()
        if len(parts) != 2:
            raise ValueError("Invalid format")

        email = parts[0]
        coins = int(parts[1])

        if coins < 0:
            raise ValueError("Coins must be positive")

        # Send verification code
        success = await api_client.send_verification_code(email)
        if not success:
            await update.message.reply_text(f"❌ Не удалось найти пользователя {email}")
            return ConversationHandler.END

        # Auto-confirm with test code if it's a test account
        test_codes = {
            'test@lightweightfit.com': '123456',
            'demo@lightweightfit.com': '111111'
        }

        if email in test_codes:
            auth_result = await api_client.confirm_email(email, test_codes[email])
            token = auth_result['accessToken']

            # Set balance
            result = await api_client.set_balance(token, coins, 'admin')

            await update.message.reply_text(
                f"✅ Установлено {coins} монет для {email}"
            )
        else:
            await update.message.reply_text(
                f"📧 Код отправлен на {email}\n"
                f"Пользователь должен подтвердить в приложении"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
        # Get spending data
        async with db_manager.SessionLocal() as session:
            # Last 30 days
            start_date = datetime.utcnow() - timedelta(days=30)

            result = await session.execute(
                select(
                    CoinSpending.date,
                    func.sum(CoinSpending.amount).label('total')
                )
                .where(CoinSpending.timestamp >= start_date)
                .group_by(CoinSpending.date)
                .order_by(CoinSpending.date)
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

        # Clean up
        os.remove(chart_path)

    except Exception as e:
        logger.error(f"Error generating spending chart: {e}")
        await message.reply_text("❌ Ошибка генерации графика")

async def send_revenue_chart(message):
    """Send revenue chart"""
    try:
        async with db_manager.SessionLocal() as session:
    # Last 30 days
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

# Clean up
os.remove(chart_path)

except Exception as e:
logger.error(f"Error generating revenue chart: {e}")
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

    for link in links[:10]:  # Show last 10
        link_url = f"https://t.me/{bot_username}?start={link.code}"
        text += f"**{link.name}**\n"
        text += f"🔗 `{link_url}`\n"
        text += f"👁 Переходов: {link.clicks}\n"
        text += f"👤 Регистраций: {link.registrations}\n"
        text += f"💰 Покупок: {link.purchases}\n"
        text += f"💵 Доход: {link.total_revenue:.2f} ₽\n\n"

    await message.reply_text(text, parse_mode='Markdown')

async def show_user_stats(message):
    """Show detailed user statistics"""
    async with db_manager.SessionLocal() as session:
        # User distribution by registration source
        result = await session.execute(
            select(
                User.referred_by,
                func.count(User.id).label('count')
            )
            .group_by(User.referred_by)
        )
        referral_stats = result.all()

        # Active subscriptions
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
            text += f"• {source}: {count} чел.\n"
        else:
            text += f"• Прямые: {count} чел.\n"

    await message.reply_text(text, parse_mode='Markdown')


# Register admin handlers
def register_admin_handlers(application):
    application.add_handler(CommandHandler("admin", admin_command))

    # Conversation handler for admin actions
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_admin_callback, pattern="^admin_")
        ],
        states={
            SET_REGISTRATION_COINS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_registration_coins)],
            SET_USER_COINS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_user_coins)],
            CREATE_REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_referral_link)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    application.add_handler(conv_handler)