from app.models import Candle, Signal
from app.strategies.strategy_engine import StrategyEngine


class Backtester:
    def __init__(self, engine: StrategyEngine) -> None:
        self.engine = engine

    def run(self, pair: str, timeframe: str, candles: list[Candle]) -> dict:
        signals: list[Signal] = []
        for index in range(60, len(candles) + 1):
            signal = self.engine.analyze(pair, timeframe, candles[:index])
            if signal:
                signals.append(signal)

        return {
            "pair": pair,
            "timeframe": timeframe,
            "candles": len(candles),
            "signals": [signal.model_dump(mode="json") for signal in signals],
            "wins": 0,
            "losses": 0,
            "note": "Win/loss scoring requires a take-profit/stop-loss policy.",
        }
