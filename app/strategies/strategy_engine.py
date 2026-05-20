from datetime import datetime, timedelta, timezone

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange

from app.models import AIPrediction, Candle, Signal, SignalDirection


class StrategyEngine:
    def __init__(self, cooldown_minutes: int) -> None:
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._last_signals: dict[tuple[str, str, SignalDirection], datetime] = {}

    def analyze(self, pair: str, timeframe: str, candles: list[Candle]) -> Signal | None:
        if len(candles) < 60:
            return None

        frame = self._to_frame(candles)
        enriched = self._with_indicators(frame).dropna()
        if len(enriched) < 3:
            return None

        previous = enriched.iloc[-2]
        current = enriched.iloc[-1]

        trend = self._trend(current)
        volatility_ok = self._volatility_ok(current)
        volume_ok = self._volume_ok(enriched)
        ai_prediction = self._ai_prediction_placeholder(pair, timeframe, current)

        buy_conditions = {
            "RSI oversold": current["rsi"] < 30,
            "EMA bullish crossover": previous["ema20"] <= previous["ema50"]
            and current["ema20"] > current["ema50"],
            "MACD bullish crossover": previous["macd"] <= previous["macd_signal"]
            and current["macd"] > current["macd_signal"],
            "Trend bullish": trend == "Bullish",
            "Volatility acceptable": volatility_ok,
            "Volume confirmed": volume_ok,
        }
        sell_conditions = {
            "RSI overbought": current["rsi"] > 70,
            "EMA bearish crossover": previous["ema20"] >= previous["ema50"]
            and current["ema20"] < current["ema50"],
            "MACD bearish crossover": previous["macd"] >= previous["macd_signal"]
            and current["macd"] < current["macd_signal"],
            "Trend bearish": trend == "Bearish",
            "Volatility acceptable": volatility_ok,
            "Volume confirmed": volume_ok,
        }

        if self._is_actionable(buy_conditions):
            return self._build_signal(
                pair,
                timeframe,
                SignalDirection.BUY,
                current,
                trend,
                buy_conditions,
                ai_prediction,
            )
        if self._is_actionable(sell_conditions):
            return self._build_signal(
                pair,
                timeframe,
                SignalDirection.SELL,
                current,
                trend,
                sell_conditions,
                ai_prediction,
            )
        return None

    def _build_signal(
        self,
        pair: str,
        timeframe: str,
        direction: SignalDirection,
        current: pd.Series,
        trend: str,
        conditions: dict[str, bool],
        ai_prediction: AIPrediction,
    ) -> Signal | None:
        if self._is_duplicate(pair, timeframe, direction):
            return None

        serializable_conditions = {
            name: bool(value) for name, value in conditions.items()
        }
        confidence = sum(serializable_conditions.values()) / len(serializable_conditions)
        now = datetime.now(timezone.utc)
        self._last_signals[(pair, timeframe, direction)] = now

        return Signal(
            pair=pair,
            timeframe=timeframe,
            direction=direction,
            entry=round(float(current["close"]), 5),
            rsi=round(float(current["rsi"]), 2),
            trend=trend,
            strategy="EMA crossover + RSI + MACD + trend/volatility filters",
            confidence=round(confidence, 2),
            timestamp=now,
            metadata={
                "conditions": serializable_conditions,
                "macd": round(float(current["macd"]), 6),
                "macd_signal": round(float(current["macd_signal"]), 6),
                "ema20": round(float(current["ema20"]), 6),
                "ema50": round(float(current["ema50"]), 6),
                "atr_percent": round(float(current["atr_percent"]), 4),
                "ai_prediction": ai_prediction.model_dump(),
            },
        )

    def _is_duplicate(self, pair: str, timeframe: str, direction: SignalDirection) -> bool:
        last = self._last_signals.get((pair, timeframe, direction))
        return last is not None and datetime.now(timezone.utc) - last < self.cooldown

    @staticmethod
    def _to_frame(candles: list[Candle]) -> pd.DataFrame:
        return pd.DataFrame([candle.model_dump() for candle in candles])

    @staticmethod
    def _with_indicators(frame: pd.DataFrame) -> pd.DataFrame:
        enriched = frame.copy()
        enriched["rsi"] = RSIIndicator(enriched["close"], window=14).rsi()
        enriched["ema20"] = EMAIndicator(enriched["close"], window=20).ema_indicator()
        enriched["ema50"] = EMAIndicator(enriched["close"], window=50).ema_indicator()
        macd = MACD(enriched["close"])
        enriched["macd"] = macd.macd()
        enriched["macd_signal"] = macd.macd_signal()
        atr = AverageTrueRange(enriched["high"], enriched["low"], enriched["close"], window=14)
        enriched["atr"] = atr.average_true_range()
        enriched["atr_percent"] = (enriched["atr"] / enriched["close"]) * 100
        return enriched

    @staticmethod
    def _trend(row: pd.Series) -> str:
        if row["ema20"] > row["ema50"] and row["close"] > row["ema20"]:
            return "Bullish"
        if row["ema20"] < row["ema50"] and row["close"] < row["ema20"]:
            return "Bearish"
        return "Neutral"

    @staticmethod
    def _volatility_ok(row: pd.Series) -> bool:
        return 0.01 <= float(row["atr_percent"]) <= 1.5

    @staticmethod
    def _volume_ok(frame: pd.DataFrame) -> bool:
        if not frame["volume"].any():
            return True
        recent = float(frame.iloc[-1]["volume"])
        average = float(frame["volume"].tail(20).mean())
        return recent >= average * 0.75

    @staticmethod
    def _is_actionable(conditions: dict[str, bool]) -> bool:
        return all(
            conditions[name]
            for name in (
                "Volatility acceptable",
                "Volume confirmed",
            )
        ) and sum(conditions.values()) >= 5

    @staticmethod
    def _ai_prediction_placeholder(pair: str, timeframe: str, row: pd.Series) -> AIPrediction:
        return AIPrediction(
            label="neutral",
            confidence=0.0,
            rationale=(
                f"No AI model is connected. Technical indicators only for {pair} {timeframe}; "
                f"last close {float(row['close']):.5f}."
            ),
        )
