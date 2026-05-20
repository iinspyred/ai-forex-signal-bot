import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import Candle
from app.utils.retry import retry_async

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS)

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_candles(self, pair: str, timeframe: str) -> list[Candle]:
        async def request() -> list[Candle]:
            params = {
                "symbol": pair,
                "interval": timeframe,
                "outputsize": self.settings.CANDLE_LIMIT,
                "apikey": self.settings.TWELVEDATA_API_KEY,
                "format": "JSON",
            }
            response = await self.client.get("https://api.twelvedata.com/time_series", params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "error":
                raise RuntimeError(payload.get("message", "TwelveData returned an error"))
            values = payload.get("values") or []
            candles = [self._parse_twelvedata_candle(item) for item in values]
            return sorted(candles, key=lambda candle: candle.timestamp)

        return await retry_async(
            request,
            attempts=3,
            operation_name=f"fetch candles {pair} {timeframe}",
        )

    async def fetch_quote(self, pair: str) -> dict[str, Any]:
        symbol = f"OANDA:{pair.replace('/', '_')}"

        async def request() -> dict[str, Any]:
            response = await self.client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": self.settings.FINNHUB_API_KEY},
            )
            response.raise_for_status()
            return response.json()

        try:
            return await retry_async(request, attempts=2, operation_name=f"fetch quote {pair}")
        except Exception as exc:  # noqa: BLE001 - quote data is enrichment only.
            logger.warning("Finnhub quote unavailable for %s: %s", pair, exc)
            return {}

    @staticmethod
    def _parse_twelvedata_candle(item: dict[str, Any]) -> Candle:
        raw_time = item.get("datetime")
        timestamp = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
        return Candle(
            timestamp=timestamp,
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item.get("volume") or 0.0),
        )
