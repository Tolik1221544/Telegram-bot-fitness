from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, \
    CommandHandler
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

# Conversation states
AWAITING_PROMO = 1


class TributePayment:
    """Tribute.tg payment integration - ИСПРАВЛЕННАЯ ВЕРСИЯ"""

    def __init__(self):
        self.api_key = config.TRIBUTE_API_KEY
        self.webhook_secret = config.TRIBUTE_WEBHOOK_SECRET

        # ✅ ПРАВИЛЬНЫЙ URL согласно документации Tribute.tg
        self.base_url = "https://api.tribute.tg"

    async def create_payment(self, amount: float, order_id: str, description: str,
                             success_url: Optional[str] = None,
                             telegram_id: Optional[int] = None) -> dict:
        """Create payment via Tribute API

        Документация: https://tribute.tg/docs
        """

        # ✅ Tribute принимает рубли (не копейки!)
        payload = {
            "amount": amount,  # В рублях (299, 499 и т.д.)
            "description": description,
            "order_id": order_id,
            "return_url": success_url or f"https://t.me/{config.BOT_USERNAME.replace('@', '')}",
            "metadata": {
                "telegram_id": str(telegram_id) if telegram_id else None,
                "source": "telegram_bot"
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                # ✅ Правильный endpoint
                async with session.post(
                        f"{self.base_url}/payments",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_text = await response.text()

                    if response.status == 200 or response.status == 201:
                        data = await response.json()
                        return {
                            "success": True,
                            "payment_url": data.get("payment_url") or data.get("url"),
                            "payment_id": data.get("id") or data.get("payment_id")
                        }
                    else:
                        logger.error(f"Tribute payment creation failed: {response.status} - {response_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {response_text}"
                        }
        except asyncio.TimeoutError:
            logger.error("Tribute API timeout")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            logger.error(f"Tribute API error: {e}")
            return {"success": False, "error": str(e)}

    async def check_payment_status(self, payment_id: str) -> dict:
        """Check payment status via Tribute API"""

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                # ✅ Правильный endpoint для проверки статуса
                async with session.get(
                        f"{self.base_url}/payments/{payment_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "status": data.get("status"),  # succeeded, pending, failed
                            "amount": data.get("amount"),
                            "order_id": data.get("order_id")
                        }
                    else:
                        return {
                            "success": False,
                            "status": "unknown"
                        }
        except Exception as e:
            logger.error(f"Error checking Tribute payment: {e}")
            return {"success": False, "status": "unknown"}

    def verify_webhook(self, signature: str, payload: str) -> bool:
        """Verify Tribute webhook signature"""
        expected_signature = hashlib.sha256(
            f"{payload}{self.webhook_secret}".encode()
        ).hexdigest()
        return signature == expected_signature

SUBSCRIPTION_PACKAGES = [
    {
        'id': 'week_50',
        'name': '📅 Неделя (50 монет)',
        'coins': 50,
        'days': 7,
        'price': 99,  # ✅ В рублях, не в копейках
        'description': '50 монет на 7 дней'
    },
    {
        'id': 'two_weeks_100',
        'name': '📆 2 недели (100 монет)',
        'coins': 100,
        'days': 14,
        'price': 199,
        'description': '100 монет на 14 дней'
    },
    {
        'id': 'month_200',
        'name': '📆 Месяц (200 монет)',
        'coins': 200,
        'days': 30,
        'price': 299,
        'description': '200 монет на 30 дней'
    },
    {
        'id': 'month_500',
        'name': '💎 Премиум (500 монет)',
        'coins': 500,
        'days': 30,
        'price': 499,
        'description': '500 монет на 30 дней'
    }
]

def validate_tribute_config():
    """Проверка настроек Tribute перед запуском"""
    if not config.TRIBUTE_API_KEY:
        logger.error("❌ TRIBUTE_API_KEY не настроен в .env!")
        logger.error("Получите ключ на https://tribute.tg/merchants")
        return False

    if not config.TRIBUTE_WEBHOOK_SECRET:
        logger.warning("⚠️ TRIBUTE_WEBHOOK_SECRET не настроен!")
        logger.warning("Webhook подтверждения не будут работать")

    logger.info(f"✅ Tribute API Key: {config.TRIBUTE_API_KEY[:10]}...")
    return True

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

    text = """💳 **Покупка монет и подписок**

✅ Оплата через Tribute - безопасно и удобно
✅ Работает с российскими картами  
✅ Моментальное зачисление
✅ Автоматическое продление (опционально)

🎁 При первой покупке +10% монет бонусом!

Выберите подходящий пакет:"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_direct_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show direct coin purchase options"""
    query = update.callback_query
    await query.answer()

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
        discount = " 🔥 Выгодно!" if pack["coins"] >= 200 else ""
        button_text = f"💰 {pack['coins']} монет - {pack['price']} ₽{discount}"
        callback_data = f"buy_coins_{pack['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """💰 **Прямая покупка монет**

Купите монеты без подписки!
Монеты не истекают и остаются навсегда.

🎯 Чем больше пакет - тем выгоднее цена!"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription package selection"""
    query = update.callback_query
    user = query.from_user

    callback_data = query.data

    # Determine package type
    if callback_data.startswith("buy_package_"):
        package_id = callback_data.replace("buy_package_", "")
        package_type = "subscription"

        package = None
        for p in config.SUBSCRIPTION_PACKAGES:
            if p['id'] == package_id:
                package = p
                break

    elif callback_data.startswith("buy_coins_"):
        coins_id = callback_data.replace("buy_coins_", "")
        package_type = "direct"

        coins_amount = int(coins_id.replace("coins_", ""))
        prices = {10: 49, 50: 199, 100: 349, 200: 599, 500: 1299, 1000: 2299}

        if coins_amount in prices:
            package = {
                'id': coins_id,
                'name': f'{coins_amount} монет',
                'coins': coins_amount,
                'price': prices[coins_amount],
                'days': 0,
                'description': f'Покупка {coins_amount} монет'
            }
        else:
            await query.answer("❌ Пакет не найден", show_alert=True)
            return
    else:
        await query.answer("❌ Неверный формат", show_alert=True)
        return

    if not package:
        await query.answer("❌ Пакет не найден", show_alert=True)
        return

    await query.answer()

    # Get or create user
    db_user = await db_manager.get_user(user.id)
    if not db_user:
        await query.message.reply_text("❌ Сначала используйте /start")
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

    # Save payment to database (pending)
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
        error_msg = payment_result.get('error', 'Unknown error')
        logger.error(f"Payment creation failed: {error_msg}")
        await query.message.reply_text(
            f"❌ Ошибка создания платежа: {error_msg}\n\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        return

    # Update payment with Tribute payment ID
    async with db_manager.SessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Payment).where(Payment.payment_id == order_id)
        )
        payment = result.scalar_one_or_none()
        if payment:
            payment.payment_id = payment_result['payment_id']
            session.add(payment)
            await session.commit()

    # Create payment message
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить в Tribute", url=payment_result['payment_url'])],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    emoji = "📅" if package_type == "subscription" else "💰"
    period_text = f"📅 Период: {package['days']} дней\n" if package.get('days', 0) > 0 else ""

    text = f"""💳 **Оплата через Tribute**

{emoji} Пакет: {package['name']}
💰 Монет: {package['coins']}
{period_text}💵 К оплате: {package['price']} ₽

➡️ Нажмите "Оплатить в Tribute"
➡️ После оплаты нажмите "Проверить оплату"

🆔 ID заказа: `{order_id[:8]}`

⚡ Платеж через Tribute - безопасно!"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # Store payment info
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

    order_id = query.data.replace("check_payment_", "")

    # Get payment info
    payment_info = context.user_data.get(f'payment_{order_id}')
    if not payment_info:
        # Try database
        from sqlalchemy import select
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

    # Check status with Tribute
    status_result = await tribute.check_payment_status(payment_info['tribute_id'])

    if not status_result['success']:
        await query.answer("⏳ Проверяем...", show_alert=True)
        return

    status = status_result.get('status', 'unknown')

    if status == 'pending':
        await query.answer("⏳ Платеж обрабатывается. Попробуйте через минуту.", show_alert=True)
        return

    if status == 'failed':
        await query.answer("❌ Платеж отклонен", show_alert=True)

        from sqlalchemy import select
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

    if status in ['paid', 'success']:
        await query.answer("✅ Платеж успешен!", show_alert=True)

        from sqlalchemy import select
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
                        # Subscription
                        await api_client.purchase_subscription(
                            token=db_user.api_token,
                            coins=payment.coins,
                            days=payment.days,
                            price=float(payment.amount)
                        )
                    else:
                        # Direct purchase
                        current_balance = await api_client.get_balance(db_user.api_token)
                        new_balance = current_balance['balance'] + payment.coins

                        await api_client.set_balance(
                            token=db_user.api_token,
                            amount=new_balance,
                            source='purchase'
                        )

                    # Track referral purchase
                    if db_user.referred_by:
                        from bot.utils.tracking import track_purchase
                        await track_purchase(db_user.referred_by, float(payment.amount))

                    # Success message
                    success_text = f"""✅ **Платеж успешно обработан!**

💰 Начислено: {payment.coins} монет
"""
                    if payment.days > 0:
                        success_text += f"📅 Действуют: {payment.days} дней\n"
                    else:
                        success_text += "♾️ Монеты постоянные\n"

                    success_text += f"""💵 Оплачено: {payment.amount} ₽

Спасибо за покупку! 🎉
/balance - проверить баланс"""

                    await query.message.reply_text(success_text, parse_mode='Markdown')

                    # Cleanup
                    if f'payment_{order_id}' in context.user_data:
                        del context.user_data[f'payment_{order_id}']

                except Exception as e:
                    logger.error(f"Error activating coins: {e}")
                    await query.message.reply_text(
                        "⚠️ Платеж получен, но ошибка начисления.\n"
                        f"Обратитесь в поддержку: {order_id[:8]}"
                    )


async def start_promo_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start promo code entry"""
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🎁 **Введите промокод**\n\n"
        "Отправьте промокод в следующем сообщении:",
        parse_mode='Markdown'
    )

    return AWAITING_PROMO


async def process_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process promo code"""
    promo_code = update.message.text.strip().upper()

    # Test promo codes
    promo_codes = {
        'WELCOME50': {'coins': 50, 'message': 'Добро пожаловать! +50 монет'},
        'FITNESS100': {'coins': 100, 'message': 'Фитнес бонус! +100 монет'},
        'NEWYEAR2024': {'coins': 200, 'message': 'Новогодний подарок! +200 монет'}
    }

    if promo_code in promo_codes:
        promo = promo_codes[promo_code]

        user = update.effective_user
        db_user = await db_manager.get_user(user.id)

        if db_user and db_user.api_token:
            try:
                balance = await api_client.get_balance(db_user.api_token)
                new_balance = balance['balance'] + promo['coins']

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
                logger.error(f"Promo activation error: {e}")
                await update.message.reply_text("❌ Ошибка активации")
        else:
            await update.message.reply_text("❌ Сначала свяжите аккаунт")
    else:
        await update.message.reply_text("❌ Промокод недействителен")

    return ConversationHandler.END


async def cancel_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel promo entry"""
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END


def register_payment_handlers(application):
    """Register payment handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(show_direct_coins, pattern="^direct_coins$"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_package_"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_coins_"))
    application.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment_"))

    promo_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_promo_entry, pattern="^enter_promo$")],
        states={
            AWAITING_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_promo_code)]
        },
        fallbacks=[CommandHandler("cancel", cancel_promo)]
    )

    application.add_handler(promo_handler)