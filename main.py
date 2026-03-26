import aiohttp
from typing import Optional
from urllib.parse import quote

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

WIKI_API_URL = "https://terraria.wiki.gg/zh/api.php"
WIKI_BASE_URL = "https://terraria.wiki.gg/zh/wiki/"


@register("astrbot_plugin_terraria_wiki", "kaipol", "泰拉瑞亚中文 Wiki 查询插件", "1.0.0")
class TerrariaWikiPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """插件初始化，创建共享的 HTTP 会话。"""
        self._session = aiohttp.ClientSession()

    @filter.command("wiki")
    async def wiki(self, event: AstrMessageEvent):
        """查询泰拉瑞亚中文 Wiki。用法：/wiki <关键词>"""
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请提供查询关键词，例如：/wiki 泰拉瑞亚")
            return

        try:
            result = await self._search_wiki(query)
        except aiohttp.ClientResponseError as e:
            logger.error(f"[TerrariaWiki] HTTP 错误: {e.status} {e.message}")
            yield event.plain_result("查询 Wiki 时出错，请稍后重试。")
            return
        except Exception as e:
            logger.error(f"[TerrariaWiki] 查询失败: {e}")
            yield event.plain_result("查询失败，请稍后再试。")
            return

        if result is None:
            yield event.plain_result(f"未找到与「{query}」相关的内容。")
            return

        yield event.plain_result(result)

    async def _search_wiki(self, query: str) -> Optional[str]:
        """使用 MediaWiki API 搜索泰拉瑞亚中文 Wiki，返回格式化结果。"""
        session = self._session or aiohttp.ClientSession()
        # 第一步：搜索匹配的页面
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 1,
            "format": "json",
            "utf8": 1,
        }
        async with session.get(WIKI_API_URL, params=search_params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return None

        title = search_results[0]["title"]

        # 第二步：获取页面简介文本
        extract_params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "exsentences": 3,
            "format": "json",
            "utf8": 1,
        }
        async with session.get(WIKI_API_URL, params=extract_params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        extract = page.get("extract", "").strip()

        page_url = WIKI_BASE_URL + quote(title.replace(" ", "_"), safe="/:@!$&'()*+,;=")

        if extract:
            # 截断过长的简介，避免消息过长
            if len(extract) > 300:
                extract = extract[:300].rstrip() + "……"
            return f"【{title}】\n{extract}\n\n🔗 {page_url}"
        else:
            return f"【{title}】\n\n🔗 {page_url}"

    async def terminate(self):
        """插件销毁，关闭 HTTP 会话。"""
        if self._session and not self._session.closed:
            await self._session.close()

