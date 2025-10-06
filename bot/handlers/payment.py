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
import asyncio

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_PROMO = 1


class TributePayment:
    """Tribute.tg payment integration"""

    def __init__(self):
        self.api_key = config.TRIBUTE_API_KEY
        self.webhook_secret = config.TRIBUTE_WEBHOOK_SECRET
        # ИСПРАВЛЕНО: используем правильный базовый URL
        self.base_url = "https://tribute.tg/api"

    async def create_payment(self, amount: float, order_id: str, description: str,
                             success_url: Optional[str] = None,
                             telegram_id: Optional[int] = None) -> dict:
        """Create payment via Tribute API"""

        if not self.api_key:
            logger.error("❌ TRIBUTE_API_KEY not configured!")
            return {
                "success": False,
                "error": "API key not configured"
            }

        # ИСПРАВЛЕНО: Согласно документации Tribute, используем GET запрос
        params = {
            "api_key": self.api_key,
            "name": description,
            "amount": int(amount),  # Сумма в рублях
            "order_id": order_id,
        }

        if telegram_id:
            params["telegram_id"] = telegram_id

        logger.info(f"📤 Sending request to Tribute API:")
        logger.info(f"   URL: {self.base_url}/create")
        logger.info(f"   Params: {params}")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # ИСПРАВЛЕНО: GET запрос вместо POST
                async with session.get(
                        f"{self.base_url}/create",
                        params=params
                ) as response:
                    response_text = await response.text()

                    logger.info(f"📥 Tribute API Response:")
                    logger.info(f"   Status: {response.status}")
                    logger.info(f"   Body: {response_text}")

                    if response.status in [200, 201]:
                        try:
                            data = await response.json()
                        except:
                            # Если ответ не JSON, возможно это просто URL
                            if response_text.startswith('http'):
                                return {
                                    "success": True,
                                    "payment_url": response_text.strip(),
                                    "payment_id": order_id
                                }
                            else:
                                logger.error(f"❌ Failed to parse response: {response_text}")
                                return {
                                    "success": False,
                                    "error": "Invalid response format"
                                }

                        # Получаем URL для оплаты из ответа
                        payment_url = data.get("payment_url") or data.get("url") or data.get("link")
                        payment_id = data.get("id") or data.get("payment_id") or order_id

                        if not payment_url:
                            logger.error(f"❌ No payment URL in response: {data}")
                            return {
                                "success": False,
                                "error": "No payment URL returned"
                            }

                        logger.info(f"✅ Payment created successfully:")
                        logger.info(f"   Payment ID: {payment_id}")
                        logger.info(f"   Payment URL: {payment_url}")

                        return {
                            "success": True,
                            "payment_url": payment_url,
                            "payment_id": payment_id
                        }

                    elif response.status == 401:
                        logger.error(f"❌ Unauthorized (401) - неверный API ключ")
                        return {
                            "success": False,
                            "error": "Неверный API ключ"
                        }

                    elif response.status == 403:
                        logger.error(f"❌ Forbidden (403) - доступ запрещен")
                        return {
                            "success": False,
                            "error": "Доступ запрещен"
                        }

                    else:
                        logger.error(f"❌ Tribute API error: {response.status}")
                        logger.error(f"   Response: {response_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {response_text[:100]}"
                        }

        except asyncio.TimeoutError:
            logger.error("❌ Tribute API timeout")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            logger.error(f"❌ Tribute API error: {type(e).__name__}: {e}")
            logger.exception("Full traceback:")
            return {"success": False, "error": f"Error: {str(e)}"}

    async def check_payment_status(self, payment_id: str) -> dict:
        """Check payment status via Tribute API"""

        if not self.api_key:
            return {"success": False, "status": "unknown", "error": "API key not configured"}

        params = {
            "api_key": self.api_key,
            "order_id": payment_id
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        f"{self.base_url}/status",
                        params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        status = data.get("status", "pending")
                        is_paid = data.get("paid", False) or status in ["paid", "completed", "success"]

                        if is_paid:
                            return {
                                "success": True,
                                "status": "paid",
                                "amount": data.get("amount"),
                                "order_id": payment_id
                            }
                        else:
                            return {
                                "success": True,
                                "status": "pending",
                                "amount": data.get("amount"),
                                "order_id": payment_id
                            }
                    else:
                        response_text = await response.text()
                        logger.error(f"Check status failed: {response.status} - {response_text}")
                        return {
                            "success": False,
                            "status": "unknown"
                        }
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            return {"success": False, "status": "unknown"}

    def verify_webhook(self, signature: str, payload: str) -> bool:
        """Verify Tribute webhook signature"""
        if not self.webhook_secret:
            logger.warning("⚠️ Webhook secret not configured")
            return True

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
        'price': 99,
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
    """Проверка настроек Tribute"""
    if not config.TRIBUTE_API_KEY:
        logger.error("❌ TRIBUTE_API_KEY не настроен в .env!")
        return False

    logger.info(f"✅ Tribute API Key configured: {config.TRIBUTE_API_KEY[:10]}...")
    return True


tribute = TributePayment()


async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available subscription packages"""
    query = update.callback_query
    await query.answer()

    keyboard = []

    for package in SUBSCRIPTION_PACKAGES:
        button_text = f"{package['name']} - {package['price']} ₽"
        callback_data = f"buy_package_{package['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

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
        discount = " 🔥" if pack["coins"] >= 200 else ""
        button_text = f"💰 {pack['coins']} монет - {pack['price']} ₽{discount}"
        callback_data = f"buy_coins_{pack['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="subscriptions")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """💰 **Прямая покупка монет**

Купите монеты без подписки!
Монеты не истекают.

🎯 Чем больше пакет - тем выгоднее!"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription package selection"""
    query = update.callback_query
    user = query.from_user
    callback_data = query.data

    # Determine package
    if callback_data.startswith("buy_package_"):
        package_id = callback_data.replace("buy_package_", "")
        package = next((p for p in SUBSCRIPTION_PACKAGES if p['id'] == package_id), None)
    elif callback_data.startswith("buy_coins_"):
        coins_id = callback_data.replace("buy_coins_", "")
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

    # Get user
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

    # Create order
    order_id = str(uuid.uuid4())

    # Save to DB
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
            days=package.get('days', 0)
        )
        session.add(payment)
        await session.commit()

    # Create Tribute payment
    logger.info(f"🔄 Creating payment: {package['name']}, {package['price']} RUB")

    payment_result = await tribute.create_payment(
        amount=package['price'],
        order_id=order_id,
        description=package['description'],
        telegram_id=user.id
    )

    if not payment_result['success']:
        error_msg = payment_result.get('error', 'Unknown')
        logger.error(f"❌ Payment failed: {error_msg}")

        await query.message.reply_text(
            f"❌ **Ошибка создания платежа**\n\n"
            f"Причина: {error_msg}\n\n"
            f"Проверьте:\n"
            f"1️⃣ API ключ Tribute\n"
            f"2️⃣ Баланс в Tribute\n\n"
            f"Попробуйте позже.",
            parse_mode='Markdown'
        )
        return

    # Success - show payment button
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_result['payment_url'])],
        [InlineKeyboardButton("✅ Проверить", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    period_text = f"📅 Период: {package['days']} дней\n" if package.get('days', 0) > 0 else ""

    text = f"""💳 **Оплата через Tribute**

📦 Пакет: {package['name']}
💰 Монет: {package['coins']}
{period_text}💵 К оплате: {package['price']} ₽

➡️ Нажмите "Оплатить"
➡️ После оплаты нажмите "Проверить"

🆔 ID: `{order_id[:12]}`"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # Store info
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
    payment_info = context.user_data.get(f'payment_{order_id}')

    await query.answer("⏳ Проверяем...")

    # Check with Tribute
    status_result = await tribute.check_payment_status(order_id)

    if not status_result['success']:
        await query.answer("⏳ Попробуйте через минуту", show_alert=True)
        return

    status = status_result.get('status')

    if status == 'pending':
        await query.answer("⏳ Обрабатывается...", show_alert=True)
        return

    if status in ['paid', 'success', 'completed']:
        await query.answer("✅ Оплачено!", show_alert=True)

        # Update DB
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

                # Add coins
                db_user = await db_manager.get_user(user.id)

                try:
                    if payment.days > 0:
                        await api_client.purchase_subscription(
                            token=db_user.api_token,
                            coins=payment.coins,
                            days=payment.days,
                            price=float(payment.amount)
                        )
                    else:
                        balance = await api_client.get_balance(db_user.api_token)
                        new_balance = balance['balance'] + payment.coins
                        await api_client.set_balance(
                            token=db_user.api_token,
                            amount=new_balance,
                            source='purchase'
                        )

                    success_text = f"""✅ **Платеж успешен!**

💰 Начислено: {payment.coins} монет
"""
                    if payment.days > 0:
                        success_text += f"📅 На {payment.days} дней\n"

                    success_text += f"""💵 Оплачено: {payment.amount} ₽

Спасибо! 🎉
/balance - проверить баланс"""

                    await query.message.reply_text(success_text, parse_mode='Markdown')

                    # Cleanup
                    if f'payment_{order_id}' in context.user_data:
                        del context.user_data[f'payment_{order_id}']

                except Exception as e:
                    logger.error(f"❌ Activation error: {e}")
                    await query.message.reply_text(
                        f"⚠️ Ошибка начисления.\n"
                        f"ID: {order_id[:12]}\n"
                        f"Обратитесь в поддержку"
                    )


async def start_promo_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start promo entry"""
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🎁 **Введите промокод**\n\n"
        "Отправьте промокод:",
        parse_mode='Markdown'
    )

    return AWAITING_PROMO


async def process_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process promo code"""
    promo_code = update.message.text.strip().upper()

    promo_codes = {
        'WELCOME50': {'coins': 50, 'message': '+50 монет'},
        'FITNESS100': {'coins': 100, 'message': '+100 монет'},
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
                    f"💰 Баланс: {new_balance} монет",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Promo error: {e}")
                await update.message.reply_text("❌ Ошибка")
        else:
            await update.message.reply_text("❌ Свяжите аккаунт")
    else:
        await update.message.reply_text("❌ Неверный промокод")

    return ConversationHandler.END


async def cancel_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel promo"""
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END


def register_payment_handlers(application):
    """Register handlers"""
    if not validate_tribute_config():
        logger.warning("⚠️ Tribute config validation failed!")

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