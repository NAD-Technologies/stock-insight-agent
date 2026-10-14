"""Tiny in-memory TTL cache + retry-with-backoff helper."""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger("cache")
_store: dict[tuple, tuple[float, Any]] = {}


def _k(v):
    """Hashable cache-key part; pandas objects are keyed by shape and last index/value."""
    if hasattr(v, "index") and hasattr(v, "shape"):
        try:
            return (type(v).__name__, v.shape, str(v.index[-1]) if len(v) else "")
        except Exception:  # noqa: BLE001
            return (type(v).__name__, v.shape)
    return v


def ttl_cache(ttl: float):
    """Cache async function results by (name, args) for `ttl` seconds. Errors are not cached."""
    def deco(fn: Callable[..., Awaitable[Any]]):
        @functools.wraps(fn)
        async def wrapper(*args, **kw):
            key = (fn.__qualname__, tuple(_k(a) for a in args), tuple(sorted((k, _k(v)) for k, v in kw.items())))
            hit = _store.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            val = await fn(*args, **kw)
            _store[key] = (time.monotonic(), val)
            return val
        return wrapper
    return deco


def clear():
    _store.clear()


async def with_backoff(fn: Callable[[], Any], attempts: int = 3, base: float = 0.8):
    """Run blocking `fn` in a thread; retry on exceptions with exponential backoff."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await asyncio.to_thread(fn)
        except Exception as e:  # noqa: BLE001 - provider libs raise assorted types
            last = e
            msg = str(e).lower()
            if "not found" in msg or "delisted" in msg:
                break
            await asyncio.sleep(base * (2 ** i))
    raise last  # type: ignore[misc]
