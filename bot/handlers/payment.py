import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

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

    text = """💳 **LightWeight PAY**

Здесь вы можете купить LW coins со скидкой, оплатить картой любой страны и любым удобным способом.

**📋 Доступные тарифы:**

- **1 месяц** — 2 € → 100 монет на 30 дней
- **3 месяца** — 5 € → 300 монет на 90 дней
- **6 месяцев** — 10 € → 600 монет на 180 дней
- **Год** — 20 € → 1200 монет на 365 дней

**Как купить:**
1️⃣ Нажмите кнопку "💳 Открыть магазин Tribute"
2️⃣ Выберите нужный период подписки
3️⃣ Выберите способ оплаты
4️⃣ Подтвердите платёж

⚡️ Монеты зачислятся **автоматически** в течение 2 минут после оплаты!

✅ Безопасно и удобно
✅ Поддержка карт любых стран
✅ Автоматическое начисление монет"""

    logger.info(f"💳 User {user.id} ({db_user.email}) opening Tribute store")

    keyboard = [
        [InlineKeyboardButton("💳 Открыть магазин Tribute", url=TRIBUTE_STORE_LINK)],
        [InlineKeyboardButton("🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


def register_payment_handlers(application):
    """Регистрация handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))