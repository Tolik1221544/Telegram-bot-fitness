from bot.database import db_manager, Payment, LwCoinTransaction
from bot.api_client import api_client
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def handle_tribute_payment(payment_data: dict):
    """
    Обработка успешного платежа от Tribute

    Вызывается когда Tribute отправляет webhook на ваш бэкенд.
    Бэкенд должен вызвать эту функцию с данными платежа.

    Args:
        payment_data: {
            'user_id': telegram_id пользователя,
            'package_id': ID пакета ('year', '6months', etc),
            'amount': сумма платежа,
            'currency': валюта,
            'transaction_id': ID транзакции от Tribute
        }
    """
    try:
        user_id = payment_data.get('user_id')
        package_id = payment_data.get('package_id')
        amount = payment_data.get('amount')
        transaction_id = payment_data.get('transaction_id')

        logger.info(f"💳 Processing Tribute payment: user={user_id}, package={package_id}, amount={amount}")

        # Находим пользователя
        db_user = await db_manager.get_user(user_id)
        if not db_user:
            logger.error(f"❌ User {user_id} not found in database")
            return False

        if not db_user.api_token:
            logger.error(f"❌ User {user_id} has no API token")
            return False

        # Находим пакет подписки
        from bot.handlers.payment import SUBSCRIPTION_PACKAGES
        package = next((p for p in SUBSCRIPTION_PACKAGES if p['id'] == package_id), None)

        if not package:
            logger.error(f"❌ Package {package_id} not found")
            return False

        # Начисляем монеты через API
        result = await api_client.purchase_subscription(
            db_user.api_token,
            coins=package['coins'],
            days=package['days'],
            price=package['price']
        )

        logger.info(f"✅ Coins credited: {package['coins']} to user {user_id}")

        # Обновляем платёж в БД
        async with db_manager.SessionLocal() as session:
            # Находим pending платёж
            from sqlalchemy import select
            stmt = select(Payment).where(
                Payment.telegram_id == user_id,
                Payment.package_id == package_id,
                Payment.status == 'pending'
            ).order_by(Payment.created_at.desc()).limit(1)

            result_payment = await session.execute(stmt)
            payment = result_payment.scalar_one_or_none()

            if payment:
                payment.status = 'completed'
                payment.completed_at = datetime.utcnow()
                payment.payment_id = transaction_id
            else:
                # Создаём новый платёж
                payment = Payment(
                    user_id=db_user.id,
                    telegram_id=user_id,
                    payment_id=transaction_id,
                    amount=amount,
                    currency='EUR',
                    status='completed',
                    package_id=package_id,
                    coins=package['coins'],
                    days=package['days'],
                    completed_at=datetime.utcnow()
                )
                session.add(payment)

            # Записываем транзакцию монет для графика доходов
            coin_transaction = LwCoinTransaction(
                telegram_id=user_id,
                api_user_id=db_user.api_user_id,
                amount=package['coins'],  # Положительное число
                type='purchase',
                feature_used='subscription',
                description=f"Покупка подписки {package['name']}",
                date=datetime.utcnow().strftime('%Y-%m-%d')
            )
            session.add(coin_transaction)

            await session.commit()

        logger.info(f"💾 Payment saved to database: {transaction_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Error processing Tribute payment: {e}")
        logger.exception("Full traceback:")
        return False


async def track_coin_spending(user_id: int, amount: int, feature: str, description: str = None):
    """
    Записать трату монет для графика

    Вызывайте эту функцию когда пользователь тратит монеты в приложении.

    Args:
        user_id: Telegram ID пользователя
        amount: Количество потраченных монет (положительное число)
        feature: Название функции ('photo', 'voice', 'text', 'ai_response')
        description: Описание траты
    """
    try:
        db_user = await db_manager.get_user(user_id)
        if not db_user:
            logger.warning(f"User {user_id} not found for coin spending tracking")
            return

        async with db_manager.SessionLocal() as session:
            # Записываем как ОТРИЦАТЕЛЬНОЕ число для трат
            spending = LwCoinTransaction(
                telegram_id=user_id,
                api_user_id=db_user.api_user_id,
                amount=-abs(amount),  # Отрицательное!
                type='spent',
                feature_used=feature,
                description=description or f"Использована функция {feature}",
                date=datetime.utcnow().strftime('%Y-%m-%d')
            )
            session.add(spending)

            # Обновляем total_spent у пользователя
            db_user.total_spent = (db_user.total_spent or 0) + abs(amount)
            session.add(db_user)

            await session.commit()

        logger.info(f"💸 Tracked spending: user={user_id}, amount={amount}, feature={feature}")

    except Exception as e:
        logger.error(f"Error tracking coin spending: {e}")
