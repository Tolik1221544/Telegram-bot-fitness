import logging
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.database import db_manager
from bot.api_client import api_client

logger = logging.getLogger(__name__)

TRIBUTE_STORE_LINK = "https://t.me/tribute/app?startapp=sDlI"

SUBSCRIPTION_PACKAGES = [
    {'id': '1month', 'name': '1 месяц', 'coins': 100, 'days': 30, 'price': 2},
    {'id': '3months', 'name': '3 месяца', 'coins': 300, 'days': 90, 'price': 5},
    {'id': '6months', 'name': '6 месяцев', 'coins': 600, 'days': 180, 'price': 10},
    {'id': 'year', 'name': 'Год', 'coins': 1200, 'days': 365, 'price': 20}
]


async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем что пользователь привязал аккаунт
    from bot.database import db_manager
    db_user = await db_manager.get_user(user.id)

    if not db_user:
        await query.message.edit_text("❌ Используйте /start")
        return

    if not db_user.api_token:
        keyboard = [
            [InlineKeyboardButton("🔗 Сначала свяжите аккаунт", callback_data="link_account")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]
        await query.message.edit_text(
            "❌ Для покупки подписки сначала нужно связать аккаунт с приложением.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    order_id = str(uuid.uuid4())[:8]

    selected_package = SUBSCRIPTION_PACKAGES[0]  # По умолчанию 1 месяц

    try:
        await api_client.create_pending_payment(
            order_id=order_id,
            telegram_id=user.id,
            amount=selected_package['price'],
            currency='EUR',
            package_id=selected_package['id'],
            coins_amount=selected_package['coins'],
            duration_days=selected_package['days']
        )

        logger.info(f"📝 Created pending payment {order_id} for user {user.id}")
    except Exception as e:
        logger.error(f"❌ Failed to create pending payment: {e}")
        await query.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
        return

    text = f"""💳 **LightWeight PAY**

Здесь вы можете купить LW coins со скидкой, оплатить картой любой страны и любым удобным способом.

**📋 Доступные тарифы:**

- **1 месяц** — 2 € → 100 монет на 30 дней
- **3 месяца** — 5 € → 300 монет на 90 дней  
- **6 месяцев** — 10 € → 600 монет на 180 дней
- **Год** — 20 € → 1200 монет на 365 дней

**Как купить:**
1️⃣ Нажмите кнопку "💳 Открыть магазин Tribute"
2️⃣ Выберите нужный период подписки
3️⃣ Добавьте удобный для вас способ оплаты и оплатите покупку

⚡️ Монеты зачислятся автоматически в течение 2 минут!
"""

    keyboard = [
        [InlineKeyboardButton("💳 Открыть магазин Tribute", url=TRIBUTE_STORE_LINK)],
        [InlineKeyboardButton("🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = query.data.replace("check_payment_", "")

    try:
        status = await api_client.check_payment_status(order_id)

        if status.get('status') == 'completed':
            await query.message.edit_text(
                f"✅ Платёж успешно обработан!\n"
                f"💰 Начислено монет: {status.get('coins_added', 0)}\n\n"
                f"Спасибо за покупку!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="start")]])
            )
        elif status.get('status') == 'pending':
            await query.answer("⏳ Платёж ещё обрабатывается. Подождите 1-2 минуты и проверьте снова.", show_alert=True)
        else:
            await query.answer("❌ Платёж не найден или отклонён", show_alert=True)

    except Exception as e:
        logger.error(f"Error checking payment: {e}")
        await query.answer("❌ Ошибка проверки платежа", show_alert=True)


def register_payment_handlers(application):
    """Регистрация handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern="^check_payment_"))