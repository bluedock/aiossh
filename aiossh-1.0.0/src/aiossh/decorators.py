"""
Utility Decorators - v2.0

Provides retry logic with exponential backoff, session connectivity
verification, and performance timing measurement.
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

from .exceptions import AIOSSHSessionExpiredError

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator to retry an async function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (0 = no retries).
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for delay after each retry.
        exceptions: Tuple of exception types to catch and retry.

    Returns:
        Decorated async function with retry logic.

    Raises:
        ValueError: If parameters are invalid.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if delay <= 0:
        raise ValueError("delay must be positive")
    if backoff < 1.0:
        raise ValueError("backoff must be >= 1.0")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            remaining = max_retries + 1  # +1 for initial attempt
            current_delay = delay

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    remaining -= 1
                    if remaining <= 0:
                        raise
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        return wrapper  # type: ignore[return-value]

    return decorator


def require_session(func: F) -> F:
    """Decorator to verify session connectivity before execution.

    Must be used on methods of classes with an `is_connected` property.

    Args:
        func: The async method to protect.

    Returns:
        Decorated method that checks session connectivity.

    Raises:
        AIOSSHSessionExpiredError: If the session is not connected.
    """

    @functools.wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not self.is_connected:
            raise AIOSSHSessionExpiredError(
                "Session is not connected",
                code="SESSION_NOT_CONNECTED",
            )
        return await func(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def timing(func: F) -> F:
    """Decorator to measure and log async function execution time.

    Args:
        func: The async function to time.

    Returns:
        Decorated function that prints execution time.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"[TIMING] {func.__name__} completed in {elapsed:.4f}s")
        return result

    return wrapper  # type: ignore[return-value]