import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from .models import CacheEntry

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int, max_entries: int, time_func: Callable[[], float] | None = None):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._time = time_func or time.monotonic
        self._store: dict[str, CacheEntry[T]] = {}
        self._ops = 0
        self._sweep_interval = max(16, min(64, max_entries // 2 if max_entries > 0 else 16))

    def get(self, key: str) -> T | None:
        now = self._time()
        entry = self._store.get(key)
        if entry is None:
            self._maybe_sweep(now)
            return None
        if entry.expires_at <= now:
            self._store.pop(key, None)
            self._maybe_sweep(now)
            return None
        self._maybe_sweep(now)
        return entry.value

    def set(self, key: str, value: T) -> None:
        now = self._time()
        self._store[key] = CacheEntry(value=value, expires_at=now + self.ttl_seconds)
        if len(self._store) > self.max_entries:
            self._prune_expired(now)
            self._prune_overflow()
        else:
            self._maybe_sweep(now)

    def clear(self) -> None:
        self._store.clear()

    def _maybe_sweep(self, now: float) -> None:
        self._ops += 1
        if self._ops % self._sweep_interval == 0:
            self._prune_expired(now)

    def _prune_expired(self, now: float | None = None) -> None:
        current = self._time() if now is None else now
        expired_keys = [key for key, entry in self._store.items() if entry.expires_at <= current]
        for key in expired_keys:
            self._store.pop(key, None)

    def _prune_overflow(self) -> None:
        while len(self._store) > self.max_entries:
            oldest_key = min(self._store.items(), key=lambda item: item[1].expires_at)[0]
            self._store.pop(oldest_key, None)


class InFlightRequestDeduper:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        existing_task = self._tasks.get(key)
        if existing_task is not None:
            return await existing_task

        task = asyncio.create_task(factory())
        self._tasks[key] = task
        try:
            return await task
        finally:
            if self._tasks.get(key) is task:
                self._tasks.pop(key, None)
