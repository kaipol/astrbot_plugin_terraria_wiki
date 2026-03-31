import asyncio
import unittest

from terraria_wiki.cache import InFlightRequestDeduper, TTLCache


class TTLCacheTests(unittest.TestCase):
    def test_cache_entry_expires(self):
        now = 0.0

        def fake_time():
            return now

        cache = TTLCache[str](ttl_seconds=10, max_entries=10, time_func=fake_time)
        cache.set("a", "value")
        self.assertEqual(cache.get("a"), "value")

        now = 11.0
        self.assertIsNone(cache.get("a"))


class InFlightDeduperTests(unittest.IsolatedAsyncioTestCase):
    async def test_deduper_reuses_same_task(self):
        deduper = InFlightRequestDeduper()
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return "done"

        result1, result2 = await asyncio.gather(
            deduper.run("same", factory),
            deduper.run("same", factory),
        )

        self.assertEqual(result1, "done")
        self.assertEqual(result2, "done")
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
