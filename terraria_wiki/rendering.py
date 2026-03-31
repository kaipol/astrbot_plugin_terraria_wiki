from urllib.parse import quote

from .config import (
    CARD_FOOTER,
    CARD_SUMMARY_LENGTH_LIMIT,
    GUIDE_SECTION_SUMMARY_LIMIT,
    STRUCTURED_SUMMARY_LIMIT,
    SUMMARY_LENGTH_LIMIT,
    WIKI_BASE_URL,
)
from .models import LookupResult
from .structured_support import format_recipe_details


def build_page_url(title: str) -> str:
    return WIKI_BASE_URL + quote(title.replace(" ", "_"), safe="/:@!$&'()*+,;=")


def article_url(result: LookupResult) -> str:
    return result.article.canonical_url or build_page_url(result.article.title)


def truncate_text(text: str, limit: int) -> str:
    if text and len(text) > limit:
        return text[:limit].rstrip() + "……"
    return text


def _format_guide_sections_plain(result: LookupResult) -> str:
    lines = []
    for section in result.article.guide_sections:
        summary = truncate_text(section.summary, GUIDE_SECTION_SUMMARY_LIMIT)
        line = f"- {section.title}"
        if summary:
            line += f"：{summary}"
        if section.url:
            line += f"\n  {section.url}"
        lines.append(line)
    return "\n".join(lines)


def _format_guide_sections_card(result: LookupResult) -> str:
    lines = []
    for section in result.article.guide_sections:
        summary = truncate_text(section.summary, 80)
        line = f"- {section.title}"
        if summary:
            line += f"：{summary}"
        lines.append(line)
    return "\n".join(lines)


def _format_used_in_plain(result: LookupResult) -> list[str]:
    lines = ["用于："]
    for recipe in result.article.used_in[:2]:
        target = f"{recipe.result} x{recipe.amount}" if recipe.amount else recipe.result
        if not target:
            continue
        if recipe.station:
            lines.append(f"- {target}（制作站：{recipe.station}）")
        else:
            lines.append(f"- {target}")
    return lines


def _format_transmutations_plain(result: LookupResult) -> list[str]:
    lines = ["微光嬗变："]
    for recipe in result.article.transmutations[:2]:
        target = f"{recipe.result} x{recipe.amount}" if recipe.amount else recipe.result
        if target:
            lines.append(f"- {target}")
    return lines


def _format_structured_plain(result: LookupResult) -> str:
    lines = []
    summary_lines = [
        line
        for line in result.article.structured_summary[:STRUCTURED_SUMMARY_LIMIT]
        if not line.startswith("配方：") and not line.startswith("用于：")
    ]
    if summary_lines:
        lines.extend(summary_lines)
    elif result.article.infobox_fields:
        for label, value in list(result.article.infobox_fields.items())[:STRUCTURED_SUMMARY_LIMIT]:
            lines.append(f"{label}：{value}")

    if result.article.recipes:
        lines.append("配方：")
        for detail in format_recipe_details(result.article.recipes[0]):
            lines.append(f"- {detail}")

    if result.article.used_in:
        lines.extend(_format_used_in_plain(result))

    if result.article.transmutations:
        lines.extend(_format_transmutations_plain(result))

    return "\n".join(lines)


def _format_structured_card(result: LookupResult) -> str:
    lines = []
    for line in result.article.structured_summary[:STRUCTURED_SUMMARY_LIMIT]:
        if line.startswith("配方：") or line.startswith("用于："):
            continue
        lines.append(truncate_text(line, 60))

    if result.article.recipes:
        lines.append("配方：")
        for detail in format_recipe_details(result.article.recipes[0]):
            lines.append(truncate_text(f"· {detail}", 60))

    if result.article.used_in:
        lines.append("用于：")
        for recipe in result.article.used_in[:2]:
            target = f"{recipe.result} x{recipe.amount}" if recipe.amount else recipe.result
            if target:
                lines.append(truncate_text(f"· {target}", 60))

    if result.article.transmutations:
        lines.append("微光嬗变：")
        for recipe in result.article.transmutations[:2]:
            target = f"{recipe.result} x{recipe.amount}" if recipe.amount else recipe.result
            if target:
                lines.append(truncate_text(f"· {target}", 60))

    return "\n".join(lines)


def format_plain_text(result: LookupResult) -> str:
    extract = truncate_text(result.article.extract, SUMMARY_LENGTH_LIMIT)
    parts = [f"【{result.article.title}】"]
    if result.article.redirected_from:
        parts.append(f"重定向自：{result.article.redirected_from}")
    if extract:
        parts.append(extract)

    has_structured = (
        result.article.structured_summary
        or result.article.infobox_fields
        or result.article.recipes
        or result.article.used_in
        or result.article.transmutations
    )
    if has_structured:
        structured_text = _format_structured_plain(result)
        if structured_text:
            parts.append("核心属性：\n" + structured_text)
    elif result.article.guide_like and result.article.guide_sections:
        parts.append("关键章节：\n" + _format_guide_sections_plain(result))

    parts.append(f"🔗 {article_url(result)}")

    if result.alternative_titles and not result.exact_match:
        parts.append(f"可能还想查：{'、'.join(result.alternative_titles)}")

    return "\n\n".join(parts)


def format_card_text(result: LookupResult) -> str:
    summary = truncate_text(result.article.extract, CARD_SUMMARY_LENGTH_LIMIT)
    parts = [f"【{result.article.title}】"]
    if summary:
        parts.append(summary)

    has_structured = (
        result.article.structured_summary
        or result.article.infobox_fields
        or result.article.recipes
        or result.article.used_in
        or result.article.transmutations
    )
    if has_structured:
        parts.append("核心属性：")
        parts.append(_format_structured_card(result))
    elif result.article.guide_like and result.article.guide_sections:
        parts.append("章节摘要：")
        parts.append(_format_guide_sections_card(result))

    parts.append(f"原链接：{article_url(result)}")

    if result.alternative_titles and not result.exact_match:
        parts.append(f"相关词条：{'、'.join(result.alternative_titles)}")

    parts.append(CARD_FOOTER)
    return "\n".join(parts)
