import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings
from app.models import ScannerState
from app.services.database import SignalDatabase
from app.services.market_service import MarketService
from app.services.market_service import MarketDataRateLimitError
from app.services.telegram_service import TelegramService
from app.strategies.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("trade")


class MarketScanner:
    def __init__(
        self,
        settings: Settings,
        market_service: MarketService,
        strategy_engine: StrategyEngine,
        telegram_service: TelegramService,
        database: SignalDatabase,
    ) -> None:
        self.settings = settings
        self.market_service = market_service
        self.strategy_engine = strategy_engine
        self.telegram_service = telegram_service
        self.database = database
        self.state = ScannerState()
        self.telegram_service.set_scanner_state(self.state)

    async def run_forever(self) -> None:
        self.state.running = True
        logger.info("Market scanner started")
        try:
            while True:
                scan_started_at = asyncio.get_running_loop().time()
                await self.scan_once()
                elapsed = asyncio.get_running_loop().time() - scan_started_at
                delay = max(5.0, self.settings.SCAN_INTERVAL_SECONDS - elapsed)
                await asyncio.sleep(delay)
        finally:
            self.state.running = False
            logger.info("Market scanner stopped")

    async def scan_once(self) -> None:
        self.state.last_scan_at = datetime.now(timezone.utc)
        self.state.scanned_pairs = 0
        for pair in self.settings.market_pairs:
            for timeframe in self.settings.timeframes:
                try:
                    candles = await self.market_service.fetch_candles(pair, timeframe)
                    quote = await self.market_service.fetch_quote(pair)
                    signal = self.strategy_engine.analyze(pair, timeframe, candles)
                    self.state.scanned_pairs += 1
                    if not signal:
                        continue
                    signal.metadata["quote"] = quote
                    await self.database.save_signal(signal)
                    await self.telegram_service.send_signal(signal)
                    self.state.generated_signals += 1
                    trade_logger.info("%s", signal.model_dump_json())
                except MarketDataRateLimitError as exc:
                    message = f"Market data rate limit for {pair} {timeframe}: {exc}"
                    self.state.last_error = message
                    logger.warning(message)
                    return
                except Exception as exc:  # noqa: BLE001 - one pair must not stop the scanner.
                    message = f"Scan failed for {pair} {timeframe}: {exc}"
                    self.state.last_error = message
                    logger.exception(message)
                    await self.telegram_service.send_error(message)
