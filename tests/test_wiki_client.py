import sys
import types
import unittest
from unittest.mock import AsyncMock

try:
    import aiohttp  # type: ignore
except ImportError:
    aiohttp_module = types.ModuleType("aiohttp")

    class ClientSession:
        pass

    aiohttp_module.ClientSession = ClientSession
    sys.modules["aiohttp"] = aiohttp_module

from terraria_wiki.models import StructuredRecipe, WikiArticle
from terraria_wiki.wiki_client import WikiClient


class WikiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_article_uses_page_cache(self):
        cached_article = WikiArticle(title="泰拉瑞亚", extract="沙盒游戏")

        class FakeCache:
            def __init__(self):
                self.cached = {"泰拉瑞亚": cached_article}

            def get(self, key):
                return self.cached.get(key)

            def set(self, key, value):
                self.cached[key] = value

        client = WikiClient(session=object(), page_cache=FakeCache())
        client.fetch_json = AsyncMock()

        article = await client.fetch_article("泰拉瑞亚")
        self.assertIs(article, cached_article)
        client.fetch_json.assert_not_called()

    async def test_fetch_article_prefers_parsed_html_summary(self):
        client = WikiClient(session=object())
        client.fetch_json = AsyncMock(
            side_effect=[
                {
                    "query": {
                        "pages": [
                            {
                                "pageid": 1,
                                "title": "生命水晶",
                                "length": 1234,
                                "canonicalurl": "https://terraria.wiki.gg/zh/wiki/%E7%94%9F%E5%91%BD%E6%B0%B4%E6%99%B6",
                                "categories": [],
                                "revisions": [
                                    {
                                        "slots": {
                                            "main": {
                                                "content": "'''生命水晶'''是一种{{tr|Life Crystal}}。"
                                            }
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                },
                {"parse": {"sections": []}},
                {
                    "parse": {
                        "text": "<div><p><b>生命水晶</b>是一种消耗品，使用后它会永久性地将玩家的最大生命值增加 20。</p></div>"
                    }
                },
                {"cargoquery": []},
            ]
        )

        article = await client.fetch_article("生命水晶")

        self.assertEqual(article.extract, "生命水晶是一种消耗品，使用后它会永久性地将玩家的最大生命值增加 20。")

    async def test_fetch_structured_payload_normalizes_rows(self):
        client = WikiClient(session=object())
        responses = [
            {"cargoquery": [{"title": {"page": "铜短剑", "name": "Copper Shortsword", "itemid": "3507", "damage": "5", "stack": "1", "sell": "12", "imagefile": "Copper Shortsword.png"}}]},
            {
                "cargoquery": [
                    {"title": {"result": "Copper Shortsword", "resultid": "3507", "amount": "1", "station": "Iron Anvil", "ings": "¦Copper Bar¦7", "version": "old-gen 3ds", "legacy": "1", "result_page": "铜短剑", "result_imagefile": "Copper Shortsword.png"}},
                    {"title": {"result": "Copper Shortsword", "resultid": "3507", "amount": "1", "station": "Iron Anvil", "ings": "¦Copper Bar¦5", "version": "desktop console mobile", "legacy": "0", "result_page": "铜短剑", "result_imagefile": "Copper Shortsword.png"}},
                ]
            },
            {
                "cargoquery": [
                    {"title": {"result": "Zenith", "resultid": "4956", "amount": "1", "station": "Mythril Anvil", "ings": "¦Copper Shortsword¦1", "version": "", "legacy": "0", "result_page": "天顶剑", "result_imagefile": "Zenith.png"}}
                ]
            },
            {
                "cargoquery": [
                    {"title": {"name": "Copper Bar", "page": "铜锭", "imagefile": "Copper Bar.png"}},
                    {"title": {"name": "Iron Anvil", "page": "铁砧", "imagefile": "Iron Anvil.png"}},
                    {"title": {"name": "Copper Shortsword", "page": "铜短剑", "imagefile": "Copper Shortsword.png"}},
                    {"title": {"name": "Mythril Anvil", "page": "秘银砧", "imagefile": "Mythril Anvil.png"}},
                ]
            },
            {
                "query": {
                    "pages": [
                        {"title": "File:Copper Shortsword.png", "imageinfo": [{"url": "https://img/Copper_Shortsword.png"}]},
                        {"title": "File:Copper Bar.png", "imageinfo": [{"url": "https://img/Copper_Bar.png"}]},
                        {"title": "File:Iron Anvil.png", "imageinfo": [{"url": "https://img/Iron_Anvil.png"}]},
                        {"title": "File:Zenith.png", "imageinfo": [{"url": "https://img/Zenith.png"}]},
                        {"title": "File:Mythril Anvil.png", "imageinfo": [{"url": "https://img/Mythril_Anvil.png"}]},
                    ]
                }
            },
        ]
        client.fetch_json = AsyncMock(side_effect=responses)

        payload = await client.fetch_structured_payload("铜短剑", [])

        self.assertEqual(payload["entity_type"], "item")
        self.assertIn("伤害", payload["infobox_fields"])
        self.assertEqual(payload["recipes"][0].station, "铁砧")
        self.assertEqual(payload["recipes"][0].ingredients, ["铜锭5"])
        self.assertEqual(payload["recipes"][0].ingredient_details[0].name, "铜锭")
        self.assertEqual(payload["used_in"][0].result, "天顶剑")

    async def test_fetch_guide_sections_skips_wikitext_when_html_summary_available(self):
        class FakeGuideCache:
            def __init__(self):
                self.store = {}

            def get(self, key):
                return self.store.get(key)

            def set(self, key, value):
                self.store[key] = value

        client = WikiClient(session=object(), guide_cache=FakeGuideCache())
        client.fetch_parsed_html = AsyncMock(side_effect=[
            "<div><ul><li>第一段摘要，包含足够多的中文文本用于提取。</li></ul></div>",
            "<div><ul><li>第二段摘要，包含足够多的中文文本用于提取。</li></ul></div>",
        ])
        client.fetch_section_wikitext = AsyncMock()

        sections = await client.fetch_guide_sections(
            "血月",
            "https://terraria.wiki.gg/zh/wiki/%E8%A1%80%E6%9C%88",
            [
                {"index": "1", "line": "影响", "anchor": "影响", "toclevel": 1},
                {"index": "2", "line": "敌怪", "anchor": "敌怪", "toclevel": 1},
            ],
        )

        self.assertEqual(len(sections), 2)
        self.assertTrue(sections[0].summary.startswith("第一段摘要"))
        self.assertEqual(client.fetch_section_wikitext.await_count, 0)


if __name__ == "__main__":
    unittest.main()
