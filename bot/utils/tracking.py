from bot.database import db_manager, ReferralLink, User
from sqlalchemy import select, update
import logging

logger = logging.getLogger(__name__)


async def track_referral(code: str, telegram_id: int):
    """Track referral link click and registration"""
    async with db_manager.SessionLocal() as session:
        # Find referral link
        result = await session.execute(
            select(ReferralLink).where(ReferralLink.code == code)
        )
        link = result.scalar_one_or_none()

        if link:
            # Update clicks
            link.clicks += 1

            # Check if user registered
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user and not user.referred_by:
                user.referred_by = code
                link.registrations += 1

                # If link has creator, increase their referral count
                if link.creator_telegram_id:
                    creator_result = await session.execute(
                        select(User).where(User.telegram_id == link.creator_telegram_id)
                    )
                    creator = creator_result.scalar_one_or_none()
                    if creator:
                        creator.referral_count += 1

            await session.commit()
            logger.info(f"Tracked referral: {code} for user {telegram_id}")


async def track_purchase(code: str, amount: float):
    """Track purchase from referral link"""
    async with db_manager.SessionLocal() as session:
        result = await session.execute(
            select(ReferralLink).where(ReferralLink.code == code)
        )
        link = result.scalar_one_or_none()

        if link:
            link.purchases += 1
            link.total_revenue += amount
            await session.commit()
            logger.info(f"Tracked purchase: {code} amount {amount}")


async def get_referral_stats(code: str) -> dict:
    """Get referral link statistics"""
    async with db_manager.SessionLocal() as session:
        result = await session.execute(
            select(ReferralLink).where(ReferralLink.code == code)
        )
        link = result.scalar_one_or_none()

        if link:
            return {
                'name': link.name,
                'clicks': link.clicks,
                'registrations': link.registrations,
                'purchases': link.purchases,
                'revenue': link.total_revenue,
                'created': link.created_at
            }

        return {}