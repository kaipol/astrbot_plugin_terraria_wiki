import re
import unicodedata
from typing import Optional

from .config import ALTERNATIVE_CANDIDATE_LIMIT
from .models import SearchSelection

_TOKEN_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("_", " ").lower()
    normalized = _TOKEN_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def tokenize_text(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if token]


def is_exact_match(query: str, title: str) -> bool:
    normalized_query = normalize_text(query).replace(" ", "")
    normalized_title = normalize_text(title).replace(" ", "")
    return bool(normalized_query) and normalized_query == normalized_title


def _score_result(query: str, result: dict) -> tuple[int, int, int, int, int]:
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    normalized_query = normalize_text(query)
    normalized_title = normalize_text(title)
    normalized_snippet = normalize_text(snippet)
    compact_query = normalized_query.replace(" ", "")
    compact_title = normalized_title.replace(" ", "")
    query_tokens = set(tokenize_text(query))
    title_tokens = set(tokenize_text(title))
    overlap = len(query_tokens & title_tokens)

    if compact_title == compact_query:
        rank = 0
    elif normalized_title.startswith(normalized_query) and normalized_query:
        rank = 1
    elif normalized_query and normalized_query in normalized_title:
        rank = 2
    elif overlap:
        rank = 3
    elif normalized_query and normalized_query in normalized_snippet:
        rank = 4
    else:
        rank = 5

    return rank, -overlap, result.get("index", 0), len(title), -int(result.get("wordcount", 0) or 0)


def pick_best_result(query: str, search_results: list[dict]) -> Optional[SearchSelection]:
    candidates = []
    for index, result in enumerate(search_results):
        title = result.get("title")
        if title:
            candidate = dict(result)
            candidate["index"] = index
            candidates.append(candidate)

    if not candidates:
        return None

    ranked_results = sorted(candidates, key=lambda item: _score_result(query, item))
    selected = ranked_results[0]
    selected_title = selected["title"]

    alternative_titles = []
    for item in ranked_results[1:]:
        title = item.get("title")
        if title and title != selected_title and title not in alternative_titles:
            alternative_titles.append(title)
        if len(alternative_titles) >= ALTERNATIVE_CANDIDATE_LIMIT:
            break

    return SearchSelection(
        title=selected_title,
        alternative_titles=alternative_titles,
        exact_match=is_exact_match(query, selected_title),
        page_id=selected.get("pageid"),
        snippet=result_snippet(selected),
        size=int(selected.get("size", 0) or 0),
        wordcount=int(selected.get("wordcount", 0) or 0),
    )


def result_snippet(result: dict) -> str:
    snippet = re.sub(r"<[^>]+>", "", result.get("snippet", ""))
    return html_unescape(snippet).strip()


def html_unescape(value: str) -> str:
    return value.replace("&quot;", '"').replace("&#039;", "'").replace("&amp;", "&")
