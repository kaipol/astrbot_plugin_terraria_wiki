import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import register

from terraria_wiki.config import (
    ALTERNATIVE_CANDIDATE_LIMIT,
    CARD_SUMMARY_LENGTH_LIMIT,
    PLUGIN_VERSION,
    REQUEST_TIMEOUT_SECONDS,
    SEARCH_CANDIDATE_LIMIT,
    SUMMARY_LENGTH_LIMIT,
    WIKI_API_URL,
    WIKI_BASE_URL,
)
from terraria_wiki.plugin import TerrariaWikiPlugin as _BaseTerrariaWikiPlugin
from terraria_wiki.ranking import is_exact_match as _is_exact_match
from terraria_wiki.ranking import normalize_text as _normalize_text
from terraria_wiki.ranking import pick_best_result as _pick_best_result
from terraria_wiki.rendering import build_page_url as _build_page_url
from terraria_wiki.rendering import format_plain_text as _format_result
from terraria_wiki.wiki_client import WikiClient


@register("astrbot_plugin_terraria_wiki", "kaipol", "泰拉瑞亚中文 Wiki 查询插件", PLUGIN_VERSION)
class TerrariaWikiPlugin(_BaseTerrariaWikiPlugin):
    @filter.command("wiki")
    async def wiki(self, event: AstrMessageEvent, query: str = "", query_fallback: str = ""):
        normalized_query = str(query or "").strip()
        if not normalized_query:
            normalized_query = str(query_fallback or "").strip()
        async for item in super().wiki(event, normalized_query):
            yield item

    @filter.llm_tool(name="terraria_wiki_lookup")
    async def terraria_wiki_lookup(self, event: AstrMessageEvent, query: str):
        """查询泰拉瑞亚中文 Wiki 词条，返回适合 AI 继续引用的纯文本摘要。

        Args:
            query(string): 要查询的泰拉瑞亚词条关键词，例如星怒、蜂王、神圣锭、Guide:Hardmode。
        """
        return await super().terraria_wiki_lookup(event, query)


async def _fetch_json(session, params):
    return await WikiClient(session).fetch_json(params)
