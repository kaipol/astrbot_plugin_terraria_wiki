import html as html_lib
import re
from typing import Any

from .config import CARGO_QUERY_LIMIT, STRUCTURED_RECIPE_LIMIT, STRUCTURED_SUMMARY_LIMIT
from .models import RecipeComponent, StructuredRecipe

_FIELD_LABELS = {
    "type": "类型",
    "damage": "伤害",
    "defense": "防御",
    "knockback": "击退",
    "usetime": "使用时间",
    "damagetype": "伤害类型",
    "rare": "稀有度",
    "stack": "堆叠",
    "buy": "买入",
    "sell": "卖出",
}

_PREFERRED_VERSION_KEYWORDS = (
    "电脑版",
    "桌面版",
    "移动版",
    "主机版",
    "desktop",
    "mobile",
    "console",
)

_DEPRIORITIZED_VERSION_KEYWORDS = (
    "3ds",
    "任天堂3ds",
    "旧主机版",
    "old-gen",
    "old gen",
)

_TYPE_VALUE_TRANSLATIONS = {
    "weapon": "武器",
    "crafting material": "制作材料",
    "material": "材料",
    "accessory": "饰品",
    "consumable": "消耗品",
    "furniture": "家具",
    "tool": "工具",
    "ammo": "弹药",
    "block": "物块",
    "placeable": "可放置物",
    "vanity item": "时装",
    "permanent booster": "永久强化物品",
}

_STATION_VALUE_TRANSLATIONS = {
    "shimmer": "微光",
    "iron anvil": "铁砧",
    "lead anvil": "铅砧",
    "mythril anvil": "秘银砧或山铜砧",
    "orichalcum anvil": "秘银砧或山铜砧",
    "tinkerer's workshop": "工匠作坊",
    "ecto mist": "灵雾",
    "heavy assembler": "重型工作台",
    "困难模式前的砧": "铁砧或铅砧",
    "困难模式前砧": "铁砧或铅砧",
    "困难模式之前的砧": "铁砧或铅砧",
    "困难模式的砧": "秘银砧或山铜砧",
    "困难模式后砧": "秘银砧或山铜砧",
    "困难模式后的砧": "秘银砧或山铜砧",
    "pre-hardmode anvil": "铁砧或铅砧",
    "pre-hardmode anvils": "铁砧或铅砧",
    "hardmode anvil": "秘银砧或山铜砧",
    "hardmode anvils": "秘银砧或山铜砧",
}

_DAMAGE_TYPE_TRANSLATIONS = {
    "melee": "近战",
    "ranged": "远程",
    "magic": "魔法",
    "summon": "召唤",
    "throwing": "投掷",
}


def cargo_query_params(tables: str, fields: str, where: str, limit: int = CARGO_QUERY_LIMIT, join_on: str = "") -> dict[str, Any]:
    params = {
        "action": "cargoquery",
        "tables": tables,
        "fields": fields,
        "where": where,
        "limit": limit,
        "format": "json",
    }
    if join_on:
        params["join_on"] = join_on
    return params


def unwrap_cargo_rows(data: dict) -> list[dict]:
    rows = []
    for row in data.get("cargoquery", []) or []:
        if isinstance(row, dict) and isinstance(row.get("title"), dict):
            rows.append(row["title"])
        elif isinstance(row, dict):
            rows.append(row)
    return rows


def normalize_cargo_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#039;", "'").replace("&quot;", '"')
    text = text.replace("¦", "").strip()
    return " ".join(text.split())


def clean_structured_value(value: Any) -> str:
    text = html_lib.unescape(normalize_cargo_text(value)).replace("^", " / ")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def prefer_primary_platform_text(value: str) -> str:
    text = clean_structured_value(value)
    if not text or "(" not in text:
        return text
    parts = [part.strip() for part in text.split(" / ") if part.strip()]
    if len(parts) <= 1:
        return text
    preferred = [
        part
        for part in parts
        if any(keyword in part.lower() for keyword in _PREFERRED_VERSION_KEYWORDS)
        and not any(keyword in part.lower() for keyword in _DEPRIORITIZED_VERSION_KEYWORDS)
    ]
    if preferred:
        return " / ".join(preferred)
    non_deprioritized = [
        part for part in parts if not any(keyword in part.lower() for keyword in _DEPRIORITIZED_VERSION_KEYWORDS)
    ]
    return " / ".join(non_deprioritized) if non_deprioritized else text


