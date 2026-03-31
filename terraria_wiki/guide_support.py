import html as html_lib
import re
from urllib.parse import quote

from .config import GUIDE_MAX_SECTIONS, GUIDE_NAMESPACE_NAME, GUIDE_PAGE_LENGTH_THRESHOLD, GUIDE_SECTION_THRESHOLD
from .models import GuideSection

_SKIP_SECTION_TITLES = {
    "参见",
    "参考",
    "参考资料",
    "外部链接",
    "历史",
    "注释",
    "引用",
    "备注",
    "see also",
    "references",
    "external links",
    "history",
    "notes",
}


def clean_snippet(snippet: str) -> str:
    snippet = re.sub(r"<[^>]+>", "", snippet or "")
    return snippet.replace("&quot;", '"').replace("&#039;", "'").replace("&amp;", "&").strip()


def html_to_plain_text(text: str) -> str:
    plain = text or ""
    plain = re.sub(r"<!--.*?-->", " ", plain, flags=re.S)
    plain = re.sub(r"<ref[^>/]*?>[\s\S]*?</ref>", " ", plain, flags=re.I)
    plain = re.sub(r"<ref[^>]*/>", " ", plain, flags=re.I)
    plain = re.sub(r"<script[\s\S]*?</script>", " ", plain, flags=re.I)
    plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
    plain = re.sub(r"<br\s*/?>", "\n", plain, flags=re.I)
    plain = re.sub(r"</(?:p|div|section|table|tr|ul|ol|dl|blockquote|h\d)>", "\n", plain, flags=re.I)
    plain = re.sub(r"<li[^>]*>", "- ", plain, flags=re.I)
    plain = re.sub(r"</li>", "\n", plain, flags=re.I)
    plain = re.sub(r"<(?:b|strong|i|em|span|a)\b[^>]*>", "", plain, flags=re.I)
    plain = re.sub(r"</(?:b|strong|i|em|span|a)>", "", plain, flags=re.I)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = html_lib.unescape(plain).replace("\xa0", " ")
    plain = re.sub(r"\[\s*编辑\s*\]", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    plain = re.sub(r"[ \t]{2,}", " ", plain)
    plain = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", plain)
    plain = re.sub(r"([\u4e00-\u9fff])\s+([，。！？；：）】》])", r"\1\2", plain)
    plain = re.sub(r"([（【《])\s+([\u4e00-\u9fff])", r"\1\2", plain)
    plain = re.sub(r" ?\n ?", "\n", plain)
    return plain.strip()


def _strip_parse_noise(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"<div id=\"toc\"[\s\S]*?</ul>\s*</div>\s*</div>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<span class=\"mw-editsection\"[\s\S]*?</span>", " ", cleaned, flags=re.I)
    return cleaned


def _normalize_summary_candidate(text: str) -> str:
    candidate = (text or "").strip()
    candidate = re.sub(r"^[\-•·]\s*", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate.strip()


def summarize_parsed_html(text: str, limit: int, allow_full_fallback: bool = True) -> str:
    source = text or ""
    paragraph_candidates = [
        _normalize_summary_candidate(html_to_plain_text(match))
        for match in re.findall(r"<p\b[^>]*>([\s\S]*?)</p>", source, flags=re.I)
    ]
    list_candidates = [
        _normalize_summary_candidate(html_to_plain_text(match))
        for match in re.findall(r"<li\b[^>]*>([\s\S]*?)</li>", source, flags=re.I)
    ]
    candidates = [
        candidate
        for candidate in [*paragraph_candidates, *list_candidates]
        if len(re.sub(r"\s+", "", candidate)) >= 12
    ]
    summary = candidates[0] if candidates else (
        html_to_plain_text(_strip_parse_noise(source)) if allow_full_fallback else ""
    )
    if len(summary) > limit:
        return summary[:limit].rstrip() + "……"
    return summary



def wikitext_to_plain_text(text: str) -> str:
    plain = text or ""
    plain = re.sub(r"\{\{tr\|([^{}|]+)(?:\|[^{}]*)?\}\}", r"\1", plain)
    plain = re.sub(r"\{\{nbsp\}\}", " ", plain)
    plain = re.sub(r"\{\{chance\|([^{}|]+)\}\}", r"\1", plain)
    plain = re.sub(r"\{\{old-gen\}\}", "旧主机版", plain)
    plain = re.sub(r"\{\{eicons?\|[^{}]*\}\}", " ", plain)
    previous = None
    while previous != plain:
        previous = plain
        plain = re.sub(r"\{\{[^{}]*\}\}", " ", plain)
        plain = re.sub(r"\{\|[\s\S]*?\|\}", " ", plain)
    plain = re.sub(r"<!--.*?-->", " ", plain, flags=re.S)
    plain = re.sub(r"<ref[^>/]*?>[\s\S]*?</ref>", " ", plain, flags=re.I)
    plain = re.sub(r"<ref[^>]*/>", " ", plain, flags=re.I)
    plain = re.sub(r"\[\[(?:File|Image|文件|图像|圖像):[^\]]+\]\]", " ", plain, flags=re.I)
    plain = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", plain)
    plain = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", plain)
    plain = re.sub(r"={2,}\s*([^=]+?)\s*={2,}", "\n", plain)
    plain = re.sub(r"'{2,}", "", plain)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    plain = re.sub(r"[ \t]{2,}", " ", plain)
    return plain.strip()


def summarize_wikitext(text: str, limit: int) -> str:
    plain = wikitext_to_plain_text(text)
    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", plain) if segment.strip()]
    summary = paragraphs[0] if paragraphs else plain
    if len(summary) > limit:
        return summary[:limit].rstrip() + "……"
    return summary


def is_guide_like(title: str, categories: list[str], length: int, section_count: int) -> bool:
    normalized_title = (title or "").lower()
    normalized_categories = [item.lower() for item in categories]
    return (
        normalized_title.startswith(f"{GUIDE_NAMESPACE_NAME.lower()}:")
        or any("guide" in item or "指南" in item or "攻略" in item for item in normalized_categories)
        or length >= GUIDE_PAGE_LENGTH_THRESHOLD
        or section_count >= GUIDE_SECTION_THRESHOLD
    )


def select_key_sections(sections: list[dict]) -> list[dict]:
    selected = []
    for section in sections:
        title = (section.get("line") or "").strip()
        if not title:
            continue
        if title.lower() in _SKIP_SECTION_TITLES:
            continue
        if int(section.get("toclevel", 1) or 1) > 2:
            continue
        selected.append(section)
        if len(selected) >= GUIDE_MAX_SECTIONS:
            break
    return selected


def build_section_url(base_url: str, anchor: str) -> str:
    if not anchor:
        return base_url
    return f"{base_url}#{quote(anchor, safe='')}"


def build_guide_sections(base_url: str, sections: list[dict], summaries: dict[str, str]) -> list[GuideSection]:
    guide_sections = []
    for section in sections:
        index = str(section.get("index", ""))
        anchor = section.get("anchor", "")
        title = (section.get("line") or "").strip()
        summary = (summaries.get(index, "") or "").strip()
        if not summary:
            continue
        guide_sections.append(
            GuideSection(
                index=index,
                title=title,
                anchor=anchor,
                summary=summary,
                url=build_section_url(base_url, anchor),
            )
        )
    return guide_sections
