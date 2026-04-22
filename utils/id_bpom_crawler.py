"""
id_bpom_crawler.py — BPOM Cek 의약품 등록 DB 크롤러

대상: https://cekbpom.pom.go.id/produk-obat
방식: DataTables JSON API  POST /produk-dt/01
      (CSRF 토큰 선취득 후 세션 유지)

수집 필드:
  - product_name   : 제품명 (PRODUCT_NAME)
  - brand_name     : 브랜드명 (PRODUCT_BRANDS)
  - inn            : 성분명 (INGREDIENTS)
  - reg_no         : 등록번호 (PRODUCT_REGISTER)  ML=수입 / MD=국내
  - dosage_form    : 제형 (PRODUCT_FORM)
  - packaging      : 포장 단위 (PRODUCT_PACKAGE)
  - manufacturer   : 제조사 (MANUFACTURER_NAME)
  - registrar      : 등록업체 (REGISTRAR)
  - status         : 허가 상태 (STATUS)  Berlaku = 유효
  - expire_date    : 만료일 (PRODUCT_EXPIRED)
  - atc_code       : ATC 코드 (PRODUCT_ATC)
  - source         : "BPOM"
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

_BASE_URL   = "https://cekbpom.pom.go.id"
_PAGE_URL   = f"{_BASE_URL}/produk-obat"
_DT_URL     = f"{_BASE_URL}/produk-dt/01"   # 01 = Obat (medicines)
_TIMEOUT    = 25.0
_DELAY      = 2.0


def _make_base_headers() -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }


def _make_ajax_headers(csrf_token: str, referer: str = _PAGE_URL) -> dict[str, str]:
    return {
        "User-Agent": pick_ua(),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-TOKEN": csrf_token,
        "Referer": referer,
        "Origin": _BASE_URL,
    }


def _parse_product(item: dict[str, Any], keyword: str) -> dict[str, Any]:
    """BPOM JSON 레코드를 공통 포맷으로 변환."""
    brand = (item.get("PRODUCT_BRANDS") or "").strip()
    if brand in ("-", "—", ""):
        brand = ""
    raw = {
        "product_name":  (item.get("PRODUCT_NAME") or "").strip(),
        "brand_name":    brand,
        "inn":           (item.get("INGREDIENTS") or "").strip(),
        "reg_no":        (item.get("PRODUCT_REGISTER") or "").strip(),
        "dosage_form":   (item.get("PRODUCT_FORM") or "").strip(),
        "packaging":     (item.get("PRODUCT_PACKAGE") or "").strip(),
        "manufacturer":  (item.get("MANUFACTURER_NAME") or "").strip(),
        "registrar":     (item.get("REGISTRAR") or "").strip(),
        "status":        (item.get("STATUS") or "").strip(),
        "expire_date":   (item.get("PRODUCT_EXPIRED") or "").strip(),
        "atc_code":      (item.get("PRODUCT_ATC") or "").strip(),
        "source":        "BPOM",
        "keyword":       keyword,
        "confidence":    0.90,   # 공식 정부 등록 DB — 높은 신뢰도
    }
    return normalize_record(raw)


async def search_bpom(
    keyword: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """BPOM Cek에서 성분명(INN) 또는 제품명으로 검색.

    Args:
        keyword     : 검색어 (INN 권장, 예: "Atorvastatin")
        max_results : 최대 반환 건수

    Returns:
        등록 제품 정보 딕셔너리 리스트
    """
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers=_make_base_headers(),
        follow_redirects=True,
    ) as client:
        # ── 1단계: CSRF 토큰 + 세션 쿠키 확보 ──────────────────────────
        try:
            page_resp = await client.get(_PAGE_URL)
            csrf_match = re.search(
                r'meta\s+name="csrf-token"\s+content="([^"]+)"',
                page_resp.text,
            )
            csrf_token = csrf_match.group(1) if csrf_match else ""
        except Exception as exc:
            logger.warning("BPOM 메인 페이지 요청 실패: %s", exc)
            results.append({
                "product_name": "", "inn": keyword,
                "source": "BPOM", "keyword": keyword,
                "error": f"페이지 로드 실패: {exc}",
            })
            return results

        # ── 2단계: DataTables JSON POST ─────────────────────────────────
        dt_payload = {
            "draw":           "1",
            "start":          "0",
            "length":         str(max_results),
            "search[value]":  keyword,
            "search[regex]":  "false",
        }
        try:
            dt_resp = await client.post(
                _DT_URL,
                data=dt_payload,
                headers=_make_ajax_headers(csrf_token),
            )
            if dt_resp.status_code != 200:
                logger.warning("BPOM DT endpoint 실패: HTTP %s", dt_resp.status_code)
            else:
                data = dt_resp.json()
                for item in data.get("data", [])[:max_results]:
                    if isinstance(item, dict) and item.get("PRODUCT_NAME"):
                        results.append(_parse_product(item, keyword))
        except Exception as exc:
            logger.warning("BPOM DataTables 요청 실패: %s", exc)

    if not results:
        results.append({
            "product_name": "", "inn": keyword,
            "reg_no": "", "dosage_form": "", "manufacturer": "",
            "source": "BPOM", "keyword": keyword,
            "error": "검색 결과 없음",
        })
    return results


def classify_reg_no(reg_no: str) -> str:
    """등록번호 앞자리로 수입(ML) / 국내(MD) 분류."""
    prefix = reg_no.strip().upper()[:2]
    mapping = {
        "ML": "수입 (Import)",
        "MD": "국내 생산 (Domestic)",
        "GKL": "국내 (Generik)",
        "DL": "수입 임상시험약",
        "SI": "특별 수입 허가",
    }
    # 3-char prefix check first
    if reg_no.strip().upper()[:3] in mapping:
        return mapping[reg_no.strip().upper()[:3]]
    return mapping.get(prefix, f"기타 ({prefix})")


async def batch_search_bpom(
    keywords: list[str],
    max_results_each: int = 10,
    delay_sec: float = _DELAY,
) -> dict[str, list[dict[str, Any]]]:
    """여러 키워드 순차 검색 (Rate limit 준수)."""
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_bpom(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
