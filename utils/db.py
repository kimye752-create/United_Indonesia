"""Supabase products 테이블 래퍼 — 인도네시아(ID) 전용.

보안 원칙:
  - 모든 쓰기 작업은 country == COUNTRY_CODE("ID") 검증 후 실행
  - 다른 국가 row 생성·수정·삭제 불가 (ValueError 발생)
  - 읽기는 항상 country="ID" 필터 적용

환경변수:
  SUPABASE_URL  (기본값 하드코딩)
  SUPABASE_KEY  (기본값 하드코딩)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

# ── 국가 코드 상수 (변경 금지) ─────────────────────────────────────────────────
COUNTRY_CODE = "ID"
_SOURCE_PREFIX = f"{COUNTRY_CODE}:"

_DEFAULT_URL = "https://oynefikqoibwtfpjlizv.supabase.co"
_DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im95bmVmaWtxb2lid3RmcGpsaXp2Iiwicm9sZSI6"
    "InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjA1NzgwMywiZXhwIjoyMDkxNjMzODAzfQ"
    ".eCFcjx7gOhiv7mCyR2RiadndE9d6e6kVOWysHrarZTM"
)

_client_cache: Any = None


def get_client():
    """Supabase 클라이언트 싱글톤 반환."""
    global _client_cache
    if _client_cache is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", _DEFAULT_URL)
        key = os.environ.get("SUPABASE_KEY", _DEFAULT_KEY)
        _client_cache = create_client(url, key)
    return _client_cache


get_supabase_client = get_client


def _guard_country(row: dict[str, Any]) -> None:
    """row의 country 필드가 COUNTRY_CODE("ID")인지 검증.

    다른 국가 값이 들어오면 즉시 ValueError를 발생시켜
    다른 팀원 데이터를 덮어쓰거나 삭제하는 사고를 방지한다.
    """
    country = row.get("country")
    if country is None:
        raise ValueError(
            f"[DB guard] 'country' 필드가 없습니다. "
            f"반드시 country='{COUNTRY_CODE}'를 명시해 주세요."
        )
    if country != COUNTRY_CODE:
        raise ValueError(
            f"[DB guard] country='{country}'는 이 프로젝트에서 쓸 수 없습니다. "
            f"인도네시아 전용 코드 '{COUNTRY_CODE}'만 허용됩니다. "
            f"다른 팀원의 데이터를 실수로 수정하지 않도록 차단합니다."
        )


# ── 조회 ────────────────────────────────────────────────────────────────────────

def fetch_all_products(country: str = COUNTRY_CODE) -> list[dict[str, Any]]:
    """products 테이블에서 인도네시아(ID) 전체 품목 조회 (deleted_at is null)."""
    if country != COUNTRY_CODE:
        raise ValueError(f"[DB guard] 이 서버는 country='{COUNTRY_CODE}'만 조회할 수 있습니다.")
    sb = get_client()
    r = (
        sb.table("products")
        .select("*")
        .eq("country", COUNTRY_CODE)
        .is_("deleted_at", "null")
        .order("crawled_at", desc=True)
        .execute()
    )
    return r.data or []


def fetch_kup_products(country: str = COUNTRY_CODE) -> list[dict[str, Any]]:
    """KUP 파이프라인 품목만 조회 (source_name='ID:kup_pipeline')."""
    if country != COUNTRY_CODE:
        raise ValueError(f"[DB guard] 이 서버는 country='{COUNTRY_CODE}'만 조회할 수 있습니다.")
    sb = get_client()
    r = (
        sb.table("products")
        .select("*")
        .eq("country", COUNTRY_CODE)
        .eq("source_name", f"{COUNTRY_CODE}:kup_pipeline")
        .is_("deleted_at", "null")
        .execute()
    )
    return r.data or []


def fetch_product_by_id(product_id: str) -> dict[str, Any] | None:
    """product_id로 단건 조회. 반드시 country=ID인 row만 반환."""
    sb = get_client()
    r = (
        sb.table("products")
        .select("*")
        .eq("product_id", product_id)
        .eq("country", COUNTRY_CODE)      # ← 다른 국가 row 접근 불가
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    data = r.data or []
    return data[0] if data else None


# ── 쓰기 ────────────────────────────────────────────────────────────────────────

def upsert_product(row: dict[str, Any]) -> bool:
    """products 테이블에 upsert.

    country 필드가 'ID'가 아니면 ValueError 발생 (다른 국가 데이터 보호).
    충돌 키: (country, source_name, source_url)
    """
    _guard_country(row)          # 반드시 country="ID" 검증
    sb = get_client()
    now = datetime.now(timezone.utc).isoformat()
    row.setdefault("crawled_at", now)
    row.setdefault("confidence", 0.5)
    try:
        sb.table("products").upsert(
            row,
            on_conflict="country,source_name,source_url",
        ).execute()
        return True
    except Exception:
        return False


def upsert_id_product(
    product_id: str,
    product_name: str,
    inn: str = "",
    source_name: str = "",
    source_url: str = "",
    extra: dict[str, Any] | None = None,
) -> bool:
    """인도네시아 전용 품목 upsert 헬퍼.

    country="ID"를 자동 설정하므로 호출자가 country를 직접 지정할 필요 없음.
    """
    row: dict[str, Any] = {
        "country":      COUNTRY_CODE,
        "product_id":   product_id,
        "product_name": product_name,
        "inn":          inn,
        "source_name":  source_name or f"{COUNTRY_CODE}:kup_pipeline",
        "source_url":   source_url,
    }
    if extra:
        # extra에 다른 country 값이 섞여 들어오는 경우 방지
        extra.pop("country", None)
        row.update(extra)
    return upsert_product(row)


def soft_delete_product(product_id: str) -> bool:
    """deleted_at을 현재 시각으로 설정 (소프트 삭제).

    country=ID인 row만 대상으로 하며, 다른 국가 row는 절대 건드리지 않는다.
    """
    sb = get_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("products").update({"deleted_at": now}).eq(
            "product_id", product_id
        ).eq(
            "country", COUNTRY_CODE   # ← 다른 국가 row 보호
        ).execute()
        return True
    except Exception:
        return False
