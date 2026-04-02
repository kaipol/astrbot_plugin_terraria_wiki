import asyncio
import base64
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def install_fake_astrbot_modules():
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")

    class DummyLogger:
        def error(self, *args, **kwargs):
            return None

    class DummyFilter:
        def __init__(self):
            self.registered_llm_tools = []

        def command(self, _name, alias=None):
            def decorator(func):
                return func

            return decorator

        def llm_tool(self, name=None, **_kwargs):
            def decorator(func):
                func.__llm_tool_name__ = name or func.__name__
                self.registered_llm_tools.append(func.__llm_tool_name__)
                return func

            return decorator

    class DummyStar:
        def __init__(self, context):
            self.context = context

    class DummyContext:
        def __init__(self):
            self.added_tools = []
            self.provider_manager = types.SimpleNamespace(llm_tools=types.SimpleNamespace(func_list=[]))

        def add_llm_tools(self, *tools):
            self.added_tools.extend(tools)

    class DummyAstrMessageEvent:
        pass

    def register(*_args, **_kwargs):
        def decorator(cls):
            return cls

        return decorator

    api_module.logger = DummyLogger()
    event_module.filter = DummyFilter()
    event_module.AstrMessageEvent = DummyAstrMessageEvent
    star_module.Context = DummyContext
    star_module.Star = DummyStar
    star_module.register = register

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module


def install_fake_aiohttp_module():
    aiohttp_module = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientConnectionError(ClientError):
        pass

    class ClientResponseError(ClientError):
        def __init__(self, request_info=None, history=(), *, status=0, message="", headers=None):
            super().__init__(message)
            self.status = status
            self.message = message
            self.headers = headers
            self.request_info = request_info
            self.history = history

    class ClientTimeout:
        def __init__(self, total=None):
            self.total = total

    class ClientSession:
        def __init__(self, *args, **kwargs):
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.closed = True

        async def close(self):
            self.closed = True

    aiohttp_module.ClientError = ClientError
    aiohttp_module.ClientConnectionError = ClientConnectionError
    aiohttp_module.ClientResponseError = ClientResponseError
    aiohttp_module.ClientTimeout = ClientTimeout
    aiohttp_module.ClientSession = ClientSession

    sys.modules["aiohttp"] = aiohttp_module


install_fake_astrbot_modules()
try:
    import aiohttp  # type: ignore
except ImportError:
    install_fake_aiohttp_module()
    import aiohttp  # type: ignore

main_module = importlib.import_module("main")
plugin_module = importlib.import_module("terraria_wiki.plugin")
ranking_module = importlib.import_module("terraria_wiki.ranking")
rendering_module = importlib.import_module("terraria_wiki.rendering")
cache_module = importlib.import_module("terraria_wiki.cache")
models_module = importlib.import_module("terraria_wiki.models")


class FakeChain:
    def __init__(self):
        self.calls = []

    def base64_image(self, payload):
        self.calls.append(("base64_image", payload))
        return self

    def message(self, text):
        self.calls.append(("message", text))
        return self


class FakeEvent:
    def __init__(self, message_str):
        self.message_str = message_str
        self.chain = FakeChain()

    def plain_result(self, text):
        return ("plain", text)

    def make_result(self):
        return self.chain

    def chain_result(self, chain):
        return ("chain", chain.calls)


