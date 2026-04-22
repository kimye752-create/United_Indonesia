"""
id_mims_crawler.py — MIMS Indonesia 임상 약품 DB 크롤러

대상: https://www.mims.com/indonesia/drug/search?q={keyword}
방식: 정적 HTML 파싱 (col-lg-9 카드 구조 분석)

수집 필드:
  - product_name   : 제품명 (상품명)
  - drug_type      : Brand | Generic
  - inn            : 성분명 (Generic Name)
  - mims_class     : MIMS 클래스 (치료 분류)
  - indication     : 적응증 요약
  - manufacturer   : 제조사
  - detail_url     : 상세 페이지 URL
  - source         : "MIMS Indonesia"
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from utils.id_antibot import pick_ua
from utils.id_normalizer import normalize_record

logger = logging.getLogger(__name__)

_BASE_URL   = "https://www.mims.com"
_SEARCH_URL = f"{_BASE_URL}/indonesia/drug/search"
_TIMEOUT    = 20.0
_DELAY      = 1.5


def _make_headers() -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Referer": f"{_BASE_URL}/indonesia",
    }


def _parse_mims_search(html: str, keyword: str) -> list[dict[str, Any]]:
    """MIMS 검색 결과 HTML 파싱.

    구조: div.col-lg-9.col-md-9 안에 각 약품 카드가 있음
      - div.row > a > h1  : 제품명
      - span.drug-type-badge : Brand / Generic
      - span.class-header 내 텍스트: Generic Name, MIMS Class, Indication 등
    """
    soup    = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.find_all("div", class_=lambda x: x and "col-lg-9" in x and "col-md-9" in x)

    for card in cards:
        # 제품명
        h1 = card.find("h1")
        name = h1.get_text(strip=True) if h1 else ""
        if not name:
            continue

        # 상세 URL
        a_tag = card.find("a", href=re.compile(r"/indonesia/drug/info/", re.I))
        detail_url = urljoin(_BASE_URL, a_tag["href"]) if a_tag else ""

        # drug_type (Brand / Generic)
        badge = card.find("span", class_="drug-type-badge")
        drug_type = badge.get_text(strip=True) if badge else ""

        # class-header span들 파싱
        # 구조: <span class="class-header">MIMS Class :</span> <a><span>Dyslipidaemic Agents</span></a>
        # 또는: <span class="class-header">Generic Name : <span class="class-text-red"><a>Atorvastatin</a></span></span>
        inn_name   = ""
        mims_class = ""
        indication = ""
        manufacturer = ""

        for row_div in card.find_all("div", class_="row"):
            header_span = row_div.find("span", class_="class-header")
            if not header_span:
                continue
            header_text = header_span.get_text(strip=True)
            low = header_text.lower()

            # 헤더 내부 값 (Generic Name : <span>Value</span> 형태)
            inner_value = ""
            inner_red = header_span.find("span", class_=re.compile(r"class-text-red|txt-link", re.I))
            if inner_red:
                inner_value = inner_red.get_text(strip=True)

            # 헤더 형제 값 (MIMS Class : → <a><span>Value</span></a> 형태)
            sibling_value = ""
            for sib in header_span.next_siblings:
                t = sib.get_text(strip=True) if hasattr(sib, "get_text") else str(sib).strip()
                if t:
                    sibling_value = t
                    break

            value = inner_value or sibling_value or header_text

            if "generic name" in low:
                inn_name = value
            elif "mims class" in low:
                mims_class = value
            elif "indication" in low:
                indication = value[:200]
            elif "manufacturer" in low or "company" in low:
                manufacturer = value

        raw = {
            "product_name": name,
            "drug_type":    drug_type,
            "inn":          inn_name,
            "mims_class":   mims_class,
            "indication":   indication,
            "manufacturer": manufacturer,
            "detail_url":   detail_url,
            "source":       "MIMS Indonesia",
            "keyword":      keyword,
            "confidence":   0.85,  # MIMS는 신뢰도 높은 임상 DB
        }
        results.append(normalize_record(raw))

    return results


async def search_mims(
    keyword: str,
    max_results: int = 20,
    fetch_details: bool = False,
) -> list[dict[str, Any]]:
    """MIMS Indonesia에서 약품 검색.

    Args:
        keyword      : INN 성분명 또는 제품명 (예: "Atorvastatin")
        max_results  : 최대 반환 건수
        fetch_details: True이면 개별 상세 페이지도 방문
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_make_headers(),
        follow_redirects=True,
    ) as client:
        # 1) Brand 검색
        for mtype in ["brand", "generic", ""]:
            params: dict[str, Any] = {"q": keyword}
            if mtype:
                params["mtype"] = mtype
            try:
                resp = await client.get(_SEARCH_URL, params=params)
                if resp.status_code == 200 and len(resp.text) > 500:
                    parsed = _parse_mims_search(resp.text, keyword)
                    for item in parsed:
                        # 중복 제거 (제품명 기준)
                        if not any(r["product_name"] == item["product_name"] for r in results):
                            results.append(item)
            except Exception as exc:
                logger.debug("MIMS search mtype=%s 실패: %s", mtype, exc)

            if len(results) >= max_results:
                break
            await asyncio.sleep(0.3)

        # 2) 상세 페이지 방문 (선택적)
        if fetch_details and results:
            for item in results[:min(3, len(results))]:
                url = item.get("detail_url", "")
                if not url:
                    continue
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        # 적응증 보강
                        ind_el = soup.find("div", class_=re.compile(r"indication|use", re.I))
                        if ind_el and not item.get("indication"):
                            item["indication"] = ind_el.get_text(strip=True)[:300]
                except Exception:
                    pass
                await asyncio.sleep(0.5)

    results = results[:max_results]
    if not results:
        results.append({
            "product_name": "", "inn": keyword, "mims_class": "",
            "indication": "", "manufacturer": "",
            "source": "MIMS Indonesia", "keyword": keyword,
            "error": "검색 결과 없음",
        })
    return results


async def search_mims_by_class(
    mims_class: str,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """MIMS 클래스별 경쟁 제품 목록 수집."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_make_headers(), follow_redirects=True) as client:
        try:
            resp = await client.get(
                _SEARCH_URL,
                params={"q": mims_class, "mtype": "brand"},
            )
            if resp.status_code == 200:
                return _parse_mims_search(resp.text, mims_class)[:max_results]
        except Exception as exc:
            logger.warning("MIMS class search 실패: %s", exc)
    return []


async def batch_search_mims(
    keywords: list[str],
    max_results_each: int = 15,
    delay_sec: float = _DELAY,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_mims(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
