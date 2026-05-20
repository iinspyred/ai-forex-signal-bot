import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.models import Signal


class SignalDatabase:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
        self.path = Path(database_url.replace("sqlite:///", "", 1))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._initialized = False

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pair TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        entry REAL NOT NULL,
                        rsi REAL NOT NULL,
                        trend TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT NOT NULL
                    )
                    """
                )
            self._initialized = True

    async def save_signal(self, signal: Signal) -> None:
        await self.initialize()
        async with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO signals (
                        pair, timeframe, direction, entry, rsi, trend, strategy,
                        confidence, timestamp, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.pair,
                        signal.timeframe,
                        signal.direction.value,
                        signal.entry,
                        signal.rsi,
                        signal.trend,
                        signal.strategy,
                        signal.confidence,
                        signal.timestamp.isoformat(),
                        json.dumps(signal.metadata),
                    ),
                )

    async def recent_signals(self, limit: int = 50) -> list[dict]:
        await self.initialize()
        async with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def stats(self) -> dict:
        await self.initialize()
        async with self._lock:
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) AS count FROM signals").fetchone()["count"]
                buy = conn.execute(
                    "SELECT COUNT(*) AS count FROM signals WHERE direction = 'BUY'"
                ).fetchone()["count"]
                sell = conn.execute(
                    "SELECT COUNT(*) AS count FROM signals WHERE direction = 'SELL'"
                ).fetchone()["count"]
        return {
            "total_signals": total,
            "buy_signals": buy,
            "sell_signals": sell,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["metadata"] = json.loads(item["metadata"])
        return item
