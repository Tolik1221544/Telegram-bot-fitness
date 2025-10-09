from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.database import db_manager, Payment
from bot.api_client import api_client
from bot.config import config
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class TributePayment:
    """Tribute.tg payment integration"""

    def __init__(self):
        self.shop_url = "https://t.me/tribute/app?startapp=sDlI"

    def get_payment_link(self, user_id: int, package_id: str) -> str:
        """
        Получить ссылку на магазин Tribute

        ВАЖНО: Используем базовую ссылку без изменений,
        так как Tribute не поддерживает передачу metadata через URL
        """
        return self.shop_url

SUBSCRIPTION_PACKAGES = [
    {
        'id': 'year',
        'name': 'Год',
        'coins': 1200,
        'days': 365,
        'price': 20,
        'currency': '€',
        'description': '1200 монет на 365 дней'
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
        'id': '3months',
        'name': '3 месяца',
        'coins': 300,
        'days': 90,
        'price': 5,
        'currency': '€',
        'description': '300 монет на 90 дней'
    },
    {
        'id': '1month',
        'name': '1 месяц',
        'coins': 100,
        'days': 30,
        'price': 2,
        'currency': '€',
        'description': '100 монет на 30 дней'
    }
]

tribute = TributePayment()

async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available subscription packages"""
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
    """Handle subscription package selection"""
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

    order_id = str(uuid.uuid4())
    
    async with db_manager.SessionLocal() as session:
        payment = Payment(
            user_id=db_user.id,
            telegram_id=user.id,
            payment_id=order_id,
            amount=package['price'],
            currency=package['currency'],
            status='pending',
            package_id=package['id'],
            coins=package['coins'],
            days=package.get('days', 0)
        )
        session.add(payment)
        await session.commit()

    payment_url = tribute.get_payment_link(user.id, package['id'])

    logger.info(f"💳 User {user.id} (@{user.username or 'no_username'}) started payment")
    logger.info(f"📦 Package: {package['name']} - {package['price']} {package['currency']}")
    logger.info(f"🔗 Payment URL: {payment_url}")
    logger.info(f"👤 User info: {user.first_name} (ID: {user.id}, Email: {db_user.email})")

    keyboard = [
        [InlineKeyboardButton(
            "💳 Открыть магазин Tribute",
            url=payment_url  # Обычный url для telegram-ссылок
        )],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    keyboard = [
        [InlineKeyboardButton(
            "💳 Открыть магазин Tribute",
            url=payment_url
        )],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""💳 **Оплата через Tribute**

📦 Пакет: **{package['name']}**
💰 Монет: {package['coins']}
📅 Период: {package['days']} дней
💵 К оплате: **{package['price']} {package['currency']}**

**Инструкция:**

1️⃣ Нажмите кнопку "💳 Открыть магазин Tribute"
2️⃣ Выберите период: **{package['name']}** ({package['price']} {package['currency']})
3️⃣ Выберите способ оплаты
4️⃣ Подтвердите платёж

⚡️ Монеты зачислятся автоматически после оплаты!

💡 После оплаты проверьте баланс: /balance
"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


def register_payment_handlers(application):
    """Register handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_package_"))