#!/usr/bin/env python
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.config import config
from bot.database import db_manager
from bot.handlers import start, admin, payment
import sys

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL),
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Initialize bot after startup"""
    # Initialize database
    await db_manager.init_db()
    logger.info("Database initialized")

    # Set bot commands
    await application.bot.set_my_commands([
        ("start", "Главное меню"),
        ("help", "Помощь"),
        ("balance", "Проверить баланс"),
        ("subscribe", "Купить подписку"),
        ("stats", "Статистика"),
        ("admin", "Админ панель (только для админов)")
    ])
    logger.info("Bot commands set")


def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    start.register_start_handlers(application)
    admin.register_admin_handlers(application)
    payment.register_payment_handlers(application)

    # Error handler
    async def error_handler(update: Update, context):
        logger.error(f"Exception while handling an update: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
            )

    application.add_error_handler(error_handler)

    # Start bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()