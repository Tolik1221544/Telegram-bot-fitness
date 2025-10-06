#!/usr/bin/env python
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.config import config
from bot.database import db_manager
from bot.handlers import start, admin, payment, user
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

    # Initialize Tribute products
    from bot.handlers.payment import tribute
    try:
        logger.info("🛍️ Starting Tribute products initialization...")
        await tribute.init_products()
        logger.info("✅ Tribute products initialized successfully")
        logger.info(f"📦 Product IDs: {tribute.product_ids}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Tribute products: {e}")
        logger.exception("Full traceback:")

    # Set bot commands
    await application.bot.set_my_commands([
        ("start", "Главное меню"),
        ("balance", "Проверить баланс"),
        ("subscribe", "Купить подписку"),
        ("admin", "Админ панель")
    ])
    logger.info("Bot commands set")


def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    start.register_start_handlers(application)
    user.register_user_handlers(application)  # Добавили
    admin.register_admin_handlers(application)
    payment.register_payment_handlers(application)

    # Error handler
    async def error_handler(update: Update, context):
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
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