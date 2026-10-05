"""Build verified eBay listing facts from supplier and eBay metadata."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from src.commerce.ebay_inventory_service import load_access_token


TAXONOMY_BASE = "https://api.ebay.com/commerce/taxonomy/v1"


def _request_json(
    url: str,
    token: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Accept-Language": "en-GB",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def get_uk_category_tree_id(token: str) -> str:
    query = urllib.parse.urlencode(
        {
            "marketplace_id": "EBAY_GB",
        }
    )

    payload = _request_json(
        f"{TAXONOMY_BASE}/get_default_category_tree_id?{query}",
        token,
    )

    tree_id = payload.get("categoryTreeId")

    if not tree_id:
        raise RuntimeError(
            "eBay did not return a UK category tree ID."
        )

    return str(tree_id)


def suggest_category(
    *,
    title: str,
    token: str,
    category_tree_id: str,
) -> dict[str, str]:
    query = urllib.parse.urlencode(
        {
            "q": title,
        }
    )

    payload = _request_json(
        (
            f"{TAXONOMY_BASE}/category_tree/"
            f"{category_tree_id}/get_category_suggestions?"
            f"{query}"
        ),
        token,
    )

    suggestions = payload.get(
        "categorySuggestions",
        [],
    )

    if not suggestions:
        raise RuntimeError(
            "eBay returned no category suggestion."
        )

    category = suggestions[0].get(
        "category",
        {},
    )

    category_id = category.get("categoryId")
    category_name = category.get("categoryName")

    if not category_id:
        raise RuntimeError(
            "eBay category suggestion has no category ID."
        )

    return {
        "category_id": str(category_id),
        "category_name": str(category_name or ""),
    }


def get_category_aspects(
    *,
    category_id: str,
    token: str,
    category_tree_id: str,
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "category_id": category_id,
        }
    )

    payload = _request_json(
        (
            f"{TAXONOMY_BASE}/category_tree/"
            f"{category_tree_id}/"
            f"get_item_aspects_for_category?"
            f"{query}"
        ),
        token,
    )

    return list(
        payload.get("aspects", [])
    )


def required_aspect_names(
    aspects: list[dict[str, Any]],
) -> list[str]:
    names = []

    for aspect in aspects:
        constraints = aspect.get(
            "aspectConstraint",
            {},
        )

        if constraints.get(
            "aspectRequired"
        ) is True:
            name = aspect.get(
                "localizedAspectName"
            )

            if name:
                names.append(
                    str(name)
                )

    return names


def extract_supplier_images(
    document: str,
    *,
    product_title: str,
) -> list[str]:
    """Return only Go Dropship images belonging to this product gallery."""

    expected_alt = _normalized(product_title)

    class ProductImageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag.casefold() != "img":
                return

            values = dict(attrs)
            src = str(values.get("src") or "").strip()
            alt = str(values.get("alt") or "").strip()

            if not src:
                return

            src_lower = src.casefold()

            if "godropship.co.uk/uploadfile/" not in src_lower:
                return

            if "/thumbnail_" in src_lower or "thumbnail_" in src_lower:
                return

            if _normalized(alt) != expected_alt:
                return

            self.images.append(src)

    parser = ProductImageParser()
    parser.feed(html.unescape(document))

    result: list[str] = []
    seen: set[str] = set()

    for url in parser.images:
        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result[:12]


def build_listing_metadata(
    *,
    title: str,
    supplier_html: str,
) -> dict[str, Any]:
    token = load_access_token()

    tree_id = get_uk_category_tree_id(
        token,
    )

    category = suggest_category(
        title=title,
        token=token,
        category_tree_id=tree_id,
    )

    aspects = get_category_aspects(
        category_id=category["category_id"],
        token=token,
        category_tree_id=tree_id,
    )

    images = extract_supplier_images(
        supplier_html,
        product_title=title,
    )

    return {
        "ebay_title": title[:80],
        "ebay_category_id": (
            category["category_id"]
        ),
        "ebay_category_name": (
            category["category_name"]
        ),
        "image_urls": images,
        "condition": "NEW",
        "required_aspects": (
            required_aspect_names(
                aspects
            )
        ),
        "taxonomy_aspects": aspects,
    }


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def resolve_required_aspects(
    *,
    title: str,
    supplier_html: str,
    taxonomy_aspects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve required aspects only when supplier evidence is unambiguous."""

    normalized_title = _normalized(title)
    supplier_text = _plain_supplier_text(supplier_html)

    resolved: dict[str, list[str]] = {}
    missing: list[str] = []

    for aspect in taxonomy_aspects:
        constraints = aspect.get("aspectConstraint", {})

        if constraints.get("aspectRequired") is not True:
            continue

        name = str(
            aspect.get("localizedAspectName") or ""
        ).strip()

        if not name:
            continue

        values = [
            str(item.get("localizedValue") or "").strip()
            for item in aspect.get("aspectValues", [])
            if item.get("localizedValue")
        ]

        # Brand must have explicit labelled supplier evidence.
        # Never infer a brand merely because its name appears somewhere
        # in navigation, marketing text, or unrelated page content.
        if name.casefold() == "brand":
            brand_match = re.search(
                r"\bbrand\s*[:\-]\s*([^|,;]+)",
                supplier_text,
                flags=re.I,
            )

            if brand_match:
                labelled_brand = _normalized(
                    brand_match.group(1)
                )

                matching_values = [
                    value
                    for value in values
                    if _normalized(value) == labelled_brand
                ]

                if len(matching_values) == 1:
                    resolved[name] = [matching_values[0]]
                    continue

            missing.append(name)
            continue

        # Prefer the most-specific exact allowed value appearing in title.
        title_matches = [
            value
            for value in values
            if _normalized(value)
            and re.search(
                rf"\b{re.escape(_normalized(value))}\b",
                normalized_title,
            )
        ]

        if title_matches:
            title_matches.sort(
                key=lambda value: len(_normalized(value)),
                reverse=True,
            )
            resolved[name] = [title_matches[0]]
            continue

        missing.append(name)

    return {
        "resolved": resolved,
        "missing": missing,
        "complete": not missing,
    }


def _plain_supplier_text(document: str) -> str:
    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        document,
        flags=re.I | re.S,
    )
    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def build_verified_listing_facts(
    *,
    title: str,
    supplier_html: str,
) -> dict[str, Any]:
    metadata = build_listing_metadata(
        title=title,
        supplier_html=supplier_html,
    )

    aspect_result = resolve_required_aspects(
        title=title,
        supplier_html=supplier_html,
        taxonomy_aspects=metadata["taxonomy_aspects"],
    )

    return {
        "ebay_title": metadata["ebay_title"],
        "ebay_category_id": metadata["ebay_category_id"],
        "ebay_category_name": metadata["ebay_category_name"],
        "image_urls": metadata["image_urls"],
        "condition": metadata["condition"],
        "aspects": aspect_result["resolved"],
        "missing_required_aspects": aspect_result["missing"],
        "listing_facts_complete": aspect_result["complete"],
    }
