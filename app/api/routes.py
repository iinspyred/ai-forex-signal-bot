from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.config import Settings
from app.core.rate_limit import InMemoryRateLimiter, client_key
from app.services.database import SignalDatabase
from app.services.scanner import MarketScanner
from app.services.telegram_service import TelegramService


class TradingViewWebhook(BaseModel):
    pair: str = Field(min_length=3, max_length=20)
    timeframe: str = Field(min_length=1, max_length=10)
    action: str = Field(pattern="^(BUY|SELL|buy|sell)$")
    price: float = Field(gt=0)
    message: str = Field(default="", max_length=500)


def create_router(
    *,
    settings: Settings,
    database: SignalDatabase,
    scanner: MarketScanner,
    telegram: TelegramService,
    started_at: datetime,
    rate_limiter: InMemoryRateLimiter,
) -> APIRouter:
    router = APIRouter()

    def enforce_rate_limit(request: Request) -> None:
        rate_limiter.check(client_key(request))

    RateLimited = Annotated[None, Depends(enforce_rate_limit)]

    @router.get("/")
    async def root(_: RateLimited = None) -> dict:
        return {
            "name": settings.APP_NAME,
            "status": "online",
            "deployment": "Render",
            "active_pairs": settings.market_pairs,
            "timeframes": settings.timeframes,
        }

    @router.get("/health")
    async def health(_: RateLimited = None) -> dict:
        uptime = datetime.now(timezone.utc) - started_at
        return {
            "status": "healthy",
            "uptime_seconds": int(uptime.total_seconds()),
            "scanner": scanner.state.model_dump(mode="json"),
            "telegram_mode": "webhook" if settings.TELEGRAM_WEBHOOK_URL else "polling",
        }

    @router.get("/signals")
    async def signals(limit: int = 50, _: RateLimited = None) -> dict:
        safe_limit = min(max(limit, 1), 100)
        return {"signals": await database.recent_signals(limit=safe_limit)}

    @router.get("/stats")
    async def stats(_: RateLimited = None) -> dict:
        uptime = datetime.now(timezone.utc) - started_at
        db_stats = await database.stats()
        return {
            "uptime_seconds": int(uptime.total_seconds()),
            "active_pairs": settings.market_pairs,
            "timeframes": settings.timeframes,
            "scanner": scanner.state.model_dump(mode="json"),
            **db_stats,
        }

    @router.post("/telegram/webhook")
    async def telegram_webhook(payload: dict, _: RateLimited = None) -> dict:
        await telegram.process_webhook_update(payload)
        return {"ok": True}

    @router.post("/webhooks/tradingview")
    async def tradingview_webhook(payload: TradingViewWebhook, _: RateLimited = None) -> dict:
        await telegram.send_message(
            "TradingView alert\n"
            f"Pair: {payload.pair}\n"
            f"Timeframe: {payload.timeframe}\n"
            f"Action: {payload.action.upper()}\n"
            f"Price: {payload.price}\n"
            f"Message: {payload.message or 'none'}"
        )
        return {"ok": True, "received_at": datetime.now(timezone.utc).isoformat()}

    return router
