from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.database import db_manager, Payment
from bot.api_client import api_client
from bot.config import config
import logging
import uuid
import aiohttp
import hashlib
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TributePayment:
    """Tribute.tg payment integration"""

    def __init__(self):
        self.api_key = config.TRIBUTE_API_KEY
        self.webhook_secret = config.TRIBUTE_WEBHOOK_SECRET
        self.base_url = "https://api.tribute.tg/v1"

    async def create_payment(self, amount: float, order_id: str, description: str,
                             success_url: Optional[str] = None,
                             telegram_id: Optional[int] = None) -> dict:
        """Create payment via Tribute API"""

        payload = {
            "amount": amount,
            "order_id": order_id,
            "description": description,
            "currency": "RUB",
            "success_url": success_url or f"https://t.me/{config.BOT_USERNAME.replace('@', '')}",
            "payment_metadata": {
                "telegram_id": str(telegram_id) if telegram_id else None
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    f"{self.base_url}/payments/create",
                    json=payload,
                    headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "payment_url": data.get("payment_url"),
                        "payment_id": data.get("payment_id")
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Tribute payment creation failed: {error_text}")
                    return {
                        "success": False,
                        "error": error_text
                    }

    async def check_payment_status(self, payment_id: str) -> dict:
        """Check payment status via Tribute API"""

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{self.base_url}/payments/{payment_id}/status",
                    headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "status": data.get("status"),  # pending, success, failed
                        "amount": data.get("amount"),
                        "order_id": data.get("order_id")
                    }
                else:
                    return {
                        "success": False,
                        "status": "unknown"
                    }

    def verify_webhook(self, signature: str, payload: str) -> bool:
        """Verify Tribute webhook signature"""
        expected_signature = hashlib.sha256(
            f"{payload}{self.webhook_secret}".encode()
        ).hexdigest()

        return signature == expected_signature


tribute = TributePayment()


async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available subscription packages"""
    query = update.callback_query
    await query.answer()

    keyboard = []

    # Subscription packages
    for package in config.SUBSCRIPTION_PACKAGES:
        button_text = f"{package['name']} - {package['price']} ₽"
        callback_data = f"buy_package_{package['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Additional options
    keyboard.append([
        InlineKeyboardButton("💎 Прямая покупка монет", callback_data="direct_coins")
    ])
    keyboard.append([
        InlineKeyboardButton("🎁 Ввести промокод", callback_data="enter_promo")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """
💳 **Покупка монет и подписок**

✅ Оплата через Tribute - безопасно и удобно
✅ Работает с российскими картами
✅ Моментальное зачисление
✅ Автоматическое продление (опционально)

🎁 При первой покупке +10% монет бонусом!

Выберите подходящий пакет:
    """

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_direct_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show direct coin purchase options"""
    query = update.callback_query
    await query.answer()

    # Direct coin packages
    coin_packages = [
        {"coins": 10, "price": 49, "id": "coins_10"},
        {"coins": 50, "price": 199, "id": "coins_50"},
        {"coins": 100, "price": 349, "id": "coins_100"},
        {"coins": 200, "price": 599, "id": "coins_200"},
        {"coins": 500, "price": 1299, "id": "coins_500"},
        {"coins": 1000, "price": 2299, "id": "coins_1000"}
    ]

    keyboard = []
    for pack in coin_packages:
        discount = ""
        if pack["coins"] >= 200:
            discount = " 🔥 Выгодно!"
        button_text = f"💰 {pack['coins']} монет - {pack['price']} ₽{discount}"
        callback_data = f"buy_coins_{pack['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """
💰 **Прямая покупка монет**

Купите монеты без подписки!
Монеты не истекают и остаются навсегда.

🎯 Чем больше пакет - тем выгоднее цена!
    """

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription package selection"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data
    callback_data = query.data

    # Determine if it's subscription or direct coins
    if callback_data.startswith("buy_package_"):
        package_id = callback_data.replace("buy_package_", "")
        package_type = "subscription"

        # Find package
        package = None
        for p in config.SUBSCRIPTION_PACKAGES:
            if p['id'] == package_id:
                package = p
                break

    elif callback_data.startswith("buy_coins_"):
        coins_id = callback_data.replace("buy_coins_", "")
        package_type = "direct"

        # Parse coins package
        coins_amount = int(coins_id.replace("coins_", ""))
        prices = {10: 49, 50: 199, 100: 349, 200: 599, 500: 1299, 1000: 2299}

        if coins_amount in prices:
            package = {
                'id': coins_id,
                'name': f'{coins_amount} монет',
                'coins': coins_amount,
                'price': prices[coins_amount],
                'days': 0,  # Permanent coins
                'description': f'Покупка {coins_amount} монет'
            }
        else:
            await query.answer("❌ Пакет не найден", show_alert=True)
            return

    if not package:
        await query.answer("❌ Пакет не найден", show_alert=True)
        return

    await query.answer()

    # Get or create user
    db_user = await db_manager.get_user(user.id)
    if not db_user:
        await query.message.reply_text(
            "❌ Сначала нужно зарегистрироваться. Используйте /start"
        )
        return

    # Check if user has linked account
    if not db_user.api_token:
        keyboard = [[InlineKeyboardButton("🔗 Связать аккаунт", callback_data="link_account")]]
        await query.message.reply_text(
            "❌ Сначала свяжите аккаунт с приложением",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Create unique order ID
    order_id = str(uuid.uuid4())

    # Save payment to database (pending status)
    async with db_manager.SessionLocal() as session:
        payment = Payment(
            user_id=db_user.id,
            telegram_id=user.id,
            payment_id=order_id,
            amount=package['price'],
            currency='RUB',
            status='pending',
            package_id=package['id'],
            coins=package['coins'],
            days=package.get('days', 0),
            payment_metadata=f'{{"type": "{package_type}"}}'
        )
        session.add(payment)
        await session.commit()

    # Create payment via Tribute
    payment_result = await tribute.create_payment(
        amount=package['price'],
        order_id=order_id,
        description=package['description'],
        telegram_id=user.id
    )

    if not payment_result['success']:
        await query.message.reply_text(
            "❌ Ошибка создания платежа. Попробуйте позже."
        )
        return

    # Update payment with Tribute payment ID
    async with db_manager.SessionLocal() as session:
        payment.payment_id = payment_result['payment_id']
        session.add(payment)
        await session.commit()

    # Create payment message with button
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить в Tribute", url=payment_result['payment_url'])],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    emoji = "📅" if package_type == "subscription" else "💰"
    period_text = f"📅 Период: {package['days']} дней\n" if package.get('days', 0) > 0 else ""

    text = f"""
💳 **Оплата через Tribute**

{emoji} Пакет: {package['name']}
💰 Монет: {package['coins']}
{period_text}💵 К оплате: {package['price']} ₽

➡️ Нажмите "Оплатить в Tribute" для перехода к оплате
➡️ После оплаты нажмите "Проверить оплату"

🆔 ID заказа: `{order_id[:8]}`

⚡ Платеж через Tribute - безопасно и быстро!
    """

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # Store payment info in context for later checking
    context.user_data[f'payment_{order_id}'] = {
        'tribute_id': payment_result['payment_id'],
        'amount': package['price'],
        'coins': package['coins'],
        'days': package.get('days', 0)
    }


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check payment status"""
    query = update.callback_query
    user = query.from_user

    # Parse order ID
    order_id = query.data.replace("check_payment_", "")

    # Get payment info from context
    payment_info = context.user_data.get(f'payment_{order_id}')
    if not payment_info:
        # Try to get from database
        async with db_manager.SessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.payment_id == order_id)
            )
            payment = result.scalar_one_or_none()

            if not payment:
                await query.answer("❌ Платеж не найден", show_alert=True)
                return

            payment_info = {
                'tribute_id': payment.payment_id,
                'amount': payment.amount,
                'coins': payment.coins,
                'days': payment.days
            }

    # Check payment status with Tribute
    status_result = await tribute.check_payment_status(payment_info['tribute_id'])

    if not status_result['success']:
        await query.answer("⏳ Проверяем статус платежа...", show_alert=True)
        return

    if status_result['status'] == 'pending':
        await query.answer("⏳ Платеж еще обрабатывается. Попробуйте через минуту.", show_alert=True)
        return

    if status_result['status'] == 'failed':
        await query.answer("❌ Платеж отклонен", show_alert=True)

        # Update payment status
        async with db_manager.SessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.payment_id == order_id)
            )
            payment = result.scalar_one_or_none()
            if payment:
                payment.status = 'failed'
                session.add(payment)
                await session.commit()

        return

    if status_result['status'] == 'success':
        # Payment successful
        await query.answer("✅ Платеж успешен!", show_alert=True)

        # Update payment in database
        async with db_manager.SessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.payment_id == order_id)
            )
            payment = result.scalar_one_or_none()

            if payment and payment.status != 'completed':
                payment.status = 'completed'
                payment.completed_at = datetime.utcnow()
                session.add(payment)
                await session.commit()

                # Get user
                db_user = await db_manager.get_user(user.id)

                # Add coins via API
                try:
                    if payment.days > 0:
                        # Subscription with expiry
                        result = await api_client.purchase_subscription(
                            token=db_user.api_token,
                            coins=payment.coins,
                            days=payment.days,
                            price=float(payment.amount)
                        )
                    else:
                        # Direct coin purchase (permanent)
                        current_balance = await api_client.get_balance(db_user.api_token)
                        new_balance = current_balance['balance'] + payment.coins

                        result = await api_client.set_balance(
                            token=db_user.api_token,
                            amount=new_balance,
                            source='purchase'
                        )

                    # Track purchase for referral
                    if db_user.referred_by:
                        from bot.utils.tracking import track_purchase
                        await track_purchase(db_user.referred_by, float(payment.amount))

                    # Send success message
                    success_text = f"""
✅ **Платеж успешно обработан!**

💰 Начислено: {payment.coins} монет
"""
                    if payment.days > 0:
                        success_text += f"📅 Действуют: {payment.days} дней\n"
                    else:
                        success_text += "♾️ Монеты постоянные (не истекают)\n"

                    success_text += f"""
💵 Оплачено: {payment.amount} ₽

Спасибо за покупку! 🎉
Используйте /balance для проверки баланса.
"""

                    await query.message.reply_text(success_text, parse_mode='Markdown')

                    # Clean up context
                    if f'payment_{order_id}' in context.user_data:
                        del context.user_data[f'payment_{order_id}']

                except Exception as e:
                    logger.error(f"Error activating coins: {e}")
                    await query.message.reply_text(
                        "⚠️ Платеж получен, но произошла ошибка при начислении монет.\n"
                        "Обратитесь в поддержку с ID заказа: " + order_id[:8]
                    )


