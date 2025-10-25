import logging
import json
from datetime import datetime
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
    """Показать меню подписок"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await db_manager.get_user(user.id)

    if not db_user or not db_user.api_token:
        keyboard = [
            [InlineKeyboardButton("🔗 Сначала свяжите аккаунт", callback_data="link_account")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]
        await query.message.edit_text(
            "❌ Для покупки подписки сначала нужно связать аккаунт с приложением.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = """💳 *LightWeight PAY*

Здесь вы можете купить LW coins со скидкой, оплатить картой любой страны и любым удобным способом\\.

📋 *Доступные тарифы:*

• *1 месяц — 2 €*
   → _100 монет на 30 дней_
• *3 месяца — 5 €*
   → _300 монет на 90 дней_
• *6 месяцев — 10 €*
   → _600 монет на 180 дней_
• *Год — 20 €*
   → _1200 монет на 365 дней_

*💡 Как купить:*
1️⃣ Нажмите кнопку "💳 Открыть магазин Tribute"
2️⃣ Выберите нужный период подписки
3️⃣ Добавьте удобный для вас способ оплаты и оплатите

⚡️ Монеты зачислятся автоматически в течение 2 минут\\!"""

    keyboard = [
        [InlineKeyboardButton("💳 Открыть магазин Tribute", url=TRIBUTE_STORE_LINK)],
        [InlineKeyboardButton("🔄 Проверить статус платежа", callback_data="check_payment")],
        [InlineKeyboardButton("🔙 Назад", callback_data="start")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить статус платежа"""
    query = update.callback_query
    await query.answer("⏳ Проверяю статус...", show_alert=False)

    user = query.from_user

    try:
        status = await api_client.check_payment_status(user.id)

        logger.info(f"Payment status response: {status}")

        if not status.get('success'):
            await show_error(query, "Ошибка проверки статуса")
            return

        last_payment = status.get('lastPayment', {})
        payment_status = last_payment.get('status', status.get('status'))

        metadata = None
        if last_payment.get('metadata'):
            try:
                metadata = json.loads(last_payment['metadata'])
            except:
                pass

        if metadata:
            operation_type = metadata.get('Type', '')

            if 'tariff_upgrade' in operation_type:
                await show_tariff_upgrade(query, metadata, last_payment)
                return
            elif 'tariff_downgrade' in operation_type:
                await show_tariff_downgrade(query, metadata, last_payment)
                return

        if payment_status == 'completed':
            await show_completed_payment(query, last_payment)

        elif payment_status == 'pending':
            await show_pending_payment(query, last_payment)

        elif payment_status == 'expired':
            await show_expired_payment(query)

        elif payment_status == 'duplicate':
            await show_duplicate_payment(query)

        elif not status.get('hasPayments'):
            await show_no_payments(query)

        else:
            await show_unknown_status(query, payment_status)

    except Exception as e:
        logger.error(f"Error checking payment: {e}")
        await show_error(query, "Произошла ошибка при проверке")


async def show_completed_payment(query, payment):
    """Показать успешный платёж"""
    amount = payment.get('amount', 0)
    coins = payment.get('coinsAmount', 0)
    package_name = payment.get('packageName', 'Подписка')
    currency = payment.get('currency', 'EUR').upper()

    if amount > 100:
        amount = amount / 100

    if package_name == 'Подписка' or not package_name:
        for pkg in SUBSCRIPTION_PACKAGES:
            if pkg['price'] == amount:
                package_name = pkg['name']
                break

    text = f"""✅ *Платёж успешно обработан\\!*

📦 *Пакет:* {package_name}
💰 *Начислено монет:* `{coins}`
💵 *Сумма:* `{amount:.2f} {currency}`

Спасибо за покупку\\! 🎉

_Монеты уже доступны в приложении\\._"""

    keyboard = [
        [InlineKeyboardButton("🔙 В главное меню", callback_data="start")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_pending_payment(query, payment):
    """Показать ожидающий платёж"""
    amount = payment.get('amount', 0)
    coins = payment.get('coinsAmount', 0)

    text = f"""⏳ *Платёж обрабатывается*

💰 *Ожидаемые монеты:* `{coins}`
💵 *Сумма:* `{amount}` EUR

_Платёж будет обработан автоматически в течение 2 минут\\._
Нажмите кнопку ниже для повторной проверки\\."""

    keyboard = [
        [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_payment")],
        [InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_tariff_upgrade(query, metadata, payment):
    """Показать апгрейд тарифа"""
    old_package = metadata.get('OldPackage', 'Старый')
    new_package = metadata.get('NewPackage', 'Новый')
    coins_added = metadata.get('CoinsAdded', 0)
    coins_diff = metadata.get('CoinsDifference', 0)

    text = f"""⬆️ *Тариф успешно повышен\\!*

📦 *Было:* {old_package}
📦 *Стало:* {new_package}

💰 *Добавлено монет:* `\\+{coins_added}`
📊 *Общая разница:* `{coins_diff}` монет

Спасибо за апгрейд\\! 🎉"""

    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="start")]]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_tariff_downgrade(query, metadata, payment):
    """Показать даунгрейд тарифа"""
    old_package = metadata.get('OldPackage', 'Старый')
    new_package = metadata.get('NewPackage', 'Новый')

    text = f"""⬇️ *Тариф изменён*

📦 *Было:* {old_package}
📦 *Стало:* {new_package}

ℹ️ *Важно:* Ваши текущие монеты сохранены\\!
_Следующее продление будет по новому тарифу\\._"""

    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="start")]]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_expired_payment(query):
    """Показать истёкший платёж"""
    text = """⏰ *Платёж истёк*

_Прошло более 24 часов с момента создания платежа\\._
Создайте новый заказ в магазине Tribute\\."""

    keyboard = [
        [InlineKeyboardButton("💳 Открыть магазин", url=TRIBUTE_STORE_LINK)],
        [InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_duplicate_payment(query):
    """Показать дубликат платежа"""
    text = """⚠️ *Этот платёж уже обработан*

_Монеты уже были начислены на ваш счёт\\._
Проверьте баланс в приложении\\."""

    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="start")]]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_no_payments(query):
    """Показать отсутствие платежей"""
    text = """ℹ️ *У вас пока нет платежей*

Хотите приобрести подписку?
Нажмите кнопку ниже для перехода в магазин\\."""

    keyboard = [
        [InlineKeyboardButton("💳 Купить подписку", url=TRIBUTE_STORE_LINK)],
        [InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_unknown_status(query, status):
    """Показать неизвестный статус"""
    text = f"""❓ *Неизвестный статус платежа*

_Статус:_ `{status}`

Попробуйте проверить позже или обратитесь в поддержку\\."""

    keyboard = [
        [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_payment")],
        [InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")]
    ]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def show_error(query, message):
    """Показать ошибку"""
    text = f"""❌ *{message}*

Попробуйте позже или обратитесь в поддержку\\."""

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")]]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )

def register_payment_handlers(application):
    """Регистрация обработчиков платежей"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern="^check_payment$"))