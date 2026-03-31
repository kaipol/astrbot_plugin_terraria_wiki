import base64
import functools
import html
import urllib.request

from .models import LookupResult, RecipeComponent, StructuredRecipe
from .rendering import article_url, format_card_text, format_plain_text, truncate_text

_CARD_WIDTH = 900
_CARD_INNER_X = 36
_CARD_INNER_WIDTH = 828
_ICON_SIZE = 28
_MAX_ICON_BYTES = 96 * 1024
_USER_AGENT = "Mozilla/5.0 ClaudeCode/terraria-wiki-plugin"


@functools.lru_cache(maxsize=256)
def _image_data_uri(url: str) -> str:
    if not url:
        return ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=5) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                return ""
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > _MAX_ICON_BYTES:
                        return ""
                except ValueError:
                    pass
            payload = response.read(_MAX_ICON_BYTES + 1)
        if not payload or len(payload) > _MAX_ICON_BYTES:
            return ""
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{content_type};base64,{encoded}"
    except Exception:
        return ""


def prefetch_icon_data_uris(urls: list[str], max_icons: int) -> int:
    warmed = 0
    for url in urls:
        if not url:
            continue
        _image_data_uri(url)
        warmed += 1
        if warmed >= max_icons:
            break
    return warmed


def _wrap_svg_text(text: str, max_width: int, font_size: int) -> list[str]:
    if not text:
        return [""]
    approx_char_width = max(10, font_size)
    max_chars = max(8, max_width // approx_char_width)
    return [text[index:index + max_chars] for index in range(0, len(text), max_chars)] or [""]


def _svg_icon(x: int, y: int, label: str, image_url: str = "") -> str:
    data_uri = _image_data_uri(image_url)
    if data_uri:
        return (
            f'<image href="{data_uri}" x="{x}" y="{y}" width="{_ICON_SIZE}" height="{_ICON_SIZE}" '
            'preserveAspectRatio="xMidYMid meet"/>'
        )
    badge = html.escape((label or "?")[:1])
    return (
        f'<rect x="{x}" y="{y}" width="{_ICON_SIZE}" height="{_ICON_SIZE}" rx="8" fill="#2563eb" fill-opacity="0.22"/>'
        f'<text x="{x + _ICON_SIZE / 2}" y="{y + 20}" text-anchor="middle" font-size="16" font-weight="700" '
        f'font-family="Segoe UI, Microsoft YaHei, sans-serif" fill="#bfdbfe">{badge}</text>'
    )


def _svg_text(
    x: int,
    y: int,
    text: str,
    font_size: int = 18,
    weight: str = "400",
    fill: str = "#e6edf3",
    max_width: int = 0,
    line_height: int = 0,
) -> tuple[str, int]:
    default_width = max(80, (_CARD_WIDTH - 40) - x)
    wrapped_lines = _wrap_svg_text(text, max_width if max_width > 0 else default_width, font_size)
    actual_line_height = line_height or max(font_size + 10, 24)
    spans = []
    for index, line in enumerate(wrapped_lines):
        dy = "0" if index == 0 else str(actual_line_height)
        spans.append(f'<tspan x="{x}" dy="{dy}">{html.escape(line)}</tspan>')
    markup = (
        f'<text x="{x}" y="{y}" font-size="{font_size}" font-weight="{weight}" '
        f'font-family="Segoe UI, Microsoft YaHei, sans-serif" fill="{fill}">'
        + "".join(spans)
        + '</text>'
    )
    return markup, len(wrapped_lines) * actual_line_height


def _svg_panel(x: int, y: int, width: int, height: int, title: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="18" fill="#0f172a" fill-opacity="0.58"/>'
        f'<text x="{x + 20}" y="{y + 28}" font-size="18" font-weight="700" '
        f'font-family="Segoe UI, Microsoft YaHei, sans-serif" fill="#93c5fd">{html.escape(title)}</text>'
    )


def _ingredient_components(recipe: StructuredRecipe) -> list[RecipeComponent]:
    if recipe.ingredient_details:
        return recipe.ingredient_details
    return [RecipeComponent(name=item) for item in recipe.ingredients]


def _recipe_panel_markup(recipe: StructuredRecipe, x: int, y: int, width: int) -> tuple[str, int]:
    components = [_component for _component in _ingredient_components(recipe) if _component.name]
    content = [_svg_panel(x, y, width, 0, "配方")]
    current_y = y + 50
    text_width = width - 78

    for component in components:
        content.append(_svg_icon(x + 20, current_y - 22, component.name, component.image_url))
        text_markup, text_height = _svg_text(
            x + 58,
            current_y,
            f"材料：{component.name}{f' x{component.amount}' if component.amount else ''}",
            max_width=text_width,
            line_height=24,
        )
        content.append(text_markup)
        current_y += max(38, text_height + 8)

    if recipe.station:
        content.append(_svg_icon(x + 20, current_y - 22, recipe.station, recipe.station_image_url))
        text_markup, text_height = _svg_text(x + 58, current_y, f"制作站：{recipe.station}", max_width=text_width, line_height=24)
        content.append(text_markup)
        current_y += max(38, text_height + 8)

    height = current_y - y + 16
    content[0] = _svg_panel(x, y, width, height, "配方")
    return "".join(content), height


def _used_in_panel_markup(recipes: list[StructuredRecipe], x: int, y: int, width: int) -> tuple[str, int]:
    content = [_svg_panel(x, y, width, 0, "用于")]
    current_y = y + 50
    text_width = width - 78

    for recipe in recipes[:2]:
        label = recipe.result or "未知产物"
        content.append(_svg_icon(x + 20, current_y - 22, label, recipe.result_image_url))
        line = f"{label}{f' x{recipe.amount}' if recipe.amount else ''}"
        text_markup, text_height = _svg_text(x + 58, current_y, line, max_width=text_width, line_height=22)
        content.append(text_markup)
        current_y += max(28, text_height)
        if recipe.station:
            station_markup, station_height = _svg_text(
                x + 58,
                current_y,
                f"制作站：{recipe.station}",
                font_size=15,
                fill="#93c5fd",
                max_width=text_width,
                line_height=20,
            )
            content.append(station_markup)
            current_y += max(24, station_height + 4)
        else:
            current_y += 10

    height = current_y - y + 12
    content[0] = _svg_panel(x, y, width, height, "用于")
    return "".join(content), height


def _transmutation_panel_markup(recipes: list[StructuredRecipe], x: int, y: int, width: int) -> tuple[str, int]:
    content = [_svg_panel(x, y, width, 0, "微光嬗变")]
    current_y = y + 50
    text_width = width - 78

    for recipe in recipes[:2]:
        label = recipe.result or "未知产物"
        content.append(_svg_icon(x + 20, current_y - 22, label, recipe.result_image_url))
        line = f"{label}{f' x{recipe.amount}' if recipe.amount else ''}"
        text_markup, text_height = _svg_text(x + 58, current_y, line, max_width=text_width, line_height=24)
        content.append(text_markup)
        current_y += max(38, text_height + 8)

    height = current_y - y + 12
    content[0] = _svg_panel(x, y, width, height, "微光嬗变")
    return "".join(content), height


def _simple_svg_card_markup(result: LookupResult) -> str:
    lines = format_card_text(result).splitlines()
    text_nodes = []
    y = 54
    for index, line in enumerate(lines):
        font_size = 26 if index == 0 else 18
        weight = "700" if index == 0 else "400"
        text_markup, text_height = _svg_text(36, y, line, font_size=font_size, weight=weight, max_width=_CARD_INNER_WIDTH)
        text_nodes.append(text_markup)
        y += text_height if index else text_height + 8

    height = max(220, y + 26)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CARD_WIDTH}" height="{height}" viewBox="0 0 {_CARD_WIDTH} {height}">'
        '<defs><linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#1d4ed8"/>'
        '</linearGradient></defs>'
        f'<rect width="{_CARD_WIDTH}" height="{height}" rx="28" fill="url(#bg)"/>'
        f'<rect x="20" y="20" width="860" height="{height - 40}" rx="22" fill="#111827" fill-opacity="0.72"/>'
        + "".join(text_nodes)
        + '</svg>'
    )


