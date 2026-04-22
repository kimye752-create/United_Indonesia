"""
id_swiperx_crawler.py — SwipeRx B2B 약국 네트워크 크롤러

대상: https://swiperx.com/id  (인도네시아)
방식: 정적 HTML 파싱 + JSON-LD + 내부 API 탐색

SwipeRx는 동남아 최대 B2B 약국 플랫폼 (인도네시아 12,000+ 약국 가입).
도매가·번들 할인·CPD 커뮤니티 데이터 수집.

수집 필드:
  - product_name  : 제품명
  - inn           : 성분명
  - strength      : 함량
  - dosage_form   : 제형
  - price_idr     : 도매가 (IDR)
  - manufacturer  : 제조사
  - category      : 치료 카테고리
  - source        : "SwipeRx"
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from utils.id_antibot import pick_ua
from utils.id_normalizer import normalize_record, normalize_price_idr

logger = logging.getLogger(__name__)

_BASE_URL  = "https://swiperx.com"
_CATALOG_URL = f"{_BASE_URL}/id/catalog"
_TIMEOUT   = 20.0
_DELAY     = 2.0  # B2B 사이트 — 더 보수적인 딜레이


def _make_headers() -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Referer": _BASE_URL,
    }


def _parse_jsonld(html: str, keyword: str) -> list[dict[str, Any]]:
    """JSON-LD Product 스키마 파싱."""
    soup    = BeautifulSoup(html, "html.parser")
    results = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, Exception):
            continue
        items_raw = []
        if isinstance(data, dict):
            if data.get("@type") == "Product":
                items_raw = [data]
            elif data.get("@type") in ("ItemList", "SearchResultsPage"):
                items_raw = data.get("itemListElement", [])
        elif isinstance(data, list):
            items_raw = data

        for item in items_raw:
            if isinstance(item, dict) and item.get("item"):
                item = item["item"]
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            name  = str(item.get("name", "")).strip()
            if not name:
                continue
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = normalize_price_idr(offers.get("price") or offers.get("priceCurrency"))
            raw = {
                "product_name":  name,
                "inn":           str(item.get("description", ""))[:80],
                "strength":      "",
                "dosage_form":   "",
                "price_idr":     price,
                "manufacturer":  str((item.get("brand") or {}).get("name", "") if isinstance(item.get("brand"), dict) else item.get("brand", "")),
                "category":      "",
                "source":        "SwipeRx",
                "keyword":       keyword,
                "confidence":    0.70,
            }
            results.append(normalize_record(raw))
    return results


def _parse_product_cards(html: str, keyword: str) -> list[dict[str, Any]]:
    """SwipeRx 상품 카드 HTML 파싱."""
    soup    = BeautifulSoup(html, "html.parser")
    results = []

    # 가능한 카드 선택자들
    cards = (
        soup.find_all("div", class_=re.compile(r"product[_-]?card|drug[_-]?card|catalog[_-]?item", re.I))
        or soup.find_all("article", class_=re.compile(r"product|item|drug", re.I))
        or soup.find_all("li",  class_=re.compile(r"product|item|drug", re.I))
    )

    for card in cards:
        name_el = (
            card.find(["h2","h3","h4","a","p"], class_=re.compile(r"name|title|product", re.I))
        )
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 3:
            continue

        price_el = card.find(class_=re.compile(r"price|harga|cost", re.I))
        inn_el   = card.find(class_=re.compile(r"inn|generic|zat.aktif|ingredient", re.I))
        mfr_el   = card.find(class_=re.compile(r"manufacturer|brand|produsen", re.I))
        cat_el   = card.find(class_=re.compile(r"category|kategori|class", re.I))
        str_el   = card.find(class_=re.compile(r"strength|kekuatan|dosis", re.I))
        frm_el   = card.find(class_=re.compile(r"form|sediaan|bentuk", re.I))

        raw = {
            "product_name": name,
            "inn":          inn_el.get_text(strip=True) if inn_el else "",
            "strength":     str_el.get_text(strip=True) if str_el else "",
            "dosage_form":  frm_el.get_text(strip=True) if frm_el else "",
            "price_idr":    normalize_price_idr(price_el.get_text(strip=True)) if price_el else None,
            "manufacturer": mfr_el.get_text(strip=True) if mfr_el else "",
            "category":     cat_el.get_text(strip=True) if cat_el else "",
            "source":       "SwipeRx",
            "keyword":      keyword,
            "confidence":   0.70,
        }
        results.append(normalize_record(raw))
    return results


async def search_swiperx(
    keyword: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """SwipeRx에서 약품 검색.

    Args:
        keyword: INN 성분명 또는 제품명
        max_results: 최대 반환 건수
    """
    results: list[dict[str, Any]] = []
    encoded = quote(keyword)

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_make_headers(),
        follow_redirects=True,
    ) as client:
        # 시도 1: 내부 API
        api_endpoints = [
            (f"{_BASE_URL}/api/v1/products", {"search": keyword, "q": keyword, "limit": max_results}),
            (f"{_BASE_URL}/api/products",    {"keyword": keyword, "limit": max_results}),
            (f"{_BASE_URL}/api/catalog",     {"q": keyword}),
        ]
        for api_url, params in api_endpoints:
            try:
                resp = await client.get(api_url, params=params)
                if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                    data = resp.json()
                    products_list = []
                    if isinstance(data, list):
                        products_list = data
                    elif isinstance(data, dict):
                        for k in ("data", "products", "items", "results", "catalog"):
                            if isinstance(data.get(k), list):
                                products_list = data[k]
                                break
                    for p in products_list:
                        if not isinstance(p, dict):
                            continue
                        name = str(p.get("name") or p.get("product_name") or "").strip()
                        if not name:
                            continue
                        raw = {
                            "product_name": name,
                            "inn":          str(p.get("inn") or p.get("generic_name") or ""),
                            "strength":     str(p.get("strength") or p.get("kekuatan") or ""),
                            "dosage_form":  str(p.get("form") or p.get("dosage_form") or ""),
                            "price_idr":    normalize_price_idr(p.get("price") or p.get("price_idr")),
                            "manufacturer": str(p.get("manufacturer") or p.get("brand") or ""),
                            "category":     str(p.get("category") or p.get("therapeutic_class") or ""),
                            "source":       "SwipeRx",
                            "keyword":      keyword,
                            "confidence":   0.75,
                        }
                        results.append(normalize_record(raw))
                    if results:
                        return results[:max_results]
            except Exception:
                continue

        # 시도 2: 카탈로그 검색 HTML
        search_urls = [
            f"{_CATALOG_URL}?q={encoded}",
            f"{_CATALOG_URL}/search?q={encoded}",
            f"{_BASE_URL}/id/search?q={encoded}",
            f"{_BASE_URL}/search?q={encoded}",
        ]
        for url in search_urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.text) > 500:
                    # JSON-LD 먼저
                    parsed = _parse_jsonld(resp.text, keyword)
                    if parsed:
                        results.extend(parsed[:max_results])
                        return results
                    # 카드 파싱
                    parsed = _parse_product_cards(resp.text, keyword)
                    if parsed:
                        results.extend(parsed[:max_results])
                        return results
            except Exception:
                continue

    if not results:
        results.append({
            "product_name": "", "inn": keyword, "strength": "",
            "dosage_form": "", "price_idr": None,
            "source": "SwipeRx", "keyword": keyword,
            "error": "검색 결과 없음 또는 사이트 구조 변경 (B2B 로그인 필요 가능성)",
        })
    return results


async def batch_search_swiperx(
    keywords: list[str],
    max_results_each: int = 10,
    delay_sec: float = _DELAY,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_swiperx(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
