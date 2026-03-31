import json
import sqlite3
import time
import zlib
from dataclasses import asdict
from typing import Optional

from .models import LookupResult


class PersistentLookupCache:
    def __init__(self, path: str, ttl_seconds: int, namespace: str = ""):
        self._path = path
        self._ttl_seconds = ttl_seconds
        self._namespace = namespace.strip()
        self._connection = sqlite3.connect(path)
        self._pending_writes = 0
        self._commit_interval = 8
        self._write_cycles = 0
        self._cleanup_interval = 32
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA temp_store=MEMORY")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lookup_cache (
                cache_key TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_lookup_cache_expires_at ON lookup_cache(expires_at)"
        )
        self._connection.commit()

    def _namespaced_key(self, key: str) -> str:
        return f"{self._namespace}:{key}" if self._namespace else key

    def _commit_if_needed(self, force: bool = False) -> None:
        if force or self._pending_writes >= self._commit_interval:
            self._connection.commit()
            self._pending_writes = 0

    def _note_write(self) -> None:
        self._pending_writes += 1
        self._commit_if_needed()

    def _cleanup_expired(self) -> None:
        cursor = self._connection.execute(
            "DELETE FROM lookup_cache WHERE expires_at <= ?",
            (time.time(),),
        )
        if (cursor.rowcount or 0) > 0:
            self._note_write()

    def _deserialize_payload(self, payload: str | bytes | memoryview) -> LookupResult:
        if isinstance(payload, memoryview):
            payload = payload.tobytes()

        if isinstance(payload, bytes):
            try:
                text = zlib.decompress(payload).decode("utf-8")
            except zlib.error:
                text = payload.decode("utf-8")
        else:
            text = payload

        return LookupResult.from_dict(json.loads(text))

    def get(self, key: str) -> Optional[LookupResult]:
        namespaced_key = self._namespaced_key(key)
        row = self._connection.execute(
            "SELECT payload FROM lookup_cache WHERE cache_key = ? AND expires_at > ?",
            (namespaced_key, time.time()),
        ).fetchone()
        if row is None:
            return None

        (payload,) = row
        return self._deserialize_payload(payload)

    def set(self, key: str, value: LookupResult) -> None:
        serialized = json.dumps(asdict(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload = sqlite3.Binary(zlib.compress(serialized))
        expires_at = time.time() + self._ttl_seconds
        self._connection.execute(
            "REPLACE INTO lookup_cache(cache_key, payload, expires_at) VALUES (?, ?, ?)",
            (self._namespaced_key(key), payload, expires_at),
        )
        self._note_write()
        self._write_cycles += 1
        if self._write_cycles % self._cleanup_interval == 0:
            self._cleanup_expired()

    def clear(self) -> None:
        if self._namespace:
            like_prefix = f"{self._namespace}:%"
            self._connection.execute("DELETE FROM lookup_cache WHERE cache_key LIKE ?", (like_prefix,))
        else:
            self._connection.execute("DELETE FROM lookup_cache")
        self._connection.commit()
        self._pending_writes = 0

    def close(self) -> None:
        self._commit_if_needed(force=True)
        self._connection.close()
