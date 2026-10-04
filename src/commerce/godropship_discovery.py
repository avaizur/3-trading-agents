"""Conservative read-only discovery from public Go Dropship pages."""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from src.commerce.schemas import ProductLane, SupplierBackedProduct


BASE_URL = "https://www.godropship.co.uk"

SOURCE_URLS = (
    f"{BASE_URL}/topsellers.html",
    f"{BASE_URL}/newArrivals.html",
    f"{BASE_URL}/household-supplies",
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; 3-Trading-Agents/1.0; "
    "+supplier-market-research)"
)

# Conservative Phase-1 exclusions.
EXCLUDED_TERMS = {
    "incontinence",
    "medical",
    "medicine",
    "rat trap",
    "mouse trap",
    "glue trap",
    "insect killer",
    "fly catcher",
    "pesticide",
    "chemical",
    "slipper",
    "socks",
    "shoe",
    "shoes",
    "clothing",
    "underwear",
    "battery",
    "charger",
    "mains",
    "electrical",
}

SEASONAL_TERMS = {
    "christmas",
    "xmas",
    "halloween",
    "easter",
}


@dataclass(frozen=True)
class DiscoveredSupplierProduct:
    sku: str
    title: str
    cost: float
    stock: int
    url: str
    lane: ProductLane


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "a":
            return

        values = dict(attrs)
        href = values.get("href")

        if href:
            self._href = href
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "a" and self._href is not None:
            text = " ".join(self._text).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def _fetch(url: str, timeout: int = 10) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _plain_text(document: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", document, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _product_links(document: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(document)

    result: list[str] = []
    seen: set[str] = set()

    ignored_paths = {
        "/",
        "/topsellers.html",
        "/newArrivals.html",
        "/household-supplies",
        "/faq",
        "/user-guide",
    }

    for href, text in parser.links:
        absolute = urljoin(BASE_URL, href)
        parsed = urlparse(absolute)

        if parsed.netloc not in {"www.godropship.co.uk", "godropship.co.uk"}:
            continue

        if parsed.path in ignored_paths:
            continue

        if len(text.strip()) < 15:
            continue

        if absolute in seen:
            continue

        seen.add(absolute)
        result.append(absolute)

    return result


def _parse_product_page(url: str, document: str) -> DiscoveredSupplierProduct | None:
    text = _plain_text(document)

    sku_match = re.search(
        r"Item\s*Code\s*:\s*([A-Za-z0-9_-]+)",
        text,
        re.I,
    )

    stock_match = re.search(
        r"UK\s*Stock\s*:\s*(\d+)",
        text,
        re.I,
    )

    price_match = re.search(
        r"Price\s*:\s*£\s*([0-9]+(?:\.[0-9]{1,2})?)",
        text,
        re.I,
    )

    if not (sku_match and stock_match and price_match):
        return None

    title_match = re.search(
        r"<h1[^>]*>(.*?)</h1>",
        document,
        re.I | re.S,
    )

    if not title_match:
        title_match = re.search(
            r"<h2[^>]*>(.*?)</h2>",
            document,
            re.I | re.S,
        )

    if not title_match:
        return None

    title = _plain_text(title_match.group(1)).strip()
    sku = sku_match.group(1).strip()
    stock = int(stock_match.group(1))
    cost = float(price_match.group(1))

    title_lower = title.casefold()

    if any(term in title_lower for term in EXCLUDED_TERMS):
        return None

    # Phase 1 economics hunting range.
    if not 4.00 <= cost <= 15.00:
        return None

    if stock < 25:
        return None

    lane = (
        ProductLane.SEASONAL
        if any(term in title_lower for term in SEASONAL_TERMS)
        else ProductLane.EVERGREEN
    )

    return DiscoveredSupplierProduct(
        sku=sku,
        title=title,
        cost=cost,
        stock=stock,
        url=url,
        lane=lane,
    )


def discover_products(
    *,
    max_products: int = 20,
    request_pause_seconds: float = 0.15,
) -> list[DiscoveredSupplierProduct]:
    """Discover a bounded conservative batch from public Go Dropship pages."""

    candidate_links: list[str] = []
    seen_links: set[str] = set()

    for source_url in SOURCE_URLS:
        try:
            page = _fetch(source_url)
        except Exception:
            continue

        for link in _product_links(page):
            if link not in seen_links:
                seen_links.add(link)
                candidate_links.append(link)

    products: list[DiscoveredSupplierProduct] = []
    seen_skus: set[str] = set()

    # Bound network work. We do not crawl the whole site.
    for link in candidate_links[:80]:
        if len(products) >= max_products:
            break

        try:
            page = _fetch(link)
            product = _parse_product_page(link, page)
        except Exception:
            product = None

        if product and product.sku not in seen_skus:
            seen_skus.add(product.sku)
            products.append(product)

        if request_pause_seconds:
            time.sleep(request_pause_seconds)

    return products


def save_new_products(store, products) -> dict:
    imported = 0
    existing = 0

    for item in products:
        current = store.get_supplier_backed_product(
            "Go Dropship",
            item.sku,
        )

        if current is not None:
            existing += 1
            continue

        now = datetime.now(timezone.utc)

        product = SupplierBackedProduct(
            supplier_name="Go Dropship",
            supplier_sku=item.sku,
            product_name=item.title,
            supplier_cost=item.cost,
            lane=item.lane,
            created_at=now,
            updated_at=now,
        )

        store.save_supplier_backed_product(product)
        imported += 1

    return {
        "discovered": len(products),
        "imported": imported,
        "already_present": existing,
    }