def _svg_card_markup(result: LookupResult) -> str:
    if not (result.article.recipes or result.article.used_in or result.article.transmutations):
        return _simple_svg_card_markup(result)

    nodes = []
    y = 54
    title_markup, title_height = _svg_text(_CARD_INNER_X, y, f"【{result.article.title}】", font_size=26, weight="700", max_width=_CARD_INNER_WIDTH)
    nodes.append(title_markup)
    y += title_height + 8

    summary = result.article.extract
    if summary:
        summary_markup, summary_height = _svg_text(_CARD_INNER_X, y, summary, max_width=_CARD_INNER_WIDTH, line_height=24)
        nodes.append(summary_markup)
        y += summary_height + 10

    info_lines = [
        line
        for line in result.article.structured_summary
        if not line.startswith("配方：") and not line.startswith("用于：")
    ][:3]
    for line in info_lines:
        line_markup, line_height = _svg_text(_CARD_INNER_X, y, line, fill="#cbd5e1", max_width=_CARD_INNER_WIDTH, line_height=24)
        nodes.append(line_markup)
        y += line_height + 4

    if result.article.recipes:
        recipe_markup, recipe_height = _recipe_panel_markup(result.article.recipes[0], _CARD_INNER_X, y + 10, _CARD_INNER_WIDTH)
        nodes.append(recipe_markup)
        y += recipe_height + 22

    if result.article.used_in:
        used_in_markup, used_in_height = _used_in_panel_markup(result.article.used_in, _CARD_INNER_X, y, _CARD_INNER_WIDTH)
        nodes.append(used_in_markup)
        y += used_in_height + 18

    if result.article.transmutations:
        transmutation_markup, transmutation_height = _transmutation_panel_markup(result.article.transmutations, _CARD_INNER_X, y, _CARD_INNER_WIDTH)
        nodes.append(transmutation_markup)
        y += transmutation_height + 18

    link_markup, link_height = _svg_text(_CARD_INNER_X, y, f"原链接：{article_url(result)}", fill="#93c5fd", max_width=_CARD_INNER_WIDTH, line_height=22)
    nodes.append(link_markup)
    y += link_height + 6
    footer_markup, footer_height = _svg_text(_CARD_INNER_X, y, "Terraria Wiki", fill="#e6edf3", max_width=_CARD_INNER_WIDTH)
    nodes.append(footer_markup)
    height = max(260, y + footer_height + 18)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CARD_WIDTH}" height="{height}" viewBox="0 0 {_CARD_WIDTH} {height}">'
        '<defs><linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#1d4ed8"/>'
        '</linearGradient></defs>'
        f'<rect width="{_CARD_WIDTH}" height="{height}" rx="28" fill="url(#bg)"/>'
        f'<rect x="20" y="20" width="860" height="{height - 40}" rx="22" fill="#111827" fill-opacity="0.72"/>'
        + "".join(nodes)
        + '</svg>'
    )


def render_card_base64(result: LookupResult) -> str:
    svg = _svg_card_markup(result)
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


def build_success_response(event, result: LookupResult):
    plain_text = format_plain_text(result)

    if hasattr(event, "make_result") and hasattr(event, "chain_result"):
        try:
            chain = event.make_result()
            if hasattr(chain, "base64_image") and hasattr(chain, "message"):
                chain.base64_image(render_card_base64(result))
                chain.message(f"原链接：{article_url(result)}")
                chain.message(plain_text)
                return event.chain_result(chain)
        except Exception:
            pass

    return event.plain_result(plain_text)
