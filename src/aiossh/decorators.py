"""
Decorators - v1.1.0
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Callable, Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry(max_retries: int = 3, exceptions: tuple = (Exception,)):
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))
            raise last_exc
        return wrapper  # type: ignore
    return decorator


def timing(func: F) -> F:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        print(f"[TIMING] {func.__name__} took {duration:.3f}s")
        return result
    return wrapper  # type: ignore