def _translate_tokens(value: str, mapping: dict[str, str]) -> str:
    parts = [part.strip() for part in value.split(" / ") if part.strip()]
    translated = [mapping.get(part.lower(), part) for part in parts]
    return " / ".join(translated)


def _translate_phrase(value: str, mapping: dict[str, str]) -> str:
    text = clean_structured_value(value)
    if not text:
        return text
    lowered = text.lower()
    if lowered in mapping:
        return mapping[lowered]
    parts = [part.strip() for part in re.split(r"\s+and\s+", text, flags=re.I) if part.strip()]
    translated = [mapping.get(part.lower(), part) for part in parts]
    return " 和 ".join(translated)


def parse_coin_value(value: Any) -> str:
    text = normalize_cargo_text(value)
    digits = [char for char in text if char.isdigit()]
    return "".join(digits) if digits else text


def parse_ingredients(raw: Any) -> list[str]:
    return [
        f"{name}{amount}" if amount else name
        for name, amount in parse_ingredient_parts(raw)
    ]


def parse_ingredient_parts(raw: Any) -> list[tuple[str, str]]:
    text = "" if raw is None else str(raw)
    text = text.replace("¦", "")
    parts = [normalize_cargo_text(part) for part in text.split("^") if normalize_cargo_text(part)]
    parsed: list[tuple[str, str]] = []
    for part in parts:
        match = re.match(r"^(.*?)(\d+)$", part)
        if match:
            name, amount = match.groups()
            parsed.append((name.strip(), amount))
        else:
            parsed.append((part, ""))
    return parsed


def format_component(component: RecipeComponent) -> str:
    return f"{component.name} x{component.amount}" if component.amount else component.name


def format_ingredient_list(ingredients: list[str], separator: str = " + ") -> str:
    formatted = []
    for item in ingredients:
        pretty = _prettify_ingredient(item)
        if pretty:
            formatted.append(pretty)
    return separator.join(formatted)


def format_recipe_details(recipe: StructuredRecipe, include_result: bool = True, include_version: bool = False) -> list[str]:
    lines: list[str] = []
    if recipe.ingredient_details:
        ingredients = "、".join(format_component(component) for component in recipe.ingredient_details if component.name)
    else:
        ingredients = format_ingredient_list(recipe.ingredients, separator="、")
    if ingredients:
        lines.append(f"材料：{ingredients}")
    if include_result and recipe.result:
        result_text = f"{recipe.result} x{recipe.amount}" if recipe.amount else recipe.result
        lines.append(f"产出：{result_text}")
    if recipe.station:
        lines.append(f"制作站：{recipe.station}")
    if include_version and recipe.version:
        lines.append(f"版本：{recipe.version}")
    return lines


def _normalized_version_text(value: str) -> str:
    return normalize_cargo_text(value).lower()


def _recipe_version_score(recipe: StructuredRecipe) -> int:
    version_text = _normalized_version_text(recipe.version)
    score = 0
    if recipe.legacy:
        score += 100
    if any(keyword in version_text for keyword in _DEPRIORITIZED_VERSION_KEYWORDS):
        score += 50
    if version_text and any(keyword in version_text for keyword in _PREFERRED_VERSION_KEYWORDS):
        score -= 10
    return score


def _recipe_sort_key(recipe: StructuredRecipe) -> tuple:
    return (
        _recipe_version_score(recipe),
        0 if recipe.ingredients else 1,
        0 if recipe.station else 1,
        0 if recipe.amount else 1,
        -len(recipe.ingredients),
        recipe.result,
        recipe.station,
    )


def select_preferred_recipes(rows: list[dict]) -> list[StructuredRecipe]:
    normalized = [normalize_recipe_row(row) for row in rows]
    ordered = sorted(normalized, key=_recipe_sort_key)
    selected: list[StructuredRecipe] = []
    seen: set[tuple] = set()
    for recipe in ordered:
        signature = (recipe.result, recipe.amount, recipe.station, tuple(recipe.ingredients))
        if signature in seen:
            continue
        seen.add(signature)
        selected.append(recipe)
        if len(selected) >= STRUCTURED_RECIPE_LIMIT:
            break
    return selected


def format_recipe_summary(recipe: StructuredRecipe) -> str:
    details = format_recipe_details(recipe)
    return "配方：" + "；".join(details) if details else "配方"


