import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.75,
    operation_name: str = "operation",
) -> T:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:  # noqa: BLE001 - retry utility logs and re-raises final error.
            last_error = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s failed on attempt %s/%s: %s; retrying in %.2fs",
                operation_name,
                attempt,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error
