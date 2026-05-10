# Lines 1-9: IMPORTS
import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from orchestrator import TallyMCPClient, handle_query

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Lines 11-22: CONFIGURATION
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = set()
allowed_str = os.getenv("ALLOWED_TELEGRAM_USERS", "")
if allowed_str:
    ALLOWED_USERS = {
        int(uid.strip()) for uid in allowed_str.split(",") if uid.strip()
    }

conversation_history = {}
mcp_client = None  # Initialized on startup

# Lines 27-35: post_init() - ERROR HANDLING IMPROVED
async def post_init(application):
    """Called after bot starts — connect to MCP server."""
    global mcp_client
    try:
        mcp_client = TallyMCPClient()
        await mcp_client.connect()
        print("✅ MCP client connected, bot ready!")
        logger.info("Successfully connected to Tally MCP server")
    except ConnectionError as e:
        logger.error(f"Failed to connect to Tally MCP: {e}")
        print("⚠️  Warning: Could not connect to Tally MCP. Bot will run in degraded mode.")
        mcp_client = None
    except Exception as e:
        logger.error(f"Unexpected error during MCP initialization: {e}")
        print("⚠️  Warning: MCP initialization failed. Bot will run in degraded mode.")
        mcp_client = None


# Lines 33-52: start() Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ALLOWED_USERS and uid not in ALLOWED_USERS:
        await update.message.reply_text(f"⛔ Unauthorized. Your ID: {uid}")
        return

    tools_info = ""
    if mcp_client and mcp_client.tools:
        tools_info = f"\n🔧 {len(mcp_client.tools)} tools connected to Tally\n"

    await update.message.reply_text(
        f"🤖 *Tally BI Bot*\n{tools_info}\n"
        "Ask me anything:\n"
        "• _What's the trial balance?_\n"
        "• _Who owes us money?_\n"
        "• _Show me P&L_\n"
        "• _Transactions on 1st July_\n\n"
        "/clear to reset conversation",
        parse_mode="Markdown",
    )

# Lines 63-90: handle_message() - ERROR HANDLING IMPROVED
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ALLOWED_USERS and uid not in ALLOWED_USERS:
        await update.message.reply_text(f"⛔ Unauthorized. Your ID: {uid}")
        logger.warning(f"Unauthorized access attempt from user {uid}")
        return

    query = update.message.text
    if not query:
        return

    # Check if MCP is connected
    if not mcp_client:
        await update.message.reply_text(
            "⚠️ Tally connection is currently unavailable. Please try again in a moment."
        )
        logger.error("User query received but MCP client not available")
        return

    await update.message.chat.send_action("typing")

    try:
        answer = await asyncio.wait_for(
            handle_query(mcp_client, str(uid), query, conversation_history),
            timeout=30.0
        )
        # Split response into chunks if too long
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i : i + 4000])
        logger.info(f"Successfully handled query from user {uid}")
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⏱️ Query timed out. Tally might be busy. Please try again."
        )
        logger.warning(f"Query timeout for user {uid}")
    except ConnectionError as e:
        await update.message.reply_text(
            "🔴 Cannot reach Tally. Please try again later or contact support."
        )
        logger.error(f"Connection error for user {uid}: {e}")
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Invalid query: {str(e)[:100]}"
        )
        logger.warning(f"Invalid query from user {uid}: {e}")
    except Exception as e:
        error_msg = str(e)[:100]
        await update.message.reply_text(
            f"❌ Unexpected error: {error_msg}\nPlease try again or contact support."
        )
        logger.error(f"Unexpected error handling query from user {uid}: {e}", exc_info=True)


# Lines 77-84: clear() Command Handler
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    # Clear from all possible locations
    conversation_history.pop(uid, None)
    conversation_history[uid] = []  # Reset to empty list

    await update.message.reply_text("🧹 Conversation cleared! Ask me something fresh.")

# Lines 123-145: main() - ERROR HANDLING IMPROVED
def main():
    """Main entry point for the Telegram bot."""
    # Validate required configuration
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        print("❌ ERROR: Set TELEGRAM_BOT_TOKEN in .env file")
        return

    try:
        print(f"🤖 Starting Tally BI Bot...")
        logger.info("Bot initialization started")
        
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("clear", clear))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Error handler for callback context
        app.add_error_handler(error_handler)
        
        print("🚀 Bot running... Press Ctrl+C to stop")
        logger.info("Bot started successfully")
        app.run_polling()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        print(f"❌ ERROR: Could not start bot: {e}")
        return


async def error_handler(update, context):
    """Log and handle errors from callback context."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)

# Lines 102-103: Entry Point
if __name__ == "__main__":
    main()
