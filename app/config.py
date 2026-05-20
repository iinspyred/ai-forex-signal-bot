from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded only from environment variables or .env locally."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "AI Forex Signal Bot"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    TWELVEDATA_API_KEY: str = Field(..., min_length=1)
    FINNHUB_API_KEY: str = Field(..., min_length=1)
    ALPHAVANTAGE_API_KEY: str = ""
    MARKET_DATA_PROVIDER: str = "twelvedata"
    TELEGRAM_BOT_TOKEN: str = Field(..., min_length=1)
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""

    DATABASE_URL: str = "sqlite:///./data/signals.db"
    SCAN_INTERVAL_SECONDS: int = Field(default=60, ge=15, le=900)
    SIGNAL_COOLDOWN_MINUTES: int = Field(default=30, ge=1, le=1440)
    HEARTBEAT_INTERVAL_SECONDS: int = Field(default=3600, ge=300, le=86400)
    REQUEST_TIMEOUT_SECONDS: float = Field(default=12.0, ge=1.0, le=60.0)
    MARKET_DATA_MIN_INTERVAL_SECONDS: float = Field(default=8.0, ge=0.0, le=120.0)
    RATE_LIMIT_REQUESTS: int = Field(default=60, ge=1)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    RISK_ATR_STOP_MULTIPLIER: float = Field(default=1.5, ge=0.1, le=10.0)
    RISK_REWARD_RATIO: float = Field(default=2.0, ge=0.1, le=10.0)
    TRAILING_STOP_ATR_MULTIPLIER: float = Field(default=1.0, ge=0.1, le=10.0)
    ACCOUNT_RISK_PERCENT: float = Field(default=1.0, ge=0.1, le=10.0)

    MARKET_PAIRS: str = "EUR/USD,GBP/USD,USD/JPY,AUD/USD"
    TIMEFRAMES: str = "1min,5min"
    CANDLE_LIMIT: int = Field(default=120, ge=60, le=500)

    @property
    def market_pairs(self) -> list[str]:
        return [item.strip() for item in self.MARKET_PAIRS.split(",") if item.strip()]

    @property
    def timeframes(self) -> list[str]:
        return [item.strip() for item in self.TIMEFRAMES.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
