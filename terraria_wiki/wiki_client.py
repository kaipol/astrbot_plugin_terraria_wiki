import asyncio
from typing import Optional

import aiohttp

from .config import (
    CARGO_QUERY_LIMIT,
    GUIDE_NAMESPACE_NAME,
    GUIDE_PAGE_LENGTH_THRESHOLD,
    GUIDE_SECTION_SUMMARY_LIMIT,
    SEARCH_CANDIDATE_LIMIT,
    SUMMARY_LENGTH_LIMIT,
    THUMBNAIL_WIDTH,
    WIKI_API_URL,
)
from .guide_support import (
    build_guide_sections,
    clean_snippet,
    is_guide_like,
    select_key_sections,
    summarize_parsed_html,
    summarize_wikitext,
)
from .models import LookupResult, WikiArticle
from .ranking import normalize_text, pick_best_result
from .rendering import build_page_url
from .structured_support import (
    build_structured_payload,
    cargo_query_params,
    normalize_cargo_text,
    parse_ingredient_parts,
    unwrap_cargo_rows,
)


class WikiClient:
    def __init__(self, session: aiohttp.ClientSession, page_cache=None, search_cache=None, guide_cache=None, redirect_cache=None):
        self._session = session
        self._page_cache = page_cache
        self._search_cache = search_cache
        self._guide_cache = guide_cache
        self._redirect_cache = redirect_cache

    async def fetch_json(self, params: dict) -> dict:
        async with self._session.get(WIKI_API_URL, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def lookup(self, query: str) -> Optional[LookupResult]:
        search_results = await self._fetch_search_results(query)
        selection = pick_best_result(query, search_results)
        if selection is None:
            return None

        article = await self.fetch_article(selection.title, snippet=selection.snippet)
        alternative_titles = selection.alternative_titles
        exact_match = selection.exact_match

        if self._is_disambiguation(article) and alternative_titles:
            fallback_title = alternative_titles[0]
            fallback_article = await self.fetch_article(fallback_title)
            alternative_titles = [article.title, *alternative_titles[1:]]
            article = fallback_article
            exact_match = False

        return LookupResult(
            article=article,
            alternative_titles=alternative_titles,
            exact_match=exact_match,
        )

    async def _fetch_search_results(self, query: str) -> list[dict]:
        cache_key = normalize_text(query)
        if self._search_cache is not None:
            cached = self._search_cache.get(cache_key)
            if cached is not None:
                return cached

        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": SEARCH_CANDIDATE_LIMIT,
            "srprop": "snippet|size|wordcount",
            "srnamespace": "0|110",
            "format": "json",
            "utf8": 1,
        }
        search_data = await self.fetch_json(search_params)
        results = search_data.get("query", {}).get("search", [])

        if self._search_cache is not None:
            self._search_cache.set(cache_key, results)
        return results

    async def fetch_article(self, title: str, snippet: str = "") -> WikiArticle:
        redirect_key = normalize_text(title)
        resolved_title = title
        redirected_from = None

        if self._redirect_cache is not None:
            redirect_entry = self._redirect_cache.get(redirect_key)
            if redirect_entry is not None:
                resolved_title = redirect_entry.get("resolved_title") or title
                redirected_from = redirect_entry.get("redirected_from")

        cache_key = normalize_text(resolved_title)
        if self._page_cache is not None:
            cached = self._page_cache.get(cache_key)
            if cached is not None:
                if snippet and not cached.snippet:
                    cached.snippet = clean_snippet(snippet)
                return cached

        article_params = {
            "action": "query",
            "titles": resolved_title,
            "redirects": 1,
            "prop": "info|pageimages|categories|revisions",
            "inprop": "url",
            "piprop": "thumbnail",
            "pithumbsize": THUMBNAIL_WIDTH,
            "cllimit": "max",
            "rvslots": "main",
            "rvprop": "content",
            "rvsection": 0,
            "format": "json",
            "formatversion": 2,
            "utf8": 1,
        }
        article_data = await self.fetch_json(article_params)
        query = article_data.get("query", {})
        redirects = query.get("redirects", [])
        if redirects:
            redirected_from = redirects[0].get("from") or redirected_from

        pages = query.get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        page = next(iter(pages), {})
        if page.get("missing"):
            raise ValueError(f"Wiki page not found: {title}")

        canonical_title = page.get("title", resolved_title)
        if self._redirect_cache is not None:
            self._redirect_cache.set(
                redirect_key,
                {"resolved_title": canonical_title, "redirected_from": redirected_from},
            )

        lead_wikitext = self._extract_revision_content(page)
        categories = self._extract_categories(page)
        canonical_url = page.get("canonicalurl") or build_page_url(canonical_title)
        length = int(page.get("length", 0) or 0)
        thumbnail_url = (page.get("thumbnail") or {}).get("source")
        raw_sections = await self.fetch_sections(canonical_title)
        lead_html = await self.fetch_parsed_html(canonical_title)
        guide_like = is_guide_like(canonical_title, categories, length, len(raw_sections))
        guide_sections = []
        if guide_like:
            guide_sections = await self.fetch_guide_sections(canonical_title, canonical_url, raw_sections)

        structured_payload = await self.fetch_structured_payload(canonical_title, categories)
        extract = summarize_parsed_html(lead_html, SUMMARY_LENGTH_LIMIT * 2) or summarize_wikitext(
            lead_wikitext, SUMMARY_LENGTH_LIMIT * 2
        ) or clean_snippet(snippet)

        article = WikiArticle(
            title=canonical_title,
            extract=extract,
            thumbnail_url=thumbnail_url,
            page_id=page.get("pageid"),
            canonical_url=canonical_url,
            categories=categories,
            length=length,
            snippet=clean_snippet(snippet),
            redirected_from=redirected_from,
            guide_like=guide_like,
            guide_sections=guide_sections,
            entity_type=structured_payload["entity_type"],
            infobox_fields=structured_payload["infobox_fields"],
            recipes=structured_payload["recipes"],
            used_in=structured_payload["used_in"],
            transmutations=structured_payload.get("transmutations", []),
            structured_summary=structured_payload["structured_summary"],
        )

        if self._page_cache is not None:
            self._page_cache.set(normalize_text(canonical_title), article)

        return article

    async def fetch_structured_payload(self, title: str, categories: list[str]) -> dict:
        safe_title = self._escape_cargo_text(title)
        item_rows = unwrap_cargo_rows(
            await self.fetch_json(
                cargo_query_params(
                    "Items",
                    "_pageName=page,name,itemid,internalname,imagefile,damage,defense,knockback,usetime,damagetype,rare,buy,sell,stack,type,listcat,tooltip",
                    f"_pageName='{safe_title}'",
                    limit=1,
                )
            )
        )
        item_row = item_rows[0] if item_rows else None
        item_id = normalize_cargo_text((item_row or {}).get("itemid"))
        item_name = normalize_cargo_text((item_row or {}).get("name"))
        if not item_id or not item_name:
            return build_structured_payload(title, categories, item_rows, [], [])

        recipe_rows = unwrap_cargo_rows(
            await self.fetch_json(
                cargo_query_params(
                    "Recipes,Items",
                    "Recipes.result=result,Recipes.resultid=resultid,Recipes.amount=amount,Recipes.station=station,Recipes.ingredients=ingredients,Recipes.ings=ings,Recipes.version=version,Recipes.legacy=legacy,Items._pageName=result_page,Items.imagefile=result_imagefile",
                    f"Recipes.resultid='{self._escape_cargo_text(item_id)}'",
                    limit=CARGO_QUERY_LIMIT,
                    join_on="Recipes.resultid=Items.itemid",
                )
            )
        )
        used_in_rows = unwrap_cargo_rows(
            await self.fetch_json(
                cargo_query_params(
                    "Recipes,Items",
                    "Recipes.result=result,Recipes.resultid=resultid,Recipes.amount=amount,Recipes.station=station,Recipes.ingredients=ingredients,Recipes.ings=ings,Recipes.version=version,Recipes.legacy=legacy,Items._pageName=result_page,Items.imagefile=result_imagefile",
                    f"Recipes.ingredients HOLDS '¦{self._escape_cargo_text(item_name)}¦'",
                    limit=CARGO_QUERY_LIMIT,
                    join_on="Recipes.resultid=Items.itemid",
                )
            )
        )

        related_item_rows = await self._fetch_related_item_rows(recipe_rows, used_in_rows)
        image_lookup = await self._fetch_image_lookup(item_rows, recipe_rows, used_in_rows, related_item_rows)
        item_lookup = {normalize_cargo_text(row.get("name")): row for row in related_item_rows if normalize_cargo_text(row.get("name"))}
        enriched_recipe_rows = self._enrich_recipe_rows(recipe_rows, item_lookup, image_lookup)
        enriched_used_in_rows = self._enrich_recipe_rows(used_in_rows, item_lookup, image_lookup)
        return build_structured_payload(title, categories, item_rows, enriched_recipe_rows, enriched_used_in_rows)

    async def _fetch_related_item_rows(self, recipe_rows: list[dict], used_in_rows: list[dict]) -> list[dict]:
        names: set[str] = set()
        for row in [*recipe_rows, *used_in_rows]:
            station = normalize_cargo_text(row.get("station"))
            if station:
                names.add(station)
            for ingredient_name, _ in parse_ingredient_parts(row.get("ings") or row.get("ingredients")):
                if ingredient_name:
                    names.add(ingredient_name)

        if not names:
            return []

        where = "name IN (" + ",".join(f"'{self._escape_cargo_text(name)}'" for name in sorted(names)) + ")"
        return unwrap_cargo_rows(
            await self.fetch_json(
                cargo_query_params(
                    "Items",
                    "name,_pageName=page,imagefile",
                    where,
                    limit=max(len(names), CARGO_QUERY_LIMIT),
                )
            )
        )

    async def _fetch_image_lookup(
        self,
        item_rows: list[dict],
        recipe_rows: list[dict],
        used_in_rows: list[dict],
        related_item_rows: list[dict],
    ) -> dict[str, str]:
        image_files = {
            normalize_cargo_text(row.get("imagefile"))
            for row in [*item_rows, *related_item_rows]
            if normalize_cargo_text(row.get("imagefile"))
        }
        image_files.update(
            normalize_cargo_text(row.get("result_imagefile"))
            for row in [*recipe_rows, *used_in_rows]
            if normalize_cargo_text(row.get("result_imagefile"))
        )
        if not image_files:
            return {}

        data = await self.fetch_json(
            {
                "action": "query",
                "titles": "|".join(f"File:{name}" for name in sorted(image_files)),
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
                "formatversion": 2,
            }
        )
        pages = data.get("query", {}).get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())

        image_lookup: dict[str, str] = {}
        for page in pages:
            title = page.get("title", "")
            if not title.startswith("File:"):
                continue
            image_file = title.split(":", 1)[-1].replace("_", " ")
            image_info = page.get("imageinfo", []) or []
            if image_info and image_info[0].get("url"):
                image_lookup[image_file] = image_info[0]["url"]
        return image_lookup

    def _enrich_recipe_rows(self, rows: list[dict], item_lookup: dict[str, dict], image_lookup: dict[str, str]) -> list[dict]:
        enriched_rows = []
        for row in rows:
            enriched = dict(row)
            result_imagefile = normalize_cargo_text(row.get("result_imagefile"))
            if result_imagefile:
                enriched["result_image_url"] = image_lookup.get(result_imagefile, "")

            station_info = item_lookup.get(normalize_cargo_text(row.get("station")))
            if station_info is not None:
                station_imagefile = normalize_cargo_text(station_info.get("imagefile"))
                enriched["station_page"] = normalize_cargo_text(station_info.get("page"))
                enriched["station_image_url"] = image_lookup.get(station_imagefile, "") if station_imagefile else ""

            ingredient_details = []
            for ingredient_name, amount in parse_ingredient_parts(row.get("ings") or row.get("ingredients")):
                ingredient_info = item_lookup.get(ingredient_name)
                ingredient_page = normalize_cargo_text((ingredient_info or {}).get("page"))
                ingredient_imagefile = normalize_cargo_text((ingredient_info or {}).get("imagefile"))
                ingredient_details.append(
                    {
                        "name": ingredient_page or ingredient_name,
                        "amount": amount,
                        "page": ingredient_page,
                        "image_url": image_lookup.get(ingredient_imagefile, "") if ingredient_imagefile else "",
                    }
                )
            enriched["ingredient_details"] = ingredient_details
            enriched_rows.append(enriched)
        return enriched_rows

    def _escape_cargo_text(self, value: str) -> str:
        return value.replace("'", "\\'")

    async def fetch_parsed_html(self, title: str, section_index: str | None = None) -> str:
        params = {
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "formatversion": 2,
        }
        if section_index is not None:
            params["section"] = section_index
        data = await self.fetch_json(params)
        return data.get("parse", {}).get("text", "") or ""

    async def fetch_sections(self, title: str) -> list[dict]:
        params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
        }
        data = await self.fetch_json(params)
        return data.get("parse", {}).get("sections", [])

    async def _summarize_guide_section(self, title: str, section: dict) -> tuple[str, str]:
        index = str(section.get("index", ""))
        if not index:
            return "", ""

        section_html = await self.fetch_parsed_html(title, section_index=index)
        html_summary = summarize_parsed_html(section_html, GUIDE_SECTION_SUMMARY_LIMIT, allow_full_fallback=False)
        if html_summary:
            return index, html_summary

        section_text = await self.fetch_section_wikitext(title, index)
        return index, summarize_wikitext(section_text, GUIDE_SECTION_SUMMARY_LIMIT)

    async def fetch_guide_sections(self, title: str, base_url: str, raw_sections: list[dict]) -> list:
        cache_key = normalize_text(title)
        if self._guide_cache is not None:
            cached = self._guide_cache.get(cache_key)
            if cached is not None:
                return cached

        selected_sections = select_key_sections(raw_sections)
        tasks = [self._summarize_guide_section(title, section) for section in selected_sections]
        summary_entries = await asyncio.gather(*tasks) if tasks else []
        summaries = {index: summary for index, summary in summary_entries if index and summary}

        guide_sections = build_guide_sections(base_url, selected_sections, summaries)
        if self._guide_cache is not None:
            self._guide_cache.set(cache_key, guide_sections)
        return guide_sections

    async def fetch_section_wikitext(self, title: str, section_index: str) -> str:
        params = {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "rvsection": section_index,
            "format": "json",
            "formatversion": 2,
            "utf8": 1,
        }
        data = await self.fetch_json(params)
        pages = data.get("query", {}).get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        page = next(iter(pages), {})
        return self._extract_revision_content(page)

    def _extract_revision_content(self, page: dict) -> str:
        revisions = page.get("revisions", [])
        if not revisions:
            return ""
        revision = revisions[0]
        slots = revision.get("slots", {})
        if isinstance(slots, dict):
            main_slot = slots.get("main", {})
            return main_slot.get("content", "") or revision.get("content", "") or ""
        return revision.get("content", "") or ""

    def _extract_categories(self, page: dict) -> list[str]:
        categories = []
        for item in page.get("categories", []) or []:
            title = item.get("title", "")
            categories.append(title.split(":", 1)[-1])
        return categories

    def _is_disambiguation(self, article: WikiArticle) -> bool:
        normalized_title = article.title.lower()
        normalized_categories = [item.lower() for item in article.categories]
        return normalized_title.endswith("(消歧义)") or any("消歧义" in item or "disambiguation" in item for item in normalized_categories)
