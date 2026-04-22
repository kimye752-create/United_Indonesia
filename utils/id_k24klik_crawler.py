"""
id_k24klik_crawler.py — K24Klik 온라인 약국 가격 크롤러

대상: https://www.k24klik.com/cariObat/{keyword}
방식: 정적 HTML 파싱  (li.product 카드 구조 — 초기 렌더링에 포함됨)
      Fallback: /product/prodSuggest POST (이름 + product_id 수집)

수집 필드:
  - product_name  : 제품명
  - price_idr     : 소매가 (IDR, 단위가 있는 경우 단위 가격)
  - price_unit    : 가격 단위 (예: "/Tablet")
  - product_url   : 상세 페이지 URL
  - source        : "K24Klik"
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from utils.id_antibot import pick_ua
from utils.id_normalizer import normalize_record, normalize_price_idr

logger = logging.getLogger(__name__)

_BASE_URL   = "https://www.k24klik.com"
_TIMEOUT    = 20.0
_DELAY      = 1.5


def _make_headers(referer: str = _BASE_URL) -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Referer": referer,
    }


def _parse_price_and_unit(text: str) -> tuple[int | None, str]:
    """'Rp2.955 /Tablet' → (2955, '/Tablet')"""
    if not text:
        return None, ""
    # Extract unit (text after the price number)
    unit_match = re.search(r'(/\S+)', text)
    unit = unit_match.group(1) if unit_match else ""
    price = normalize_price_idr(text)
    return price, unit


def _parse_product_cards(html: str, keyword: str) -> list[dict[str, Any]]:
    """li.product 카드 파싱 (K24Klik /cariObat/ 페이지)."""
    soup    = BeautifulSoup(html, "html.parser")
    results = []

    for li in soup.find_all("li", class_="product"):
        # 제품명: class="k24-width-100" (div)
        # 가장 짧은 k24-width-100 div가 상품명을 담고 있음
        name = ""
        for div in li.find_all("div", class_="k24-width-100"):
            txt = div.get_text(strip=True)
            # 가격 또는 배지 텍스트는 제외
            if txt and "Rp" not in txt and len(txt) > 3 and len(txt) < 120:
                # Skip badge-like texts
                if not any(x in txt.upper() for x in ["TERLARIS", "DISKON", "PROMO", "BARU", "SALE"]):
                    name = txt
                    break

        if not name:
            continue

        # 가격: k24-color-prim 이 포함된 span/div
        price_idr, price_unit = None, ""
        price_el = li.find(class_=re.compile(r"k24-color-prim", re.I))
        if price_el:
            price_idr, price_unit = _parse_price_and_unit(price_el.get_text(strip=True))

        # 상품 URL
        detail_url = ""
        onclick_el = li.find(attrs={"onclick": re.compile(r"product/\d+", re.I)})
        if onclick_el:
            m = re.search(r"'(https://[^']+product/\d+)'", onclick_el.get("onclick", ""))
            if m:
                detail_url = m.group(1)
        if not detail_url:
            a = li.find("a", href=re.compile(r"/product/\d+", re.I))
            if a:
                detail_url = a["href"]
                if not detail_url.startswith("http"):
                    detail_url = _BASE_URL + detail_url

        raw = {
            "product_name": name,
            "price_idr":    price_idr,
            "price_unit":   price_unit,
            "detail_url":   detail_url,
            "source":       "K24Klik",
            "keyword":      keyword,
            "confidence":   0.78,
        }
        results.append(normalize_record(raw))

    return results


def _parse_suggest_html(html: str, keyword: str) -> list[dict[str, Any]]:
    """prodSuggest POST 응답 HTML 파싱 (이름만 있음, 가격 없음)."""
    soup    = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", onclick=re.compile(r"product/\d+")):
        m = re.search(r"'(https://[^']+product/(\d+))'", a.get("onclick", ""))
        if not m:
            continue
        detail_url  = m.group(1)
        name_el     = a.find(class_=re.compile(r"name|text", re.I))
        name        = name_el.get_text(strip=True) if name_el else a.get_text(strip=True)
        if not name or len(name) < 3:
            continue
        raw = {
            "product_name": name,
            "price_idr":    None,
            "detail_url":   detail_url,
            "source":       "K24Klik",
            "keyword":      keyword,
            "confidence":   0.65,   # 가격 없음 → 낮은 신뢰도
        }
        results.append(normalize_record(raw))

    return results


async def search_k24klik(
    keyword: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """K24Klik에서 제품명/성분명 검색.

    Args:
        keyword     : 검색어 (INN 또는 브랜드명)
        max_results : 최대 반환 건수
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_make_headers(),
        follow_redirects=True,
    ) as client:
        # ── 1단계: /cariObat/{keyword} HTML 파싱 (가격 포함) ──────────
        try:
            url  = f"{_BASE_URL}/cariObat/{quote(keyword)}"
            resp = await client.get(url)
            if resp.status_code == 200 and "li" in resp.text:
                parsed = _parse_product_cards(resp.text, keyword)
                if parsed:
                    results.extend(parsed[:max_results])
        except Exception as exc:
            logger.debug("K24Klik cariObat 실패: %s", exc)

        # ── 2단계: prodSuggest fallback (이름만, 가격 없음) ───────────
        if not results:
            try:
                # CSRF 토큰 필요
                home_resp = await client.get(_BASE_URL)
                csrf_m    = re.search(
                    r'csrfToken["\s:=]+["\']([a-f0-9]+)["\']',
                    home_resp.text,
                )
                csrf_token = csrf_m.group(1) if csrf_m else ""

                sug_resp = await client.post(
                    f"{_BASE_URL}/product/prodSuggest",
                    data={"keyword": keyword, "csrfToken": csrf_token},
                    headers={
                        **_make_headers(referer=f"{_BASE_URL}/cariObat/{quote(keyword)}"),
                        "Accept": "text/html, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                if sug_resp.status_code == 200:
                    parsed = _parse_suggest_html(sug_resp.text, keyword)
                    if parsed:
                        results.extend(parsed[:max_results])
            except Exception as exc:
                logger.debug("K24Klik prodSuggest 실패: %s", exc)

    if not results:
        results.append({
            "product_name": "", "price_idr": None,
            "source": "K24Klik", "keyword": keyword,
            "error": "검색 결과 없음",
        })
    return results[:max_results]


async def batch_search_k24klik(
    keywords: list[str],
    max_results_each: int = 10,
    delay_sec: float = _DELAY,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_k24klik(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
