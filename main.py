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
from terraria_wiki.plugin import TerrariaWikiPlugin
from terraria_wiki.ranking import is_exact_match as _is_exact_match
from terraria_wiki.ranking import normalize_text as _normalize_text
from terraria_wiki.ranking import pick_best_result as _pick_best_result
from terraria_wiki.rendering import build_page_url as _build_page_url
from terraria_wiki.rendering import format_plain_text as _format_result
from terraria_wiki.wiki_client import WikiClient


async def _fetch_json(session, params):
    return await WikiClient(session).fetch_json(params)
