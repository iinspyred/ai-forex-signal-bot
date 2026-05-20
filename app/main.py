import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.api.routes import create_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import InMemoryRateLimiter
from app.services.database import SignalDatabase
from app.services.market_service import MarketService
from app.services.scanner import MarketScanner
from app.services.telegram_service import TelegramService, hourly_heartbeat
from app.strategies.strategy_engine import StrategyEngine

settings = get_settings()
configure_logging(settings.LOG_LEVEL, settings.LOG_DIR)
logger = logging.getLogger(__name__)
started_at = datetime.now(timezone.utc)

database = SignalDatabase(settings.DATABASE_URL)
market_service = MarketService(settings)
strategy_engine = StrategyEngine(
    cooldown_minutes=settings.SIGNAL_COOLDOWN_MINUTES,
    atr_stop_multiplier=settings.RISK_ATR_STOP_MULTIPLIER,
    risk_reward_ratio=settings.RISK_REWARD_RATIO,
    trailing_stop_atr_multiplier=settings.TRAILING_STOP_ATR_MULTIPLIER,
    account_risk_percent=settings.ACCOUNT_RISK_PERCENT,
)
telegram_service = TelegramService(settings, database)
scanner = MarketScanner(settings, market_service, strategy_engine, telegram_service, database)
rate_limiter = InMemoryRateLimiter(
    settings.RATE_LIMIT_REQUESTS,
    settings.RATE_LIMIT_WINDOW_SECONDS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.initialize()
    await telegram_service.start()
    await telegram_service.send_startup()

    scanner_task = asyncio.create_task(scanner.run_forever(), name="market-scanner")
    heartbeat_task = asyncio.create_task(
        hourly_heartbeat(telegram_service, settings.HEARTBEAT_INTERVAL_SECONDS),
        name="telegram-heartbeat",
    )
    app.state.tasks = [scanner_task, heartbeat_task]

    try:
        yield
    finally:
        for task in app.state.tasks:
            task.cancel()
        await asyncio.gather(*app.state.tasks, return_exceptions=True)
        await telegram_service.stop()
        await market_service.close()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)
app.include_router(
    create_router(
        settings=settings,
        database=database,
        scanner=scanner,
        telegram=telegram_service,
        started_at=started_at,
        rate_limiter=rate_limiter,
    )
)
