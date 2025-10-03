from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import json
from typing import Optional, Dict, Any
from bot.config import config

Base = declarative_base()


class User(Base):
    __tablename__ = 'bot_users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    email = Column(String(255))
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))

    # API user linkage
    api_user_id = Column(String(255))
    api_token = Column(Text)

    # Stats
    registration_coins = Column(Integer, default=config.DEFAULT_REGISTRATION_COINS)
    total_spent = Column(Float, default=0.0)

    # Tracking
    referral_link = Column(String(255))
    referred_by = Column(String(255))
    referral_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    # Admin
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)


class Payment(Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    telegram_id = Column(Integer)

    payment_id = Column(String(255), unique=True)
    amount = Column(Float)
    currency = Column(String(10), default='RUB')
    status = Column(String(50))  # pending, completed, failed

    package_id = Column(String(100))
    coins = Column(Integer)
    days = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    metadata = Column(Text)  # JSON string


class ReferralLink(Base):
    __tablename__ = 'referral_links'

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True)
    name = Column(String(255))  # e.g., "Fitness Center Moscow"
    description = Column(Text)

    creator_telegram_id = Column(Integer)

    # Stats
    clicks = Column(Integer, default=0)
    registrations = Column(Integer, default=0)
    purchases = Column(Integer, default=0)
    total_revenue = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class CoinSpending(Base):
    __tablename__ = 'coin_spending'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    api_user_id = Column(String(255))

    amount = Column(Integer)
    feature = Column(String(100))  # photo, voice, text
    description = Column(Text)

    timestamp = Column(DateTime, default=datetime.utcnow)
    date = Column(String(10))  # YYYY-MM-DD for grouping


# Database manager
class DatabaseManager:
    def __init__(self):
        self.engine = create_async_engine(config.DATABASE_URL)
        self.SessionLocal = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def init_db(self):
        """Initialize database"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        """Get database session"""
        async with self.SessionLocal() as session:
            return session

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Get user by telegram ID"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def create_user(self, telegram_id: int, **kwargs) -> User:
        """Create new user"""
        async with self.SessionLocal() as session:
            user = User(telegram_id=telegram_id, **kwargs)
            session.add(user)
            await session.commit()
            return user


db_manager = DatabaseManager()