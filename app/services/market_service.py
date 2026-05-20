import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import Candle
from app.utils.retry import retry_async

logger = logging.getLogger(__name__)


class MarketDataRateLimitError(RuntimeError):
    """Raised when an upstream data provider reports quota exhaustion."""


class MarketService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS)
        self._request_lock = asyncio.Lock()
        self._last_market_request_at = 0.0

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_candles(self, pair: str, timeframe: str) -> list[Candle]:
        provider = self.settings.MARKET_DATA_PROVIDER.lower().strip()
        if provider == "alphavantage":
            return await self._fetch_alphavantage_candles(pair, timeframe)
        return await self._fetch_twelvedata_candles(pair, timeframe)

    async def _fetch_twelvedata_candles(self, pair: str, timeframe: str) -> list[Candle]:
        async def request() -> list[Candle]:
            await self._throttle_market_request()
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
                message = payload.get("message", "TwelveData returned an error")
                if "credits" in message.lower() or "limit" in message.lower():
                    raise MarketDataRateLimitError(message)
                raise RuntimeError(message)
            values = payload.get("values") or []
            candles = [self._parse_twelvedata_candle(item) for item in values]
            return sorted(candles, key=lambda candle: candle.timestamp)

        return await retry_async(
            request,
            attempts=1,
            operation_name=f"fetch candles {pair} {timeframe}",
        )

    async def _fetch_alphavantage_candles(self, pair: str, timeframe: str) -> list[Candle]:
        if not self.settings.ALPHAVANTAGE_API_KEY:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is required when MARKET_DATA_PROVIDER=alphavantage")

        from_symbol, to_symbol = pair.split("/")
        interval = self._to_alphavantage_interval(timeframe)

        async def request() -> list[Candle]:
            await self._throttle_market_request()
            response = await self.client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "FX_INTRADAY",
                    "from_symbol": from_symbol,
                    "to_symbol": to_symbol,
                    "interval": interval,
                    "outputsize": "compact",
                    "apikey": self.settings.ALPHAVANTAGE_API_KEY,
                },
            )
            response.raise_for_status()
            payload = response.json()
            note = payload.get("Note") or payload.get("Information")
            if note:
                raise MarketDataRateLimitError(note)
            error = payload.get("Error Message")
            if error:
                raise RuntimeError(error)

            series_key = f"Time Series FX ({interval})"
            values = payload.get(series_key)
            if not values:
                raise RuntimeError("Alpha Vantage returned no FX intraday candles")

            candles = [
                self._parse_alphavantage_candle(timestamp, item)
                for timestamp, item in values.items()
            ]
            return sorted(candles, key=lambda candle: candle.timestamp)[-self.settings.CANDLE_LIMIT :]

        return await retry_async(
            request,
            attempts=1,
            operation_name=f"fetch Alpha Vantage candles {pair} {timeframe}",
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

    @staticmethod
    def _parse_alphavantage_candle(timestamp: str, item: dict[str, Any]) -> Candle:
        parsed = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
        return Candle(
            timestamp=parsed,
            open=float(item["1. open"]),
            high=float(item["2. high"]),
            low=float(item["3. low"]),
            close=float(item["4. close"]),
            volume=0.0,
        )

    @staticmethod
    def _to_alphavantage_interval(timeframe: str) -> str:
        mapping = {"1min": "1min", "5min": "5min", "15min": "15min", "30min": "30min", "60min": "60min"}
        if timeframe not in mapping:
            raise ValueError(f"Unsupported Alpha Vantage timeframe: {timeframe}")
        return mapping[timeframe]

    async def _throttle_market_request(self) -> None:
        async with self._request_lock:
            now = asyncio.get_running_loop().time()
            elapsed = now - self._last_market_request_at
            wait_seconds = self.settings.MARKET_DATA_MIN_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_market_request_at = asyncio.get_running_loop().time()
