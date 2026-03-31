import os
import tempfile
import unittest
from unittest.mock import AsyncMock

from terraria_wiki.models import LookupResult, WikiArticle
from terraria_wiki.persistent_cache import PersistentLookupCache
from terraria_wiki.config import STRUCTURED_SCHEMA_VERSION


class PersistentLookupCacheTests(unittest.TestCase):
    def test_persistent_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "cache.sqlite3")
            cache = PersistentLookupCache(path, ttl_seconds=60, namespace=STRUCTURED_SCHEMA_VERSION)
            value = LookupResult(article=WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"), exact_match=True)
            cache.set("terraria", value)
            loaded = cache.get("terraria")
            cache.close()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.article.title, "泰拉瑞亚")
        self.assertTrue(loaded.exact_match)


if __name__ == "__main__":
    unittest.main()
