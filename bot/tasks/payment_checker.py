import asyncio
import logging
from datetime import datetime, timedelta
from bot.database import db_manager, Payment, User
from bot.api_client import api_client
from bot.handlers.payment import SUBSCRIPTION_PACKAGES
from telegram import Bot
from bot.config import config

logger = logging.getLogger(__name__)


class TributePaymentChecker:
    """Фоновая задача для проверки статуса платежей Tribute"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.check_interval = 60  # Проверка каждые 60 секунд
        self.is_running = False

    async def start(self):
        """Запуск фоновой задачи"""
        if self.is_running:
            logger.warning("Payment checker already running")
            return

        self.is_running = True
        logger.info("🔄 Starting Tribute payment checker...")

        while self.is_running:
            try:
                await self.check_pending_payments()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in payment checker: {e}")
                await asyncio.sleep(self.check_interval)

    async def stop(self):
        """Остановка фоновой задачи"""
        self.is_running = False
        logger.info("🛑 Stopping Tribute payment checker...")

    async def check_pending_payments(self):
        """Проверка всех pending платежей"""
        async with db_manager.SessionLocal() as session:
            # Получаем все pending платежи за последние 24 часа
            from sqlalchemy import select

            cutoff_time = datetime.utcnow() - timedelta(hours=24)

            stmt = select(Payment).where(
                Payment.status == 'pending',
                Payment.created_at >= cutoff_time
            )

            result = await session.execute(stmt)
            pending_payments = result.scalars().all()

            if not pending_payments:
                return

            logger.info(f"📋 Checking {len(pending_payments)} pending payments...")

            for payment in pending_payments:
                await self.check_single_payment(payment, session)

    async def check_single_payment(self, payment: Payment, session):
        """Проверка одного платежа"""
        try:
            # Получаем пользователя
            stmt = select(User).where(User.telegram_id == payment.telegram_id)
            result = await session.execute(stmt)
            db_user = result.scalar_one_or_none()

            if not db_user or not db_user.api_token:
                return

            # Проверяем статус на сервере
            payment_status = await api_client.check_tribute_payment(payment.telegram_id)

            if not payment_status.get('success'):
                return

            subscription = payment_status.get('subscription', {})

            # Проверяем, соответствует ли подписка нашему платежу
            if not subscription or not subscription.get('isActive'):
                return

            # Проверяем время покупки
            purchase_time = subscription.get('purchasedAt')
            if purchase_time:
                try:
                    purchase_dt = datetime.fromisoformat(purchase_time.replace('Z', '+00:00'))

                    # Если покупка произошла после создания нашего платежа
                    if purchase_dt >= payment.created_at:
                        # Находим соответствующий пакет
                        package = next((p for p in SUBSCRIPTION_PACKAGES
                                        if p['id'] == payment.package_id), None)

                        if package:
                            # Обновляем статус платежа
                            payment.status = 'completed'
                            payment.completed_at = datetime.utcnow()

                            logger.info(f"✅ Payment {payment.payment_id} completed for user {payment.telegram_id}")

                            # Отправляем уведомление пользователю
                            await self.notify_user_payment_complete(
                                payment.telegram_id,
                                package,
                                subscription
                            )

                            await session.commit()

                except Exception as e:
                    logger.error(f"Error parsing purchase time: {e}")

        except Exception as e:
            logger.error(f"Error checking payment {payment.payment_id}: {e}")

    async def notify_user_payment_complete(self, telegram_id: int, package: dict, subscription: dict):
        """Отправка уведомления пользователю об успешном платеже"""
        try:
            message = f"""✅ **Платёж успешно обработан!**

📦 Пакет: {package['name']}
💰 Начислено: {package['coins']} монет
📅 Период: {package['days']} дней
⏰ Действует до: {subscription.get('expiresAt', 'н/д')[:10] if subscription.get('expiresAt') else 'н/д'}

Монеты уже доступны в приложении!
Проверьте баланс: /balance"""

            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Error sending notification to user {telegram_id}: {e}")