async def handle_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle promo code entry"""
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🎁 **Введите промокод**\n\n"
        "Отправьте промокод в следующем сообщении:",
        parse_mode='Markdown'
    )

    context.user_data['awaiting_promo'] = True


async def process_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process entered promo code"""
    if not context.user_data.get('awaiting_promo'):
        return

    promo_code = update.message.text.strip().upper()
    context.user_data['awaiting_promo'] = False

    # Check promo code (you can implement your logic here)
    # For demo, we'll have a few test codes
    promo_codes = {
        'WELCOME50': {'coins': 50, 'message': 'Добро пожаловать! +50 монет'},
        'FITNESS100': {'coins': 100, 'message': 'Фитнес бонус! +100 монет'},
        'NEWYEAR2024': {'coins': 200, 'message': 'Новогодний подарок! +200 монет'}
    }

    if promo_code in promo_codes:
        promo = promo_codes[promo_code]

        # Add coins to user
        user = update.effective_user
        db_user = await db_manager.get_user(user.id)

        if db_user and db_user.api_token:
            try:
                # Get current balance
                balance = await api_client.get_balance(db_user.api_token)
                new_balance = balance['balance'] + promo['coins']

                # Set new balance
                await api_client.set_balance(
                    token=db_user.api_token,
                    amount=new_balance,
                    source='promo'
                )

                await update.message.reply_text(
                    f"✅ **Промокод активирован!**\n\n"
                    f"🎁 {promo['message']}\n"
                    f"💰 Новый баланс: {new_balance} монет",
                    parse_mode='Markdown'
                )
            except Exception as e:
                await update.message.reply_text("❌ Ошибка активации промокода")
        else:
            await update.message.reply_text("❌ Сначала свяжите аккаунт")
    else:
        await update.message.reply_text(
            "❌ Промокод недействителен или уже использован"
        )


