"""
id_fornas_crawler.py — FORNAS (Formularium Nasional) 크롤러

대상: https://e-fornas.kemkes.go.id/
방식: 정적 HTML 파싱 (Kemenkes 정부 사이트)

수집 필드:
  - product_name  : 제품명
  - inn           : 성분명 (INN)
  - strength      : 함량
  - dosage_form   : 제형
  - restriction   : 처방 제한 (Pembatasan)
  - fornas_class  : 분류 코드 (DOEN/Fornas)
  - source        : "FORNAS"
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from utils.id_antibot import pick_ua
from utils.id_normalizer import normalize_record

logger = logging.getLogger(__name__)

_BASE_URL  = "https://e-fornas.kemkes.go.id"
_SEARCH_URL = f"{_BASE_URL}/obat/search"
_TIMEOUT   = 20.0
_DELAY     = 1.5  # 정부 사이트 rate limit 존중


def _make_headers() -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": _BASE_URL,
    }


def _parse_fornas_table(html: str, keyword: str) -> list[dict[str, Any]]:
    """FORNAS 검색 결과 HTML 테이블 파싱."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 주 테이블 탐색 (다양한 선택자 시도)
    table = (
        soup.find("table", {"id": re.compile(r"fornas|obat|drug", re.I)})
        or soup.find("table", class_=re.compile(r"table|result|drug", re.I))
        or soup.find("table")
    )
    if not table:
        # 카드형 레이아웃 폴백
        cards = soup.find_all("div", class_=re.compile(r"card|item|obat", re.I))
        for card in cards:
            texts = [t.get_text(strip=True) for t in card.find_all(["p", "span", "div", "td"]) if t.get_text(strip=True)]
            if texts:
                results.append({
                    "product_name": texts[0] if texts else "",
                    "inn": "",
                    "strength": "",
                    "dosage_form": "",
                    "restriction": "",
                    "fornas_class": "",
                    "source": "FORNAS",
                    "keyword": keyword,
                })
        return results

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
    for row in rows:
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 2:
            continue
        # 열 순서: 번호 | INN | Kekuatan | Bentuk Sediaan | Pembatasan | ...
        # 사이트 구조에 따라 유동적이므로 최대한 수집
        raw = {
            "product_name": cols[1] if len(cols) > 1 else cols[0],
            "inn":          cols[1] if len(cols) > 1 else "",
            "strength":     cols[2] if len(cols) > 2 else "",
            "dosage_form":  cols[3] if len(cols) > 3 else "",
            "restriction":  cols[4] if len(cols) > 4 else "",
            "fornas_class": cols[5] if len(cols) > 5 else "",
            "source":       "FORNAS",
            "keyword":      keyword,
            "confidence":   0.85,  # 공식 정부 데이터
        }
        results.append(normalize_record(raw))
    return results


async def search_fornas(
    keyword: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """FORNAS에서 성분명/제품명 검색.

    Args:
        keyword: INN 성분명 또는 제품명 (예: "Atorvastatin")
        max_results: 최대 반환 건수

    Returns:
        FORNAS 등재 의약품 딕셔너리 리스트
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_make_headers(),
        follow_redirects=True,
    ) as client:
        # 시도 1: GET 검색 파라미터
        endpoints = [
            (_SEARCH_URL, {"q": keyword, "nama": keyword, "per_page": max_results}),
            (f"{_BASE_URL}/search",  {"keyword": keyword}),
            (f"{_BASE_URL}/obat",    {"search": keyword}),
            (_BASE_URL,              {"search": keyword, "q": keyword}),
        ]
        for url, params in endpoints:
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 200 and len(resp.text) > 500:
                    parsed = _parse_fornas_table(resp.text, keyword)
                    if parsed:
                        results.extend(parsed[:max_results])
                        return results
            except Exception as exc:
                logger.debug("FORNAS endpoint %s 실패: %s", url, exc)
                continue

        # 시도 2: 메인 페이지 폼 POST
        try:
            home = await client.get(_BASE_URL)
            soup = BeautifulSoup(home.text, "html.parser")
            form = soup.find("form")
            action = form.get("action", _BASE_URL) if form else _BASE_URL
            if action and not action.startswith("http"):
                action = _BASE_URL.rstrip("/") + "/" + action.lstrip("/")
            search_resp = await client.post(
                action,
                data={"search": keyword, "keyword": keyword, "q": keyword},
            )
            if search_resp.status_code == 200:
                parsed = _parse_fornas_table(search_resp.text, keyword)
                if parsed:
                    results.extend(parsed[:max_results])
                    return results
        except Exception as exc:
            logger.warning("FORNAS POST 시도 실패: %s", exc)

    if not results:
        results.append({
            "product_name": "", "inn": keyword, "strength": "",
            "dosage_form": "", "restriction": "", "fornas_class": "",
            "source": "FORNAS", "keyword": keyword,
            "error": "검색 결과 없음 또는 사이트 구조 변경",
        })
    return results


def check_fornas_listing(inn: str) -> dict[str, Any]:
    """INN 성분이 FORNAS에 등재됐는지 동기 방식으로 확인."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    items = loop.run_until_complete(search_fornas(inn, max_results=5))
    has_error = any("error" in i for i in items)
    listed = len(items) > 0 and not has_error
    return {
        "inn": inn,
        "listed": listed,
        "count": len(items) if not has_error else 0,
        "items": items if not has_error else [],
    }


async def batch_search_fornas(
    keywords: list[str],
    max_results_each: int = 10,
    delay_sec: float = _DELAY,
) -> dict[str, list[dict[str, Any]]]:
    """여러 키워드 순차 검색."""
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_fornas(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
