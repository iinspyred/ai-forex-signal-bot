import asyncio
import logging
from datetime import datetime, timezone
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import Settings
from app.models import ScannerState, Signal
from app.services.database import SignalDatabase

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, settings: Settings, database: SignalDatabase) -> None:
        self.settings = settings
        self.database = database
        self.application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        self._scanner_state: ScannerState | None = None
        self._started = False
        self._register_handlers()

    def set_scanner_state(self, state: ScannerState) -> None:
        self._scanner_state = state

    async def start(self) -> None:
        if self._started:
            return
        await self.application.initialize()
        if self.settings.TELEGRAM_WEBHOOK_URL:
            await self.application.bot.set_webhook(self.settings.TELEGRAM_WEBHOOK_URL)
            logger.info("Telegram webhook configured at %s", self.settings.TELEGRAM_WEBHOOK_URL)
        else:
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram polling started")
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        if not self.settings.TELEGRAM_WEBHOOK_URL and self.application.updater.running:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self._started = False

    async def process_webhook_update(self, payload: dict) -> None:
        update = Update.de_json(payload, self.application.bot)
        await self.application.process_update(update)

    async def send_startup(self) -> None:
        await self.send_message("🤖 AI Forex Signal Bot started.")

    async def send_heartbeat(self) -> None:
        state = self._scanner_state or ScannerState()
        await self.send_message(
            "💓 Heartbeat\n"
            f"⚙️ Running: {state.running}\n"
            f"🕒 Last scan: {state.last_scan_at.isoformat() if state.last_scan_at else 'never'}\n"
            f"📡 Signals: {state.generated_signals}"
        )

    async def send_error(self, message: str) -> None:
        await self.send_message(f"🚨 Error alert\n{escape(message)}")

    async def send_signal(self, signal: Signal) -> None:
        icon = "🚀🟢 BUY SIGNAL" if signal.direction.value == "BUY" else "🔻🔴 SELL SIGNAL"
        trend_icon = "📈" if signal.trend == "Bullish" else "📉" if signal.trend == "Bearish" else "➡️"
        text = (
            f"<b>{icon}</b>\n\n"
            f"💱 Pair: <b>{escape(signal.pair)}</b>\n"
            f"⏱️ Timeframe: {escape(signal.timeframe)}\n"
            f"🎯 Entry: <code>{signal.entry}</code>\n"
            f"🛑 Stop Loss: <code>{signal.stop_loss}</code>\n"
            f"💰 Take Profit: <code>{signal.take_profit}</code>\n"
            f"🧲 Trailing Stop: <code>{signal.trailing_stop}</code>\n"
            f"⚖️ Risk/Reward: 1:{signal.risk_reward:g}\n"
            f"🧯 Account Risk: {signal.risk_percent:g}%\n"
            f"📊 RSI: {signal.rsi}\n"
            f"{trend_icon} Trend: {escape(signal.trend)}\n"
            f"🔥 Confidence: {signal.confidence:.0%}\n\n"
            f"🧠 Strategy:\n{escape(signal.strategy)}\n\n"
            f"🕒 Timestamp: {signal.timestamp.astimezone(timezone.utc).isoformat()}"
        )
        await self.send_message(text, parse_mode=ParseMode.HTML)

    async def send_message(self, text: str, parse_mode: str | None = None) -> None:
        if not self.settings.TELEGRAM_CHAT_ID:
            logger.info("Telegram chat id not configured; skipped message: %s", text)
            return
        try:
            await self.application.bot.send_message(
                chat_id=self.settings.TELEGRAM_CHAT_ID,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
        except Exception as exc:  # noqa: BLE001 - Telegram failures should not crash scanner.
            logger.exception("Telegram send failed: %s", exc)

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        await update.message.reply_text(
            "AI Forex Signal Bot is online.\n"
            f"Your chat id is: {chat_id}\n"
            "Commands: /help /status /signals /stats"
        )

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        await update.message.reply_text(
            "/start - show chat id\n"
            "📡 /status - scanner status\n"
            "📈 /signals - latest signals\n"
            "📊 /stats - signal counts"
        )

    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        state = self._scanner_state or ScannerState()
        await update.message.reply_text(
            "📡 Scanner status\n"
            f"⚙️ Running: {state.running}\n"
            f"🕒 Last scan: {state.last_scan_at.isoformat() if state.last_scan_at else 'never'}\n"
            f"🚨 Last error: {state.last_error or 'none'}"
        )

    async def _signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        signals = await self.database.recent_signals(limit=5)
        if not signals:
            await update.message.reply_text("📭 No signals recorded yet.")
            return
        lines = ["📈 Latest signals"]
        for signal in signals:
            direction_icon = "🚀🟢" if signal["direction"] == "BUY" else "🔻🔴"
            lines.append(
                f"{direction_icon} {signal['direction']} {signal['pair']} {signal['timeframe']} "
                f"@ {signal['entry']} | SL {signal['stop_loss']} | TP {signal['take_profit']}"
            )
        await update.message.reply_text("\n".join(lines))

    async def _stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        stats = await self.database.stats()
        await update.message.reply_text(
            "📊 Stats\n"
            f"📡 Total: {stats['total_signals']}\n"
            f"🚀🟢 BUY: {stats['buy_signals']}\n"
            f"🔻🔴 SELL: {stats['sell_signals']}\n"
            "🏆 Wins: 0\n"
            "❌ Losses: 0\n"
            "⚖️ Win/loss tracking activates after exit rules are configured"
        )

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("status", self._status_command))
        self.application.add_handler(CommandHandler("signals", self._signals_command))
        self.application.add_handler(CommandHandler("stats", self._stats_command))


async def hourly_heartbeat(service: TelegramService, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await service.send_heartbeat()
