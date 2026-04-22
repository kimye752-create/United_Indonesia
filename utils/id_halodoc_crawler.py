"""Halodoc 소매 의약품 가격 크롤러 (단순화).

대상: https://www.halodoc.com/obat-dan-vitamin
방식: httpx + JSON (Elasticsearch 기반 내부 API 탐색)
      Playwright 없이 동작하는 공개 엔드포인트 우선 시도

수집 필드:
  - product_name  : 제품명
  - brand         : 브랜드
  - price_idr     : 소매 가격 (IDR)
  - discount_pct  : 할인율 (%)
  - unit          : 단위
  - is_rx         : 처방약 여부
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "id-ID,id;q=0.9",
    "Origin": "https://www.halodoc.com",
    "Referer": "https://www.halodoc.com/obat-dan-vitamin",
}

# Halodoc 내부 검색 API (공개 탐색)
_SEARCH_ENDPOINTS = [
    "https://www.halodoc.com/api/v1/pharmacy/products/search",
    "https://api.halodoc.com/pharmacy/v1/products/search",
]
_SEARCH_WEB = "https://www.halodoc.com/obat-dan-vitamin/search"


def _parse_price(raw: Any) -> int:
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw)
    cleaned = re.sub(r"[Rp\s\.]", "", text).replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return 0


async def search_halodoc(
    keyword: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Halodoc에서 의약품 소매가 검색.

    Args:
        keyword: 검색어 (제품명 또는 INN)
        max_results: 최대 반환 건수

    Returns:
        소매가 정보 딕셔너리 리스트
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_HEADERS,
        follow_redirects=True,
    ) as client:

        # 1차 시도: 내부 JSON API
        for api_url in _SEARCH_ENDPOINTS:
            try:
                resp = await client.get(
                    api_url,
                    params={"q": keyword, "limit": max_results, "page": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = (
                        data.get("data")
                        or data.get("products")
                        or data.get("items")
                        or []
                    )
                    for item in items[:max_results]:
                        price_raw = (
                            item.get("price")
                            or item.get("sell_price")
                            or item.get("original_price")
                            or 0
                        )
                        disc_price = item.get("discounted_price") or item.get("discount_price") or 0
                        original = _parse_price(price_raw)
                        discounted = _parse_price(disc_price)
                        disc_pct = 0
                        if original > 0 and discounted > 0 and discounted < original:
                            disc_pct = round((original - discounted) / original * 100)

                        results.append({
                            "product_name": item.get("name") or item.get("product_name", ""),
                            "brand":        item.get("brand") or item.get("manufacturer", ""),
                            "price_idr":    original,
                            "discount_pct": disc_pct,
                            "unit":         item.get("unit") or item.get("satuan", ""),
                            "is_rx":        bool(item.get("is_prescription") or item.get("rx")),
                            "source":       "Halodoc (API)",
                            "keyword":      keyword,
                        })
                    if results:
                        return results
            except Exception:
                continue

        # 2차 시도: HTML 파싱 (모바일 UA)
        try:
            web_resp = await client.get(
                _SEARCH_WEB,
                params={"q": keyword},
            )
            if web_resp.status_code == 200:
                soup = BeautifulSoup(web_resp.text, "html.parser")

                # JSON-LD 또는 __NEXT_DATA__ 스크립트에서 데이터 추출
                import json
                for script in soup.find_all("script", {"id": "__NEXT_DATA__"}):
                    try:
                        next_data = json.loads(script.string or "")
                        props = next_data.get("props", {}).get("pageProps", {})
                        products = props.get("products") or props.get("searchResults") or []
                        for p in products[:max_results]:
                            results.append({
                                "product_name": p.get("name", ""),
                                "brand":        p.get("brand", ""),
                                "price_idr":    _parse_price(p.get("price", 0)),
                                "discount_pct": 0,
                                "unit":         p.get("unit", ""),
                                "is_rx":        bool(p.get("isRx")),
                                "source":       "Halodoc (Next.js SSR)",
                                "keyword":      keyword,
                            })
                        if results:
                            return results
                    except Exception:
                        pass

                # 최후 폴백: 카드 요소 텍스트 추출
                cards = soup.select("[data-testid='product-card'], .product-card, article")
                for card in cards[:max_results]:
                    name_el = card.select_one("h3, .name, [data-testid='product-name']")
                    price_el = card.select_one(".price, [data-testid='product-price']")
                    results.append({
                        "product_name": name_el.get_text(strip=True) if name_el else "",
                        "brand":        "",
                        "price_idr":    _parse_price(price_el.get_text(strip=True)) if price_el else 0,
                        "discount_pct": 0,
                        "unit":         "",
                        "is_rx":        False,
                        "source":       "Halodoc (HTML fallback)",
                        "keyword":      keyword,
                    })
        except Exception as exc:
            results.append({
                "product_name": "",
                "brand":        "",
                "price_idr":    0,
                "discount_pct": 0,
                "unit":         "",
                "is_rx":        False,
                "source":       "Halodoc",
                "keyword":      keyword,
                "error":        str(exc)[:120],
            })

    if not results:
        results.append({
            "product_name": "", "brand": "", "price_idr": 0,
            "source": "Halodoc", "keyword": keyword,
            "error": "검색 결과 없음 — Halodoc SPA 앱 인증 필요 (모바일 앱 API)",
        })
    return results


def compute_margin_spread(
    ekatalog_price: int,
    retail_price: int,
) -> dict[str, Any]:
    """e-Katalog 조달가와 Halodoc 소매가 간 마진 스프레드 산출.

    Value Chain: 공장 → PBF(도매) → 병원/약국 → 환자
    일반적 마진율: PBF ~15-20%, 약국 ~20-30%
    """
    if ekatalog_price <= 0 or retail_price <= 0:
        return {"spread_idr": None, "spread_pct": None}

    spread_idr = retail_price - ekatalog_price
    spread_pct = round(spread_idr / ekatalog_price * 100, 1)

    # 역산: 공장 출고가 추정 (e-Katalog 기준 PBF 마진 ~17% 가정)
    estimated_fob_idr = round(ekatalog_price / 1.17)

    return {
        "ekatalog_price_idr":  ekatalog_price,
        "retail_price_idr":    retail_price,
        "spread_idr":          spread_idr,
        "spread_pct":          spread_pct,
        "estimated_fob_idr":   estimated_fob_idr,
        "pbf_margin_note":     "PBF 마진 약 17% 가정 (역산 추정치)",
    }
