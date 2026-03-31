import asyncio
import time
from typing import Optional
from urllib.parse import quote

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .cache import InFlightRequestDeduper, TTLCache
from .config import (
    CACHE_MAX_ENTRIES,
    GUIDE_CACHE_TTL_SECONDS,
    ICON_PREFETCH_FILES,
    ICON_PREFETCH_INTERVAL_SECONDS,
    ICON_PREFETCH_MAX_ICONS,
    NEGATIVE_CACHE_TTL_SECONDS,
    PAGE_CACHE_TTL_SECONDS,
    PERSISTENT_CACHE_PATH,
    PERSISTENT_CACHE_TTL_SECONDS,
    PLUGIN_VERSION,
    QUERY_CACHE_TTL_SECONDS,
    REDIRECT_CACHE_TTL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    SEARCH_CACHE_TTL_SECONDS,
    STRUCTURED_SCHEMA_VERSION,
    WIKI_API_URL,
)
from .models import GuideSection, LookupResult, WikiArticle
from .persistent_cache import PersistentLookupCache
from .ranking import normalize_text
from .results import build_success_response, prefetch_icon_data_uris
from .wiki_client import WikiClient


@register("astrbot_plugin_terraria_wiki", "kaipol", "泰拉瑞亚中文 Wiki 查询插件", PLUGIN_VERSION)
class TerrariaWikiPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._session: Optional[aiohttp.ClientSession] = None
        self._query_cache = TTLCache[LookupResult](QUERY_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._negative_cache = TTLCache[bool](NEGATIVE_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._page_cache = TTLCache[WikiArticle](PAGE_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._search_cache = TTLCache[list[dict]](SEARCH_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._guide_cache = TTLCache[list[GuideSection]](GUIDE_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._redirect_cache = TTLCache[dict](REDIRECT_CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
        self._deduper = InFlightRequestDeduper()
        self._persistent_cache: Optional[PersistentLookupCache] = None
        self._last_icon_prefetch_at = 0.0
        self._icon_prefetch_lock = asyncio.Lock()
        try:
            self._persistent_cache = PersistentLookupCache(
                PERSISTENT_CACHE_PATH,
                PERSISTENT_CACHE_TTL_SECONDS,
                namespace=STRUCTURED_SCHEMA_VERSION,
            )
        except Exception as error:
            logger.error(f"[TerrariaWiki] 初始化持久缓存失败: {error}")

    async def initialize(self):
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        self._session = aiohttp.ClientSession(timeout=timeout)
        await self._prefetch_common_icons()

    async def _prefetch_common_icons(self):
        if not ICON_PREFETCH_FILES or ICON_PREFETCH_MAX_ICONS <= 0:
            return

        async with self._icon_prefetch_lock:
            now = time.monotonic()
            if now - self._last_icon_prefetch_at < ICON_PREFETCH_INTERVAL_SECONDS:
                return

            wiki_root = WIKI_API_URL.rsplit("/api.php", 1)[0]
            urls = [
                f"{wiki_root}/special:filepath/{quote(file_name, safe='')}"
                for file_name in ICON_PREFETCH_FILES[:ICON_PREFETCH_MAX_ICONS]
            ]

            try:
                await asyncio.to_thread(prefetch_icon_data_uris, urls, ICON_PREFETCH_MAX_ICONS)
                self._last_icon_prefetch_at = now
            except Exception as error:
                logger.error(f"[TerrariaWiki] 预抓取图标失败: {error}")

    @filter.command("wiki")
    async def wiki(self, event: AstrMessageEvent):
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请提供查询关键词，例如：/wiki 泰拉瑞亚")
            return

        try:
            result = await self._lookup(query)
        except asyncio.TimeoutError:
            logger.error(f"[TerrariaWiki] 查询超时: query={query}")
            yield event.plain_result("查询 Wiki 超时，请稍后重试。")
            return
        except aiohttp.ClientConnectionError as error:
            logger.error(f"[TerrariaWiki] 连接失败: query={query}, error={error}")
            yield event.plain_result("当前无法连接 Wiki，请稍后再试。")
            return
        except aiohttp.ClientResponseError as error:
            logger.error(f"[TerrariaWiki] HTTP 错误: query={query}, status={error.status}, message={error.message}")
            yield event.plain_result("查询 Wiki 时出错，请稍后重试。")
            return
        except aiohttp.ClientError as error:
            logger.error(f"[TerrariaWiki] 网络异常: query={query}, error={error}")
            yield event.plain_result("查询 Wiki 时网络异常，请稍后再试。")
            return
        except Exception as error:
            logger.error(f"[TerrariaWiki] 查询失败: query={query}, error={error}")
            yield event.plain_result("查询失败，请稍后再试。")
            return

        if result is None:
            yield event.plain_result(f"未找到与「{query}」相关的内容。")
            return

        yield build_success_response(event, result)

    async def _lookup(self, query: str) -> Optional[LookupResult]:
        if self._session and not self._session.closed:
            return await self._lookup_with_session(self._session, query)

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            return await self._lookup_with_session(session, query)

    async def _lookup_with_session(self, session: aiohttp.ClientSession, query: str) -> Optional[LookupResult]:
        key = normalize_text(query)
        cached = self._query_cache.get(key)
        if cached is not None:
            return cached

        if self._persistent_cache is not None:
            persisted = self._persistent_cache.get(key)
            if persisted is not None:
                self._query_cache.set(key, persisted)
                return persisted

        if self._negative_cache.get(key):
            return None

        async def fetch() -> Optional[LookupResult]:
            client = WikiClient(
                session,
                page_cache=self._page_cache,
                search_cache=self._search_cache,
                guide_cache=self._guide_cache,
                redirect_cache=self._redirect_cache,
            )
            result = await client.lookup(query)
            if result is None:
                self._negative_cache.set(key, True)
                return None

            self._query_cache.set(key, result)
            if self._persistent_cache is not None:
                self._persistent_cache.set(key, result)
            return result

        return await self._deduper.run(key, fetch)

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._query_cache.clear()
        self._negative_cache.clear()
        self._page_cache.clear()
        self._search_cache.clear()
        self._guide_cache.clear()
        self._redirect_cache.clear()
        if self._persistent_cache is not None:
            self._persistent_cache.close()