def _prettify_ingredient(value: str) -> str:
    text = normalize_cargo_text(value)
    match = re.match(r"^(.*?)(\d+)$", text)
    if not match:
        return text
    name, amount = match.groups()
    name = name.strip()
    return f"{name} x{amount}" if name else text


def normalize_recipe_row(row: dict) -> StructuredRecipe:
    raw_ingredients = row.get("ings") or row.get("ingredients")
    ingredient_details = row.get("ingredient_details") or [
        {"name": name, "amount": amount}
        for name, amount in parse_ingredient_parts(raw_ingredients)
    ]
    normalized_details = [RecipeComponent.from_dict(item) for item in ingredient_details]
    normalized_ingredients = [
        f"{component.name}{component.amount}" if component.amount else component.name
        for component in normalized_details
        if component.name
    ] or parse_ingredients(raw_ingredients)
    station = _translate_phrase(row.get("station_page") or row.get("station"), _STATION_VALUE_TRANSLATIONS)
    return StructuredRecipe(
        result=normalize_cargo_text(row.get("result_page") or row.get("result") or row.get("name")),
        amount=normalize_cargo_text(row.get("amount")),
        station=station,
        ingredients=normalized_ingredients,
        ingredient_details=normalized_details,
        result_page=normalize_cargo_text(row.get("result_page")),
        result_image_url=normalize_cargo_text(row.get("result_image_url")),
        station_page=normalize_cargo_text(row.get("station_page")),
        station_image_url=normalize_cargo_text(row.get("station_image_url")),
        version=normalize_cargo_text(row.get("version")),
        legacy=str(row.get("legacy", "0")).lower() in {"1", "true", "yes"},
    )


def build_infobox_fields(item_row: dict) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, label in _FIELD_LABELS.items():
        value = item_row.get(key)
        if value in (None, ""):
            continue
        normalized = parse_coin_value(value) if key in {"buy", "sell"} else prefer_primary_platform_text(value)
        if key == "type":
            normalized = _translate_tokens(normalized, _TYPE_VALUE_TRANSLATIONS)
        elif key == "damagetype":
            normalized = _translate_tokens(normalized, _DAMAGE_TYPE_TRANSLATIONS)
        elif key == "station":
            normalized = _translate_phrase(normalized, _STATION_VALUE_TRANSLATIONS)
        if normalized:
            fields[label] = normalized
    return fields


def infer_entity_type(item_row: dict | None, categories: list[str]) -> str:
    if item_row:
        return "item"
    normalized_categories = [item.lower() for item in categories]
    if any("boss" in item for item in normalized_categories):
        return "boss"
    if any("biome" in item for item in normalized_categories):
        return "biome"
    if any("event" in item for item in normalized_categories):
        return "event"
    return "unknown"


def build_structured_summary(entity_type: str, infobox_fields: dict[str, str], recipes: list[StructuredRecipe], used_in: list[StructuredRecipe]) -> list[str]:
    summary: list[str] = []
    for label, value in infobox_fields.items():
        summary.append(f"{label}：{value}")
        if len(summary) >= STRUCTURED_SUMMARY_LIMIT:
            break

    if entity_type == "item" and recipes:
        summary.append(format_recipe_summary(recipes[0]))

    if used_in:
        targets = [recipe.result for recipe in used_in[:STRUCTURED_RECIPE_LIMIT] if recipe.result]
        if targets:
            summary.append(f"用于：{'、'.join(targets)}")

    return summary[: STRUCTURED_SUMMARY_LIMIT + 2]


def build_structured_payload(title: str, categories: list[str], item_rows: list[dict], recipe_rows: list[dict], used_in_rows: list[dict]) -> dict[str, Any]:
    item_row = item_rows[0] if item_rows else None
    infobox_fields = build_infobox_fields(item_row or {})
    recipes = select_preferred_recipes(recipe_rows)
    used_in = select_preferred_recipes(used_in_rows)
    transmutations: list[StructuredRecipe] = []
    remaining_used_in: list[StructuredRecipe] = []
    for recipe in used_in:
        if recipe.station == "微光":
            transmutations.append(recipe)
        else:
            remaining_used_in.append(recipe)
    entity_type = infer_entity_type(item_row, categories)

    return {
        "entity_type": entity_type,
        "infobox_fields": infobox_fields,
        "recipes": recipes,
        "used_in": remaining_used_in,
        "transmutations": transmutations,
        "structured_summary": build_structured_summary(entity_type, infobox_fields, recipes, remaining_used_in),
    }