class RefactorPluginTests(unittest.IsolatedAsyncioTestCase):
    def make_instance(self):
        instance = plugin_module.TerrariaWikiPlugin(None)
        if instance._persistent_cache is not None:
            instance._persistent_cache.close()
            instance._persistent_cache = None
        return instance

    async def test_main_reexports_plugin_class(self):
        self.assertTrue(issubclass(main_module.TerrariaWikiPlugin, plugin_module.TerrariaWikiPlugin))

    async def test_plugin_registers_llm_tool_handler_when_available(self):
        context = plugin_module.Context()
        instance = main_module.TerrariaWikiPlugin(context)
        self.assertIn("terraria_wiki_lookup", main_module.filter.registered_llm_tools)
        self.assertEqual(context.added_tools, [])
        self.assertEqual(context.provider_manager.llm_tools.func_list, [])
        if instance._persistent_cache is not None:
            instance._persistent_cache.close()

    async def test_plugin_registers_ai_tool_via_add_llm_tools_when_llm_tool_decorator_unavailable(self):
        context = plugin_module.Context()
        original_llm_tool = plugin_module.filter.llm_tool
        instance = None
        plugin_module.filter.llm_tool = None
        try:
            instance = plugin_module.TerrariaWikiPlugin(context)
            self.assertEqual(len(context.added_tools), 1)
            self.assertIsInstance(context.added_tools[0], plugin_module.TerrariaWikiTool)
            self.assertIs(context.added_tools[0]._plugin, instance)
        finally:
            plugin_module.filter.llm_tool = original_llm_tool
            if instance is not None and instance._persistent_cache is not None:
                instance._persistent_cache.close()

    async def test_plugin_registers_ai_tool_via_legacy_tool_manager_when_llm_tool_decorator_unavailable(self):
        context = plugin_module.Context()
        context.add_llm_tools = None
        original_llm_tool = plugin_module.filter.llm_tool
        instance = None
        plugin_module.filter.llm_tool = None
        try:
            instance = plugin_module.TerrariaWikiPlugin(context)
            self.assertEqual(len(context.provider_manager.llm_tools.func_list), 1)
            self.assertIsInstance(context.provider_manager.llm_tools.func_list[0], plugin_module.TerrariaWikiTool)
            self.assertIs(context.provider_manager.llm_tools.func_list[0]._plugin, instance)
        finally:
            plugin_module.filter.llm_tool = original_llm_tool
            if instance is not None and instance._persistent_cache is not None:
                instance._persistent_cache.close()

    async def test_pick_best_result_prefers_exact_match(self):
        selection = ranking_module.pick_best_result(
            "泰拉棱镜",
            [
                {"title": "泰拉瑞亚"},
                {"title": "泰拉棱镜"},
                {"title": "泰拉闪耀靴"},
            ],
        )
        self.assertEqual(selection.title, "泰拉棱镜")
        self.assertTrue(selection.exact_match)
        self.assertEqual(selection.alternative_titles, ["泰拉瑞亚", "泰拉闪耀靴"])

    async def test_format_plain_text_truncates_and_shows_alternatives(self):
        result = models_module.LookupResult(
            article=models_module.WikiArticle(title="泰拉瑞亚", extract="测" * 500),
            alternative_titles=["泰拉棱镜", "泰拉闪耀靴"],
            exact_match=False,
        )
        text = rendering_module.format_plain_text(result)
        self.assertIn("【泰拉瑞亚】", text)
        self.assertIn("可能还想查：泰拉棱镜、泰拉闪耀靴", text)
        self.assertIn("……", text)

    async def test_lookup_uses_query_cache(self):
        instance = self.make_instance()
        expected = models_module.LookupResult(
            article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
            exact_match=True,
        )
        instance._query_cache.set("泰拉", expected)

        result = await instance._lookup_with_session(object(), "泰拉")
        self.assertIs(result, expected)

    async def test_lookup_uses_negative_cache(self):
        instance = self.make_instance()
        instance._negative_cache.set("不存在", True)

        result = await instance._lookup_with_session(object(), "不存在")
        self.assertIsNone(result)

    async def test_lookup_populates_cache_after_success(self):
        instance = self.make_instance()
        expected = models_module.LookupResult(
            article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
            exact_match=False,
        )

        fake_client = AsyncMock()
        fake_client.lookup.return_value = expected

        with patch.object(plugin_module, "WikiClient", return_value=fake_client):
            result = await instance._lookup_with_session(object(), "泰拉")

        self.assertIs(result, expected)
        self.assertIs(instance._query_cache.get("泰拉"), expected)

    async def test_lookup_records_negative_cache_after_miss(self):
        instance = self.make_instance()
        fake_client = AsyncMock()
        fake_client.lookup.return_value = None

        with patch.object(plugin_module, "WikiClient", return_value=fake_client):
            result = await instance._lookup_with_session(object(), "不存在")

        self.assertIsNone(result)
        self.assertTrue(instance._negative_cache.get("不存在"))

    async def test_build_success_response_prefers_chain_result(self):
        result = models_module.LookupResult(
            article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
            alternative_titles=["泰拉棱镜"],
            exact_match=False,
        )
        event = FakeEvent("泰拉")

        response = importlib.import_module("terraria_wiki.results").build_success_response(event, result)

        self.assertEqual(response[0], "chain")
        self.assertEqual(response[1][0][0], "base64_image")
        self.assertEqual(response[1][1][0], "message")

    async def test_render_card_base64_uses_image_icons_when_available(self):
        article = models_module.WikiArticle(
            title="铜短剑",
            extract="近战武器",
            recipes=[
                models_module.StructuredRecipe(
                    result="铜短剑",
                    amount="1",
                    station="铁砧",
                    ingredient_details=[
                        models_module.RecipeComponent(name="铜锭", amount="5", image_url="https://img/Copper_Bar.png")
                    ],
                    result_image_url="https://img/Copper_Shortsword.png",
                    station_image_url="https://img/Iron_Anvil.png",
                )
            ],
            used_in=[
                models_module.StructuredRecipe(
                    result="天顶剑",
                    amount="1",
                    station="秘银砧",
                    result_image_url="https://img/Zenith.png",
                )
            ],
        )
        with patch("terraria_wiki.results._image_data_uri", return_value="data:image/png;base64,AAA"):
            payload = importlib.import_module("terraria_wiki.results").render_card_base64(
                models_module.LookupResult(article=article, exact_match=True)
            )

        svg = base64.b64decode(payload).decode("utf-8")
        self.assertIn('<image href="data:image/png;base64,AAA"', svg)
        self.assertNotIn('>铜</text>', svg)
        self.assertNotIn("产出：", svg)

    async def test_svg_structured_card_wraps_long_summary_text(self):
        long_summary = "超长描述" * 80
        article = models_module.WikiArticle(
            title="泰拉刃",
            extract=long_summary,
            recipes=[
                models_module.StructuredRecipe(
                    result="泰拉刃",
                    amount="1",
                    station="秘银砧或山铜砧",
                    ingredient_details=[models_module.RecipeComponent(name="断裂英雄剑", amount="1")],
                )
            ],
        )

        payload = importlib.import_module("terraria_wiki.results").render_card_base64(
            models_module.LookupResult(article=article, exact_match=True)
        )
        svg = base64.b64decode(payload).decode("utf-8")

        self.assertIn("<tspan", svg)
        self.assertIn(long_summary[:20], svg)
        self.assertNotIn("……", svg)

    async def test_build_success_response_falls_back_to_plain_text(self):
        result = models_module.LookupResult(
            article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
            exact_match=True,
        )

        class PlainOnlyEvent:
            def plain_result(self, text):
                return ("plain", text)

        response = importlib.import_module("terraria_wiki.results").build_success_response(PlainOnlyEvent(), result)
        self.assertEqual(response[0], "plain")
        self.assertIn("【泰拉瑞亚】", response[1])

    async def test_wiki_command_handles_empty_input(self):
        instance = self.make_instance()
        event = FakeEvent("   ")
        results = []
        async for item in instance.wiki(event):
            results.append(item)
        self.assertEqual(results, [("plain", "请提供查询关键词，例如：/wiki 泰拉瑞亚")])

    async def test_ai_tool_handles_empty_input(self):
        instance = self.make_instance()
        tool = plugin_module.TerrariaWikiTool(instance)
        result = await tool.call(query="   ")
        self.assertEqual(result, "请提供查询关键词，例如：泰拉瑞亚")

    async def test_ai_tool_returns_plain_text_for_success(self):
        instance = self.make_instance()
        instance._lookup = AsyncMock(
            return_value=models_module.LookupResult(
                article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
                exact_match=True,
            )
        )
        tool = plugin_module.TerrariaWikiTool(instance)
        result = await tool.call(query="神圣锭")
        self.assertIn("【泰拉瑞亚】", result)

    async def test_lookup_plain_text_handles_timeout(self):
        instance = self.make_instance()
        instance._lookup = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await instance.lookup_plain_text("泰拉")
        self.assertEqual(result, "查询 Wiki 超时，请稍后重试。")

    async def test_wiki_command_accepts_parsed_query_argument(self):
        instance = self.make_instance()
        instance._lookup = AsyncMock(
            return_value=models_module.LookupResult(
                article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
                exact_match=True,
            )
        )
        event = FakeEvent("   ")
        results = []
        async for item in instance.wiki(event, "神圣锭"):
            results.append(item)
        instance._lookup.assert_awaited_once_with("神圣锭")
        self.assertEqual(results[0][0], "chain")

    async def test_wiki_command_handles_timeout(self):
        instance = self.make_instance()
        instance._lookup = AsyncMock(side_effect=asyncio.TimeoutError())
        event = FakeEvent("泰拉")
        results = []
        async for item in instance.wiki(event):
            results.append(item)
        self.assertEqual(results, [("plain", "查询 Wiki 超时，请稍后重试。")])

    async def test_wiki_command_returns_chain_response_for_success(self):
        instance = self.make_instance()
        instance._lookup = AsyncMock(
            return_value=models_module.LookupResult(
                article=models_module.WikiArticle(title="泰拉瑞亚", extract="沙盒游戏"),
                alternative_titles=["泰拉棱镜"],
                exact_match=False,
            )
        )
        event = FakeEvent("泰拉")
        results = []
        async for item in instance.wiki(event):
            results.append(item)
        self.assertEqual(results[0][0], "chain")

    async def test_prefetch_icon_data_uris_respects_max_icons(self):
        results_module = importlib.import_module("terraria_wiki.results")

        with patch("terraria_wiki.results._image_data_uri", return_value="data:image/png;base64,AAA") as mocked:
            warmed = results_module.prefetch_icon_data_uris(["u1", "u2", "u3"], 2)

        self.assertEqual(warmed, 2)
        self.assertEqual(mocked.call_count, 2)

    async def test_prefetch_common_icons_is_throttled(self):
        instance = self.make_instance()

        with (
            patch.object(plugin_module, "ICON_PREFETCH_FILES", ("Iron Anvil.png", "Lead Anvil.png")),
            patch.object(plugin_module, "ICON_PREFETCH_MAX_ICONS", 2),
            patch.object(plugin_module, "ICON_PREFETCH_INTERVAL_SECONDS", 60),
            patch.object(plugin_module.time, "monotonic", side_effect=[100.0, 100.0]),
            patch.object(plugin_module.asyncio, "to_thread", new=AsyncMock()) as mock_to_thread,
        ):
            await instance._prefetch_common_icons()
            await instance._prefetch_common_icons()

        self.assertEqual(mock_to_thread.await_count, 1)
        first_call_args = mock_to_thread.await_args.args
        self.assertIs(first_call_args[0], plugin_module.prefetch_icon_data_uris)
        self.assertEqual(first_call_args[2], 2)
        self.assertEqual(len(first_call_args[1]), 2)
        self.assertTrue(first_call_args[1][0].startswith("https://terraria.wiki.gg/zh/special:filepath/"))


if __name__ == "__main__":
    unittest.main()
