import asyncio
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.api_client import api_client
from bot.config import config
import logging

logger = logging.getLogger(__name__)

SUBSCRIPTION_PACKAGES = [
    {
        'id': '1month',
        'name': '1 месяц',
        'coins': 100,
        'days': 30,
        'price': 2,
        'currency': '€',
        'description': '100 монет на 30 дней'
    },
    {
        'id': '3months',
        'name': '3 месяца',
        'coins': 300,
        'days': 90,
        'price': 5,
        'currency': '€',
        'description': '300 монет на 90 дней'
    },
    {
        'id': '6months',
        'name': '6 месяцев',
        'coins': 600,
        'days': 180,
        'price': 10,
        'currency': '€',
        'description': '600 монет на 180 дней'
    },
    {
        'id': 'year',
        'name': 'Год',
        'coins': 1200,
        'days': 365,
        'price': 20,
        'currency': '€',
        'description': '1200 монет на 365 дней'
    }
]


async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать доступные подписки"""
    query = update.callback_query
    await query.answer()

    keyboard = []
    for package in SUBSCRIPTION_PACKAGES:
        button_text = f"📅 {package['name']} - {package['price']} {package['currency']}"
        callback_data = f"buy_package_{package['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """💳 **Покупка подписки LightWeight**

✅ Оплата через Tribute
✅ Безопасно и удобно
✅ Поддержка карт любых стран
✅ Автоматическое начисление монет

Выберите период подписки:"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора пакета подписки"""
    query = update.callback_query
    user = query.from_user
    callback_data = query.data

    if callback_data.startswith("buy_package_"):
        package_id = callback_data.replace("buy_package_", "")
        package = next((p for p in SUBSCRIPTION_PACKAGES if p['id'] == package_id), None)
    else:
        await query.answer("❌ Пакет не найден", show_alert=True)
        return

    if not package:
        await query.answer("❌ Пакет не найден", show_alert=True)
        return

    await query.answer()

    from bot.database import db_manager
    db_user = await db_manager.get_user(user.id)

    if not db_user:
        await query.message.reply_text("❌ Используйте /start")
        return

    if not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await query.message.reply_text(
            "❌ Сначала свяжите аккаунт",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    order_id = f"tg_{user.id}_{uuid.uuid4().hex[:8]}"

    logger.info(f"💳 User {user.id} starting payment for {package['name']}")
    logger.info(
        f"📦 Package: {package['coins']} coins, {package['days']} days, {package['price']} {package['currency']}")
    logger.info(f"🔗 Order ID: {order_id}")

    try:
        pending_result = await api_client._request(
            'POST',
            '/api/tribute-pending/create',
            json_data={
                'orderId': order_id,
                'telegramId': user.id,
                'amount': package['price'],
                'currency': 'EUR',
                'packageId': package['id'],
                'coinsAmount': package['coins'],
                'durationDays': package['days']
            }
        )

        if not pending_result.get('success'):
            logger.error(f"❌ Failed to create pending payment: {pending_result}")
            await query.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
            return

        logger.info(f"✅ Pending payment created on backend")

    except Exception as e:
        logger.error(f"❌ Error creating pending payment: {e}")
        await query.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
        return

    payment_url = "https://t.me/tribute/app?startapp=sDlI"

    keyboard = [
        [InlineKeyboardButton("💳 Открыть магазин Tribute", url=payment_url)],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""💳 **Оплата через Tribute**

📦 Пакет: **{package['name']}**
💰 Монет: {package['coins']}
📅 Период: {package['days']} дней
💵 К оплате: **{package['price']} {package['currency']}**

📝 **ID заказа:** `{order_id}`

**Инструкция:**

1️⃣ Нажмите "💳 Открыть магазин Tribute"
2️⃣ Выберите период: **{package['name']}** ({package['price']} {package['currency']})
3️⃣ Выберите способ оплаты
4️⃣ Подтвердите платёж

⚡️ Монеты зачислятся **автоматически** в течение 2 минут после оплаты!

"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


def register_payment_handlers(application):
    """Регистрация handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_package_"))