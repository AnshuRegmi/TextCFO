# Lines 1-9: IMPORTS
import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from orchestrator import TallyMCPClient, handle_query

load_dotenv()

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

# Lines 25-30: post_init() - SKELETON
async def post_init(application):
    """Called after bot starts — connect to MCP server."""
    global mcp_client
    mcp_client = TallyMCPClient()
    await mcp_client.connect()
    print("✅ MCP client connected, bot ready!")

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

# Lines 55-74: handle_message() Function
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ALLOWED_USERS and uid not in ALLOWED_USERS:
        await update.message.reply_text(f"⛔ Unauthorized. Your ID: {uid}")
        return

    query = update.message.text
    if not query:
        return

    await update.message.chat.send_action("typing")

    try:
        answer = await handle_query(
            mcp_client, str(uid), query, conversation_history
        )
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i : i + 4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# Lines 77-84: clear() Command Handler
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    # Clear from all possible locations
    conversation_history.pop(uid, None)
    conversation_history[uid] = []  # Reset to empty list

    await update.message.reply_text("🧹 Conversation cleared! Ask me something fresh.")

# Lines 87-99: main() Function
def main():
    if not BOT_TOKEN:
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return

    print(f"🤖 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Running!")
    app.run_polling()

# Lines 102-103: Entry Point
if __name__ == "__main__":
    main()
