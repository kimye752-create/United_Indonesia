"""e-Katalog LKPP 의약품 조달가 크롤러 (단순화).

대상: https://e-katalog.lkpp.go.id/
방식: httpx 정적 HTML + JSON API 엔드포인트 시도

수집 필드:
  - product_name  : 제품명
  - inn           : 성분명
  - price_idr     : 조달 단가 (Harga Satuan, IDR)
  - satuan        : 단위 (정, 캡슐, mL 등)
  - supplier      : 공급업체
  - year          : 연도
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "id-ID,id;q=0.9",
    "Referer": "https://e-katalog.lkpp.go.id/",
}

# e-Katalog 내부 API 엔드포인트 (공개 검색 API)
_SEARCH_API = "https://e-katalog.lkpp.go.id/api/products/search"
_SEARCH_WEB = "https://e-katalog.lkpp.go.id/produk"


def _parse_price_idr(text: str) -> int | None:
    """'Rp 15.000' 또는 '15000' 형태를 정수로 변환."""
    cleaned = re.sub(r"[Rp\s\.]", "", text).replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


async def search_ekatalog(
    keyword: str,
    max_results: int = 10,
    category: str = "obat",
) -> list[dict[str, Any]]:
    """e-Katalog에서 성분명 또는 제품명으로 조달가 검색.

    Args:
        keyword: 검색어 (INN 성분명 권장)
        max_results: 최대 반환 건수
        category: 카테고리 필터 ('obat' = 의약품)

    Returns:
        조달가 정보 딕셔너리 리스트
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_HEADERS,
        follow_redirects=True,
    ) as client:

        # 1차 시도: JSON API
        try:
            api_resp = await client.get(
                _SEARCH_API,
                params={
                    "q": keyword,
                    "category": category,
                    "per_page": max_results,
                },
            )
            if api_resp.status_code == 200:
                data = api_resp.json()
                items = data.get("data", data.get("items", data.get("results", [])))
                for item in items[:max_results]:
                    price_raw = item.get("harga_satuan") or item.get("price") or 0
                    results.append({
                        "product_name": item.get("nama_produk") or item.get("name", ""),
                        "inn":          item.get("zat_aktif") or item.get("inn", ""),
                        "price_idr":    int(price_raw) if price_raw else 0,
                        "satuan":       item.get("satuan") or item.get("unit", ""),
                        "supplier":     item.get("penyedia") or item.get("supplier", ""),
                        "year":         str(item.get("tahun") or item.get("year", "")),
                        "source":       "e-Katalog LKPP (API)",
                        "keyword":      keyword,
                    })
                if results:
                    return results
        except Exception:
            pass

        # 2차 시도: HTML 파싱
        try:
            web_resp = await client.get(
                _SEARCH_WEB,
                params={"q": keyword, "kategori": category},
            )
            web_resp.raise_for_status()
            soup = BeautifulSoup(web_resp.text, "html.parser")

            # 일반적인 테이블/카드 구조 파싱 시도
            rows = soup.select("table tbody tr") or soup.select(".product-item")
            for row in rows[:max_results]:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cols:
                    # 카드 구조
                    name = row.select_one(".product-name, h3, .name")
                    price_el = row.select_one(".price, .harga")
                    cols = [
                        name.get_text(strip=True) if name else "",
                        price_el.get_text(strip=True) if price_el else "",
                    ]

                price_idr = _parse_price_idr(cols[1]) if len(cols) > 1 else None
                results.append({
                    "product_name": cols[0] if cols else "",
                    "inn":          cols[2] if len(cols) > 2 else "",
                    "price_idr":    price_idr or 0,
                    "satuan":       cols[3] if len(cols) > 3 else "",
                    "supplier":     cols[4] if len(cols) > 4 else "",
                    "year":         "",
                    "source":       "e-Katalog LKPP (HTML)",
                    "keyword":      keyword,
                })
        except Exception as exc:
            results.append({
                "product_name": "",
                "inn":          keyword,
                "price_idr":    0,
                "satuan":       "",
                "supplier":     "",
                "year":         "",
                "source":       "e-Katalog LKPP",
                "keyword":      keyword,
                "error":        str(exc)[:120],
            })

    return results


def compute_price_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """조달가 통계 (최저/최고/중간값) 산출."""
    prices = [r["price_idr"] for r in rows if r.get("price_idr", 0) > 0]
    if not prices:
        return {"min": None, "max": None, "median": None, "count": 0}
    prices_sorted = sorted(prices)
    n = len(prices_sorted)
    median = (
        prices_sorted[n // 2]
        if n % 2
        else (prices_sorted[n // 2 - 1] + prices_sorted[n // 2]) // 2
    )
    return {
        "min":    prices_sorted[0],
        "max":    prices_sorted[-1],
        "median": median,
        "count":  n,
    }
