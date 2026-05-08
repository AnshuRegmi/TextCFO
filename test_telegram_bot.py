"""
Test suite for telegram_bot.py handlers.

Tests all handler functions:
- start() - /start command
- clear() - /clear command  
- handle_message() - text message handling
- Authorization checks
- Error handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Chat, Message
from telegram.ext import ContextTypes

# Import handlers from telegram_bot
from telegram_bot import start, clear, handle_message


class TestStartHandler:
    """Tests for /start command handler."""

    @pytest.mark.asyncio
    async def test_start_authorized_user(self):
        """Test /start command with authorized user."""
        # Setup
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.reply_text = AsyncMock()
        
        # Mock allowed users
        with patch("telegram_bot.ALLOWED_USERS", {12345}):
            await start(update, context)
        
        # Verify reply was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "🤖 *Tally BI Bot*" in call_args[0][0]
        assert "parse_mode" in call_args[1]

    @pytest.mark.asyncio
    async def test_start_unauthorized_user(self):
        """Test /start command with unauthorized user."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 99999
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", {12345}):
            await start(update, context)
        
        # Verify rejection
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "⛔ Unauthorized" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_start_no_restrictions(self):
        """Test /start command with no user restrictions."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            with patch("telegram_bot.mcp_client", MagicMock(tools=[MagicMock()])):
                await start(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "🤖 *Tally BI Bot*" in call_args[0][0]


class TestClearHandler:
    """Tests for /clear command handler."""

    @pytest.mark.asyncio
    async def test_clear_existing_conversation(self):
        """Test /clear command clears existing conversation history."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.reply_text = AsyncMock()
        
        # Setup conversation history
        with patch("telegram_bot.conversation_history", {"12345": ["old message"]}):
            await clear(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "🧹 Conversation cleared" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_clear_new_user(self):
        """Test /clear command for user with no history."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 99999
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.conversation_history", {}):
            await clear(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "🧹 Conversation cleared" in call_args[0][0]


class TestHandleMessageHandler:
    """Tests for message handling."""

    @pytest.mark.asyncio
    async def test_handle_message_authorized_user(self):
        """Test message handler with authorized user."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = "What is the trial balance?"
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", {12345}):
            with patch("telegram_bot.mcp_client", MagicMock()):
                with patch("telegram_bot.handle_query", new_callable=AsyncMock, return_value="Trial balance: $1000"):
                    await handle_message(update, context)
        
        # Verify typing action was sent
        update.message.chat.send_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_unauthorized_user(self):
        """Test message handler rejects unauthorized user."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 99999
        update.message.text = "Hello"
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", {12345}):
            await handle_message(update, context)
        
        call_args = update.message.reply_text.call_args
        assert "⛔ Unauthorized" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_message_empty_text(self):
        """Test message handler ignores empty messages."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = None
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            await handle_message(update, context)
        
        # Should return early, no reply sent
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_long_response(self):
        """Test message handler splits long responses."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = "Show me full report"
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        
        # Create a long response (> 4000 chars)
        long_response = "A" * 10000
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            with patch("telegram_bot.mcp_client", MagicMock()):
                with patch("telegram_bot.handle_query", new_callable=AsyncMock, return_value=long_response):
                    await handle_message(update, context)
        
        # Should be called 3 times (10000 / 4000 = 2.5, rounded up to 3)
        assert update.message.reply_text.call_count == 3

    @pytest.mark.asyncio
    async def test_handle_message_error_handling(self):
        """Test message handler catches and reports errors."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = "Show me data"
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            with patch("telegram_bot.mcp_client", MagicMock()):
                with patch("telegram_bot.handle_query", new_callable=AsyncMock, side_effect=Exception("Connection failed")):
                    await handle_message(update, context)
        
        # Verify error was reported
        call_args = update.message.reply_text.call_args_list[-1]
        assert "❌ Error" in call_args[0][0]
        assert "Connection failed" in call_args[0][0]


class TestAuthorizationFlow:
    """Tests for authorization logic across handlers."""

    @pytest.mark.asyncio
    async def test_authorization_with_multiple_users(self):
        """Test authorization with multiple allowed users."""
        allowed_users = {111, 222, 333}
        
        # Test authorized
        update_auth = MagicMock(spec=Update)
        update_auth.effective_user.id = 222
        update_auth.message.reply_text = AsyncMock()
        
        # Test unauthorized
        update_unauth = MagicMock(spec=Update)
        update_unauth.effective_user.id = 999
        update_unauth.message.reply_text = AsyncMock()
        
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        with patch("telegram_bot.ALLOWED_USERS", allowed_users):
            await start(update_auth, context)
            await start(update_unauth, context)
        
        # Authorized should get bot greeting
        auth_call = update_auth.message.reply_text.call_args
        assert "🤖 *Tally BI Bot*" in auth_call[0][0]
        
        # Unauthorized should get rejection
        unauth_call = update_unauth.message.reply_text.call_args
        assert "⛔ Unauthorized" in unauth_call[0][0]


class TestConversationHistoryManagement:
    """Tests for conversation history handling."""

    @pytest.mark.asyncio
    async def test_clear_resets_history(self):
        """Test that clear command resets conversation history."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.reply_text = AsyncMock()
        
        conversation_history = {"12345": ["msg1", "msg2", "msg3"]}
        
        with patch("telegram_bot.conversation_history", conversation_history):
            await clear(update, context)
        
        # History should be reset to empty list
        assert conversation_history.get("12345") == []


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_handle_message_with_special_characters(self):
        """Test message handler with special characters."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = "Show me P&L with ©2024 data"
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            with patch("telegram_bot.mcp_client", MagicMock()):
                with patch("telegram_bot.handle_query", new_callable=AsyncMock, return_value="OK"):
                    await handle_message(update, context)
        
        update.message.chat.send_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_whitespace_only(self):
        """Test message handler with whitespace-only text."""
        update = MagicMock(spec=Update)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        update.effective_user.id = 12345
        update.message.text = "   "
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        
        with patch("telegram_bot.ALLOWED_USERS", set()):
            with patch("telegram_bot.mcp_client", MagicMock()):
                with patch("telegram_bot.handle_query", new_callable=AsyncMock, return_value="OK"):
                    await handle_message(update, context)
        
        # Whitespace-only text still gets processed by handle_query
        update.message.chat.send_action.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