# Webhook handler for Tribute callbacks
async def handle_tribute_webhook(request):
    """Handle Tribute payment webhooks"""
    try:
        # Get signature from headers
        signature = request.headers.get('X-Tribute-Signature')

        # Get raw body
        body = await request.text()

        # Verify signature
        if not tribute.verify_webhook(signature, body):
            logger.warning("Invalid Tribute webhook signature")
            return {'status': 'error', 'message': 'Invalid signature'}

        # Parse webhook data
        data = await request.json()

        order_id = data.get('order_id')
        status = data.get('status')
        amount = data.get('amount')

        # Update payment in database
        async with db_manager.SessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.payment_id == order_id)
            )
            payment = result.scalar_one_or_none()

            if payment:
                if status == 'success' and payment.status != 'completed':
                    payment.status = 'completed'
                    payment.completed_at = datetime.utcnow()

                    # TODO: Notify user via bot about successful payment
                    # You'll need to implement a way to send messages to users

                elif status == 'failed':
                    payment.status = 'failed'

                session.add(payment)
                await session.commit()

        return {'status': 'ok'}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {'status': 'error', 'message': str(e)}


# Register payment handlers
def register_payment_handlers(application):
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(show_direct_coins, pattern="^direct_coins$"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_package_"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_coins_"))
    application.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment_"))
    application.add_handler(CallbackQueryHandler(handle_promo_code, pattern="^enter_promo$"))