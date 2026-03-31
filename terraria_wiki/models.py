from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class SearchSelection:
    title: str
    alternative_titles: list[str] = field(default_factory=list)
    exact_match: bool = False
    page_id: Optional[int] = None
    snippet: str = ""
    size: int = 0
    wordcount: int = 0


@dataclass(slots=True)
class GuideSection:
    index: str
    title: str
    anchor: str = ""
    summary: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "GuideSection":
        return cls(
            index=str(data.get("index", "")),
            title=data.get("title", ""),
            anchor=data.get("anchor", ""),
            summary=data.get("summary", ""),
            url=data.get("url", ""),
        )


@dataclass(slots=True)
class RecipeComponent:
    name: str
    amount: str = ""
    page: str = ""
    image_url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "RecipeComponent":
        return cls(
            name=data.get("name", ""),
            amount=str(data.get("amount", "")),
            page=data.get("page", ""),
            image_url=data.get("image_url", ""),
        )


@dataclass(slots=True)
class StructuredRecipe:
    result: str
    amount: str = ""
    station: str = ""
    ingredients: list[str] = field(default_factory=list)
    ingredient_details: list[RecipeComponent] = field(default_factory=list)
    result_page: str = ""
    result_image_url: str = ""
    station_page: str = ""
    station_image_url: str = ""
    version: str = ""
    legacy: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredRecipe":
        return cls(
            result=data.get("result", ""),
            amount=str(data.get("amount", "")),
            station=data.get("station", ""),
            ingredients=list(data.get("ingredients", [])),
            ingredient_details=[RecipeComponent.from_dict(item) for item in data.get("ingredient_details", [])],
            result_page=data.get("result_page", ""),
            result_image_url=data.get("result_image_url", ""),
            station_page=data.get("station_page", ""),
            station_image_url=data.get("station_image_url", ""),
            version=data.get("version", ""),
            legacy=bool(data.get("legacy", False)),
        )


@dataclass(slots=True)
class WikiArticle:
    title: str
    extract: str = ""
    thumbnail_url: Optional[str] = None
    page_id: Optional[int] = None
    canonical_url: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    length: int = 0
    snippet: str = ""
    redirected_from: Optional[str] = None
    guide_like: bool = False
    guide_sections: list[GuideSection] = field(default_factory=list)
    entity_type: str = "unknown"
    infobox_fields: dict[str, str] = field(default_factory=dict)
    recipes: list[StructuredRecipe] = field(default_factory=list)
    used_in: list[StructuredRecipe] = field(default_factory=list)
    transmutations: list[StructuredRecipe] = field(default_factory=list)
    structured_summary: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "WikiArticle":
        return cls(
            title=data.get("title", ""),
            extract=data.get("extract", ""),
            thumbnail_url=data.get("thumbnail_url"),
            page_id=data.get("page_id"),
            canonical_url=data.get("canonical_url"),
            categories=list(data.get("categories", [])),
            length=int(data.get("length", 0) or 0),
            snippet=data.get("snippet", ""),
            redirected_from=data.get("redirected_from"),
            guide_like=bool(data.get("guide_like", False)),
            guide_sections=[GuideSection.from_dict(item) for item in data.get("guide_sections", [])],
            entity_type=data.get("entity_type", "unknown"),
            infobox_fields=dict(data.get("infobox_fields", {})),
            recipes=[StructuredRecipe.from_dict(item) for item in data.get("recipes", [])],
            used_in=[StructuredRecipe.from_dict(item) for item in data.get("used_in", [])],
            transmutations=[StructuredRecipe.from_dict(item) for item in data.get("transmutations", [])],
            structured_summary=list(data.get("structured_summary", [])),
        )


@dataclass(slots=True)
class LookupResult:
    article: WikiArticle
    alternative_titles: list[str] = field(default_factory=list)
    exact_match: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "LookupResult":
        return cls(
            article=WikiArticle.from_dict(data.get("article", {})),
            alternative_titles=list(data.get("alternative_titles", [])),
            exact_match=bool(data.get("exact_match", False)),
        )


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    value: T
    expires_at: float
