import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level.upper())
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(log_level.upper())

    app_file = RotatingFileHandler(
        Path(log_dir) / "app.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    app_file.setFormatter(formatter)
    app_file.setLevel(log_level.upper())

    trade_file = RotatingFileHandler(
        Path(log_dir) / "trades.log",
        maxBytes=1_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    trade_file.setFormatter(formatter)
    trade_file.setLevel(logging.INFO)

    root.addHandler(console)
    root.addHandler(app_file)

    trade_logger = logging.getLogger("trade")
    trade_logger.setLevel(logging.INFO)
    trade_logger.addHandler(trade_file)
    trade_logger.propagate = True
