from datetime import datetime, timedelta, timezone

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange

from app.models import AIPrediction, Candle, Signal, SignalDirection


class StrategyEngine:
    def __init__(
        self,
        cooldown_minutes: int,
        min_confidence: float = 0.55,
        atr_stop_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
        trailing_stop_atr_multiplier: float = 1.0,
        account_risk_percent: float = 1.0,
    ) -> None:
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.min_confidence = min_confidence
        self.atr_stop_multiplier = atr_stop_multiplier
        self.risk_reward_ratio = risk_reward_ratio
        self.trailing_stop_atr_multiplier = trailing_stop_atr_multiplier
        self.account_risk_percent = account_risk_percent
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
            "RSI bullish zone": 30 <= current["rsi"] <= 60,
            "EMA trend bullish": current["ema20"] > current["ema50"],
            "Price above EMA20": current["close"] > current["ema20"],
            "MACD bullish bias": current["macd"] > current["macd_signal"],
            "MACD momentum improving": (current["macd"] - current["macd_signal"])
            > (previous["macd"] - previous["macd_signal"]),
            "Trend bullish": trend == "Bullish",
            "Volatility acceptable": volatility_ok,
            "Volume confirmed": volume_ok,
        }
        sell_conditions = {
            "RSI bearish zone": 40 <= current["rsi"] <= 70,
            "EMA trend bearish": current["ema20"] < current["ema50"],
            "Price below EMA20": current["close"] < current["ema20"],
            "MACD bearish bias": current["macd"] < current["macd_signal"],
            "MACD momentum weakening": (current["macd"] - current["macd_signal"])
            < (previous["macd"] - previous["macd_signal"]),
            "Trend bearish": trend == "Bearish",
            "Volatility acceptable": volatility_ok,
            "Volume confirmed": volume_ok,
        }

        if self._is_actionable(buy_conditions, self.min_confidence):
            return self._build_signal(
                pair,
                timeframe,
                SignalDirection.BUY,
                current,
                trend,
                buy_conditions,
                ai_prediction,
            )
        if self._is_actionable(sell_conditions, self.min_confidence):
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
        entry = float(current["close"])
        risk_plan = self._risk_plan(pair, direction, entry, float(current["atr"]))

        return Signal(
            pair=pair,
            timeframe=timeframe,
            direction=direction,
            entry=risk_plan["entry"],
            rsi=round(float(current["rsi"]), 2),
            trend=trend,
            strategy="Active confluence: EMA trend + RSI zone + MACD momentum + risk filters",
            confidence=round(confidence, 2),
            stop_loss=risk_plan["stop_loss"],
            take_profit=risk_plan["take_profit"],
            trailing_stop=risk_plan["trailing_stop"],
            risk_reward=self.risk_reward_ratio,
            risk_percent=self.account_risk_percent,
            timestamp=now,
            metadata={
                "conditions": serializable_conditions,
                "macd": round(float(current["macd"]), 6),
                "macd_signal": round(float(current["macd_signal"]), 6),
                "ema20": round(float(current["ema20"]), 6),
                "ema50": round(float(current["ema50"]), 6),
                "atr_percent": round(float(current["atr_percent"]), 4),
                "atr": risk_plan["atr"],
                "risk_distance": risk_plan["risk_distance"],
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
    def _is_actionable(conditions: dict[str, bool], min_confidence: float) -> bool:
        risk_filters_ok = all(
            conditions[name]
            for name in (
                "Volatility acceptable",
                "Volume confirmed",
            )
        )
        confidence = sum(bool(value) for value in conditions.values()) / len(conditions)
        return risk_filters_ok and confidence >= min_confidence

    def _risk_plan(
        self,
        pair: str,
        direction: SignalDirection,
        entry: float,
        atr: float,
    ) -> dict[str, float]:
        precision = self._price_precision(pair)
        safe_atr = max(atr, entry * 0.0001)
        risk_distance = safe_atr * self.atr_stop_multiplier
        trailing_distance = safe_atr * self.trailing_stop_atr_multiplier

        if direction == SignalDirection.BUY:
            stop_loss = entry - risk_distance
            take_profit = entry + (risk_distance * self.risk_reward_ratio)
            trailing_stop = entry - trailing_distance
        else:
            stop_loss = entry + risk_distance
            take_profit = entry - (risk_distance * self.risk_reward_ratio)
            trailing_stop = entry + trailing_distance

        return {
            "entry": round(entry, precision),
            "stop_loss": round(stop_loss, precision),
            "take_profit": round(take_profit, precision),
            "trailing_stop": round(trailing_stop, precision),
            "atr": round(safe_atr, precision),
            "risk_distance": round(risk_distance, precision),
        }

    @staticmethod
    def _price_precision(pair: str) -> int:
        return 3 if pair.endswith("/JPY") else 5

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
