"""BPOM Cek 의약품 등록 크롤러 (단순화).

대상: https://cekbpom.pom.go.id/
방식: httpx 정적 HTML 파싱 (Cek BPOM 검색 POST 폼)

수집 필드:
  - product_name : 제품명
  - reg_no       : 등록번호 (ML=수입, MD=국내)
  - holder       : 등록업체(Pendaftar)
  - form         : 제형(Bentuk Sediaan)
  - expire_date  : 허가 만료일(Masa Berlaku)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from bs4 import BeautifulSoup

_BASE_URL = "https://cekbpom.pom.go.id/"
_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}


async def search_bpom(
    keyword: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """BPOM Cek에서 성분명(INN) 또는 제품명으로 검색.

    Args:
        keyword: 검색어 (INN 성분명 권장, 예: "Rosuvastatin")
        max_results: 최대 반환 건수

    Returns:
        등록 제품 정보 딕셔너리 리스트
    """
    results: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            # 1단계: 메인 페이지에서 CSRF 토큰 확보
            resp = await client.get(_BASE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            csrf_input = soup.find("input", {"name": "_token"})
            csrf_token = csrf_input["value"] if csrf_input else ""

            # 2단계: 검색 POST (Cek BPOM 검색 폼)
            search_payload = {
                "_token": csrf_token,
                "search": keyword,
                "type": "nama_zat_aktif",  # 성분명 검색
            }
            search_resp = await client.post(
                _BASE_URL + "search",
                data=search_payload,
            )
            if search_resp.status_code >= 400:
                # 폼 구조 변경 시 fallback: GET 쿼리 시도
                search_resp = await client.get(
                    _BASE_URL,
                    params={"search": keyword, "type": "nama_produk"},
                )

            search_soup = BeautifulSoup(search_resp.text, "html.parser")
            rows = search_soup.select("table tbody tr")

            for row in rows[:max_results]:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 3:
                    results.append({
                        "product_name": cols[0] if len(cols) > 0 else "",
                        "reg_no":       cols[1] if len(cols) > 1 else "",
                        "holder":       cols[2] if len(cols) > 2 else "",
                        "form":         cols[3] if len(cols) > 3 else "",
                        "expire_date":  cols[4] if len(cols) > 4 else "",
                        "source":       "BPOM Cek",
                        "keyword":      keyword,
                    })

    except Exception as exc:
        results.append({
            "product_name": "",
            "reg_no": "",
            "holder": "",
            "form": "",
            "expire_date": "",
            "source": "BPOM Cek",
            "keyword": keyword,
            "error": str(exc)[:120],
        })

    return results


def classify_reg_no(reg_no: str) -> str:
    """등록번호 앞자리로 수입(ML) / 국내(MD) 분류."""
    prefix = reg_no.strip().upper()[:2]
    mapping = {
        "ML": "수입 (Import)",
        "MD": "국내 생산 (Domestic)",
        "DL": "수입 임상시험약",
        "SI": "특별 수입 허가",
    }
    return mapping.get(prefix, f"기타 ({prefix})")


async def batch_search_bpom(
    keywords: list[str],
    max_results_each: int = 5,
    delay_sec: float = 2.0,
) -> dict[str, list[dict[str, Any]]]:
    """여러 키워드 순차 검색 (Rate limit 준수)."""
    output: dict[str, list[dict[str, Any]]] = {}
    for kw in keywords:
        output[kw] = await search_bpom(kw, max_results=max_results_each)
        await asyncio.sleep(delay_sec)
    return output
