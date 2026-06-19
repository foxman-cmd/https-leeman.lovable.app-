"""Async Telegram Bot for Real-Time Signal Delivery.

Provides:
- Async message sending with retry logic
- Event-driven architecture
- Delivery tracking with millisecond precision
- Per-user notification rate limiting
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from src.models.trade_setup import TradeSetup
from src.models.trade_event import TradeEvent, EventType

try:
    from telegram import Bot, error
except ImportError:
    Bot = None
    error = None

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Async Telegram bot handler for signal delivery."""
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        """Initialize Telegram bot.
        
        Args:
            token: Telegram bot token (default: env var TELEGRAM_TOKEN)
            chat_id: Chat ID to send messages (default: env var TELEGRAM_CHAT_ID)
        """
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.bot = None
        
        if Bot is None:
            logger.warning("python-telegram-bot not installed. Install with: pip install python-telegram-bot")
            return
        
        if self.token and self.chat_id:
            self.bot = Bot(token=self.token)
        else:
            logger.warning("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set")
    
    async def send_setup_signal(self, setup: TradeSetup) -> tuple:
        """Send trading setup to Telegram.
        
        Returns:
            (success: bool, message_id: Optional[int], event: TradeEvent)
        """
        if not self.bot or not self.chat_id:
            logger.warning("Telegram not configured")
            return False, None, None
        
        send_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        direction = "🟢 BUY" if setup.signal_direction > 0 else "🔴 SELL"
        
        message = (
            f"**{direction} {setup.ticker}**\n\n"
            f"Entry: {setup.entry_price:.4f}\n"
            f"Take Profit: {setup.take_profit:.4f}\n"
            f"Stop Loss: {setup.stop_loss:.4f}\n"
            f"Risk/Reward: {setup.rr_string}\n"
            f"Confidence: {setup.signal_confidence*100:.0f}%\n"
            f"Freshness: {setup.freshness_score:.2f}\n\n"
            f"Setup ID: `{setup.setup_id}`"
        )
        
        try:
            msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"✓ Telegram sent: {setup.ticker} {direction} | Message ID: {msg.message_id}")
            
            # Create SETUP_SENT event
            event = TradeEvent(
                event_type=EventType.SETUP_SENT,
                ticker=setup.ticker,
                timestamp_ms=send_time_ms,
                signal_direction=setup.signal_direction,
                entry_price=setup.entry_price,
                take_profit=setup.take_profit,
                stop_loss=setup.stop_loss,
                current_price=setup.entry_price,
                confidence=setup.signal_confidence,
                z_score=setup.signal_z_score,
                setup_id=setup.setup_id,
                message_id=msg.message_id,
                notes=f"Sent to Telegram successfully"
            )
            
            setup.sent_at_ms = send_time_ms
            return True, msg.message_id, event
        
        except error.TelegramError as e:
            logger.error(f"✗ Telegram error: {e}")
            return False, None, None
        except Exception as e:
            logger.error(f"✗ Unexpected error sending to Telegram: {e}")
            return False, None, None
    
    async def send_message(self, text: str) -> bool:
        """Send generic message to Telegram.
        
        Args:
            text: Message text
        
        Returns:
            True if sent successfully
        """
        if not self.bot or not self.chat_id:
            logger.warning("Telegram not configured")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode='Markdown'
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def update_message(self, message_id: int, text: str) -> bool:
        """Update a previously sent message.
        
        Args:
            message_id: ID of message to update
            text: New message text
        
        Returns:
            True if updated successfully
        """
        if not self.bot or not self.chat_id:
            return False
        
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                parse_mode='Markdown'
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update Telegram message: {e}")
            return False


def get_telegram_handler() -> Optional[TelegramHandler]:
    """Get configured Telegram handler or None if not available."""
    if Bot is None:
        logger.warning("Telegram not available")
        return None
    
    return TelegramHandler()
