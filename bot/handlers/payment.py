# bot/handlers/payment.py

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
from typing import Optional, List, Dict
import asyncio

logger = logging.getLogger(__name__)

AWAITING_PROMO = 1


class TributePayment:
    """Tribute.tg payment integration with Products API"""

    def __init__(self):
        self.api_key = config.TRIBUTE_API_KEY
        self.webhook_secret = config.TRIBUTE_WEBHOOK_SECRET
        self.base_url = "https://tribute.tg/api"

        # ID продуктов в Tribute (после создания)
        self.product_ids = {
            'week_50': None,  # Заполнится после создания
            'two_weeks_100': None,
            'month_200': None,
            'month_500': None,
        }

    async def init_products(self):
        """
        Инициализация продуктов в Tribute
        Вызывается один раз при запуске бота
        """
        logger.info("🛍️ Initializing Tribute products...")

        products_to_create = [
            {
                'name': '📅 Неделя (50 монет)',
                'price': 99,
                'description': '50 монет на 7 дней',
                'key': 'week_50',
                'coins': 50,
                'days': 7
            },
            {
                'name': '📆 2 недели (100 монет)',
                'price': 199,
                'description': '100 монет на 14 дней',
                'key': 'two_weeks_100',
                'coins': 100,
                'days': 14
            },
            {
                'name': '📆 Месяц (200 монет)',
                'price': 299,
                'description': '200 монет на 30 дней',
                'key': 'month_200',
                'coins': 200,
                'days': 30
            },
            {
                'name': '💎 Премиум (500 монет)',
                'price': 499,
                'description': '500 монет на 30 дней',
                'key': 'month_500',
                'coins': 500,
                'days': 30
            }
        ]

        # Сначала получаем список существующих продуктов
        existing_products = await self.get_products()

        for product_data in products_to_create:
            # Проверяем, есть ли уже такой продукт
            existing = next(
                (p for p in existing_products if p['name'] == product_data['name']),
                None
            )

            if existing:
                logger.info(f"✅ Product already exists: {product_data['name']} (ID: {existing['id']})")
                self.product_ids[product_data['key']] = existing['id']
            else:
                # Создаем новый продукт
                result = await self.create_product(
                    name=product_data['name'],
                    price=product_data['price'],
                    description=product_data['description']
                )

                if result['success']:
                    product_id = result['product_id']
                    self.product_ids[product_data['key']] = product_id
                    logger.info(f"✅ Created product: {product_data['name']} (ID: {product_id})")
                else:
                    logger.error(f"❌ Failed to create product: {product_data['name']}")

        logger.info(f"🛍️ Products initialized: {self.product_ids}")

    async def get_products(self) -> List[Dict]:
        """Получить список всех продуктов"""
        if not self.api_key:
            return []

        params = {
            "api_key": self.api_key
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        f"{self.base_url}/products",
                        params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('products', [])
                    else:
                        logger.error(f"Failed to get products: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            return []

    async def create_product(self, name: str, price: float, description: str) -> dict:
        """
        Создать цифровой товар в Tribute

        Args:
            name: Название товара
            price: Цена в рублях
            description: Описание товара
        """
        if not self.api_key:
            return {"success": False, "error": "API key not configured"}

        params = {
            "api_key": self.api_key,
            "name": name,
            "price": int(price),
            "description": description
        }

        logger.info(f"📤 Creating product: {name} - {price}₽")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        f"{self.base_url}/products/create",
                        params=params
                ) as response:
                    response_text = await response.text()

                    logger.info(f"📥 Create product response: {response.status} - {response_text}")

                    if response.status in [200, 201]:
                        try:
                            data = await response.json()
                            product_id = data.get('id') or data.get('product_id')

                            if product_id:
                                return {
                                    "success": True,
                                    "product_id": product_id
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": "No product ID in response"
                                }
                        except:
                            # Если ответ не JSON, возможно это просто ID
                            if response_text.isdigit():
                                return {
                                    "success": True,
                                    "product_id": int(response_text)
                                }
                            return {
                                "success": False,
                                "error": "Invalid response format"
                            }
                    else:
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}"
                        }

        except Exception as e:
            logger.error(f"❌ Error creating product: {e}")
            return {"success": False, "error": str(e)}

    async def create_payment_link(self, product_key: str, telegram_id: int,
                                  custom_order_id: Optional[str] = None) -> dict:
        """
        Создать ссылку на оплату для конкретного продукта

        Args:
            product_key: Ключ продукта (week_50, month_200, и т.д.)
            telegram_id: ID пользователя в Telegram
            custom_order_id: Кастомный ID заказа (опционально)
        """
        product_id = self.product_ids.get(product_key)

        if not product_id:
            return {
                "success": False,
                "error": f"Product {product_key} not found"
            }

        params = {
            "api_key": self.api_key,
            "product_id": product_id,
            "telegram_id": telegram_id
        }

        # Добавляем кастомный order_id если указан
        if custom_order_id:
            params["order_id"] = custom_order_id

        logger.info(f"📤 Creating payment link for product {product_key} (ID: {product_id})")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                        f"{self.base_url}/create",
                        params=params
                ) as response:
                    response_text = await response.text()

                    logger.info(f"📥 Payment link response: {response.status} - {response_text}")

                    if response.status in [200, 201]:
                        # Ответ - это URL для оплаты
                        if response_text.startswith('http'):
                            return {
                                "success": True,
                                "payment_url": response_text.strip(),
                                "order_id": custom_order_id
                            }
                        else:
                            try:
                                data = await response.json()
                                payment_url = data.get("payment_url") or data.get("url")

                                return {
                                    "success": True,
                                    "payment_url": payment_url,
                                    "order_id": custom_order_id
                                }
                            except:
                                return {
                                    "success": False,
                                    "error": "Invalid response format"
                                }
                    else:
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}"
                        }

        except Exception as e:
            logger.error(f"❌ Error creating payment link: {e}")
            return {"success": False, "error": str(e)}

    async def check_payment_status(self, order_id: str) -> dict:
        """Проверить статус оплаты"""
        if not self.api_key:
            return {"success": False, "status": "unknown"}

        params = {
            "api_key": self.api_key,
            "order_id": order_id
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

                        return {
                            "success": True,
                            "status": "paid" if is_paid else "pending",
                            "amount": data.get("amount"),
                            "order_id": order_id
                        }
                    else:
                        return {"success": False, "status": "unknown"}
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            return {"success": False, "status": "unknown"}


# Пакеты подписок
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
        InlineKeyboardButton("🎁 Ввести промокод", callback_data="enter_promo")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """💳 **Покупка монет и подписок**

✅ Оплата через Tribute - безопасно и удобно
✅ Работает с российскими картами  
✅ Моментальное зачисление через webhook

Выберите подходящий пакет:"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription package selection"""
    query = update.callback_query
    user = query.from_user
    callback_data = query.data

    # Определяем пакет
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

    # Получаем пользователя
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

    # Создаем order_id
    order_id = str(uuid.uuid4())

    # Сохраняем в БД
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

    # Создаем ссылку на оплату через Products API
    logger.info(f"🔄 Creating payment link for: {package['name']}")

    payment_result = await tribute.create_payment_link(
        product_key=package['id'],
        telegram_id=user.id,
        custom_order_id=order_id
    )

    if not payment_result['success']:
        error_msg = payment_result.get('error', 'Unknown')
        logger.error(f"❌ Payment link creation failed: {error_msg}")

        # ИСПРАВЛЕНО: убрали parse_mode='Markdown' из сообщения об ошибке
        await query.message.reply_text(
            f"❌ Ошибка создания платежа\n\n"
            f"Причина: {error_msg}\n\n"
            f"Попробуйте позже или обратитесь в поддержку."
        )
        return

    # Успех - показываем кнопку оплаты
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_result['payment_url'])],
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data="subscriptions")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # ИСПРАВЛЕНО: правильное экранирование для MarkdownV2
    order_id_short = order_id[:12]

    text = f"""💳 *Оплата через Tribute*

📦 Пакет: {package['name']}
💰 Монет: {package['coins']}
📅 Период: {package['days']} дней
💵 К оплате: {package['price']} ₽

➡️ Нажмите "Оплатить"
➡️ После оплаты нажмите "Я оплатил"

💡 Монеты зачислятся автоматически через несколько секунд после оплаты

🆔 ID заказа: `{order_id_short}`"""

    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # Сохраняем информацию
    context.user_data[f'payment_{order_id}'] = {
        'amount': package['price'],
        'coins': package['coins'],
        'days': package.get('days', 0),
        'package_id': package['id']
    }


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check payment status"""
    query = update.callback_query
    user = query.from_user

    order_id = query.data.replace("check_payment_", "")

    await query.answer("⏳ Проверяем статус оплаты...")

    # Проверяем статус в Tribute
    status_result = await tribute.check_payment_status(order_id)

    if not status_result['success']:
        await query.answer("⏳ Не удалось проверить статус. Попробуйте через минуту", show_alert=True)
        return

    status = status_result.get('status')

    if status == 'pending':
        await query.answer("⏳ Платеж еще обрабатывается. Подождите немного...", show_alert=True)
        return

    if status in ['paid', 'success', 'completed']:
        # Проверяем, не начислены ли уже монеты
        from sqlalchemy import select
        async with db_manager.SessionLocal() as session:
            result = await session.execute(
                select(Payment).where(Payment.payment_id == order_id)
            )
            payment = result.scalar_one_or_none()

            if payment and payment.status == 'completed':
                await query.answer("✅ Монеты уже начислены!", show_alert=True)
                return

            if payment and payment.status != 'completed':
                payment.status = 'completed'
                payment.completed_at = datetime.utcnow()
                session.add(payment)
                await session.commit()

                # Начисляем монеты
                db_user = await db_manager.get_user(user.id)

                try:
                    # Покупка подписки с монетами
                    await api_client.purchase_subscription(
                        token=db_user.api_token,
                        coins=payment.coins,
                        days=payment.days,
                        price=float(payment.amount)
                    )

                    success_text = f"""✅ **Оплата успешно подтверждена!**

💰 Начислено: {payment.coins} монет
📅 На {payment.days} дней
💵 Оплачено: {payment.amount} ₽

Спасибо за покупку! 🎉

Монеты будут списываться автоматически через {payment.days} дней.
/balance - проверить баланс"""

                    await query.message.reply_text(success_text, parse_mode='Markdown')

                    # Очищаем данные
                    if f'payment_{order_id}' in context.user_data:
                        del context.user_data[f'payment_{order_id}']

                except Exception as e:
                    logger.error(f"❌ Activation error: {e}")
                    await query.message.reply_text(
                        f"⚠️ **Ошибка начисления монет**\n\n"
                        f"Оплата прошла успешно, но возникла ошибка при начислении.\n"
                        f"ID заказа: `{order_id[:12]}`\n\n"
                        f"Обратитесь в поддержку с этим ID.",
                        parse_mode='Markdown'
                    )
    else:
        await query.answer("❌ Платеж не найден или отменен", show_alert=True)


def register_payment_handlers(application):
    """Register handlers"""
    application.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(handle_package_selection, pattern="^buy_package_"))
    application.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment_"))