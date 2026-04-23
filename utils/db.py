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
from datetime import datetime, timedelta, timezone
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
    실제 컬럼명: trade_name (not product_name), active_ingredient (not inn).
    """
    row: dict[str, Any] = {
        "country":           COUNTRY_CODE,
        "product_id":        product_id,
        "trade_name":        product_name,   # 실제 컬럼명
        "active_ingredient": inn,            # 실제 컬럼명
        "source_name":       source_name or f"{COUNTRY_CODE}:kup_pipeline",
        "source_url":        source_url,
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


# ── 크롤 캐시 저장 / 조회 ────────────────────────────────────────────────────────
#
# 구조:
#   크롤러 성공 → save_crawl_results() → products 테이블 upsert
#   크롤러 실패 → fetch_crawl_cache()  → 7일 이내 캐시 반환
#
# unique constraint: (country, source_name, source_url)
#   source_url 은 소스별 고유 키 문자열로 생성
#   (e.g. "bpom://nie:DKL2100001234A1", "ekatalog://atorvastatin|pt kimia farma")

_SOURCE_SEGMENT: dict[str, str] = {
    # products 테이블 market_segment 체크 제약:
    # 허용값 → tender / retail / wholesale / combo_drug
    "ID:bpom":     "tender",      # 공공 규제·조달 채널
    "ID:ekatalog": "tender",      # LKPP 공공조달
    "ID:fornas":   "tender",      # JKN 급여 공공 처방집
    "ID:mims":     "retail",      # 임상 레퍼런스 (소비자 채널)
    "ID:k24klik":  "retail",      # 온라인 약국 소매
    "ID:swiperx":  "wholesale",   # B2B 도매
}


def _crawl_url_key(source_key: str, rec: dict[str, Any]) -> str:
    """소스·레코드 조합으로 고유 URL 키 생성 (unique constraint source_url 컬럼용)."""
    name = (rec.get("product_name") or "").lower().strip()
    if source_key == "ID:bpom":
        nie = (rec.get("reg_no") or rec.get("nie") or "").upper()
        return f"bpom://nie:{nie}" if nie else f"bpom://name:{name}"
    if source_key == "ID:ekatalog":
        sup = (rec.get("supplier") or rec.get("manufacturer") or "").lower().strip()
        return f"ekatalog://{name}|{sup}"
    if source_key == "ID:fornas":
        inn  = (rec.get("inn") or name).lower().strip()
        str_ = (rec.get("strength") or "").lower().strip()
        form = (rec.get("dosage_form") or "").lower().strip()
        return f"fornas://{inn}|{str_}|{form}"
    if source_key == "ID:mims":
        url = rec.get("detail_url") or ""
        return url if url.startswith("http") else f"mims://{name}"
    if source_key == "ID:k24klik":
        url = rec.get("product_url") or ""
        return url if url.startswith("http") else f"k24klik://{name}"
    if source_key == "ID:swiperx":
        return f"swiperx://{name}"
    return f"{source_key}://{name}"


def _crawl_country_specific(source_key: str, rec: dict[str, Any]) -> dict[str, Any]:
    """소스별 country_specific JSONB 생성."""
    if source_key == "ID:bpom":
        return {
            "nie":          rec.get("reg_no") or rec.get("nie", ""),
            "ml_md":        rec.get("reg_type", ""),
            "status":       rec.get("status", ""),
            "expiry_date":  rec.get("expire_date") or rec.get("expiry_date", ""),
            "atc_code":     rec.get("atc_code", ""),
            "manufacturer": rec.get("manufacturer") or rec.get("registrar", ""),
            "packaging":    rec.get("packaging", ""),
        }
    if source_key == "ID:ekatalog":
        return {
            "price_idr": rec.get("price_idr"),
            "het_idr":   rec.get("het_idr"),
            "satuan":    rec.get("satuan", ""),
            "supplier":  rec.get("supplier") or rec.get("manufacturer", ""),
            "year":      rec.get("year") or rec.get("tahun", ""),
        }
    if source_key == "ID:fornas":
        return {
            "tingkat":     rec.get("fornas_class") or rec.get("tingkat") or rec.get("level", ""),
            "restriction": rec.get("restriction") or rec.get("pembatasan", ""),
            "indication":  rec.get("indication", ""),
        }
    if source_key == "ID:mims":
        return {
            "drug_type":  rec.get("drug_type", ""),
            "mims_class": rec.get("mims_class", ""),
            "indication": rec.get("indication", ""),
            "detail_url": rec.get("detail_url", ""),
        }
    if source_key == "ID:k24klik":
        return {
            "price_idr":    rec.get("price_idr"),
            "price_unit":   rec.get("price_unit", ""),
            "stock_status": rec.get("stock_status", ""),
            "product_url":  rec.get("product_url", ""),
        }
    if source_key == "ID:swiperx":
        return {
            "price_idr":    rec.get("price_idr"),
            "category":     rec.get("category", ""),
            "pack_size":    rec.get("pack_size", ""),
            "manufacturer": rec.get("manufacturer", ""),
        }
    return {}


def save_crawl_results(
    product_id: str,
    source_key: str,
    records: list[dict[str, Any]],
    keyword: str = "",
) -> int:
    """크롤 결과를 products 테이블에 일괄 upsert. 저장된 건수 반환.

    unique constraint (country, source_name, source_url) 기준으로
    동일 레코드는 갱신(crawled_at 업데이트), 신규는 삽입.

    실제 테이블 컬럼명 매핑:
      product_name(크롤) → trade_name(DB)
      inn(크롤)          → active_ingredient(DB)
      price_idr(크롤)    → price_local(DB)
    """
    saved = 0
    for rec in records:
        if rec.get("error"):
            continue
        pname = rec.get("product_name") or rec.get("trade_name") or ""
        if not pname:
            continue
        inn_val = rec.get("inn") or rec.get("active_ingredient") or keyword
        price_val = rec.get("price_idr") or rec.get("price_local") or None
        mfr_val = rec.get("manufacturer") or rec.get("registrar") or rec.get("company") or ""
        row: dict[str, Any] = {
            "country":             COUNTRY_CODE,
            "product_id":          product_id,
            "trade_name":          pname,                    # 실제 컬럼명
            "active_ingredient":   inn_val,                  # 실제 컬럼명
            "manufacturer":        mfr_val,
            "source_name":         source_key,
            "source_url":          _crawl_url_key(source_key, rec),
            "source_tier":         1,                        # NOT NULL 제약
            "registration_number": (
                rec.get("reg_no") or rec.get("nie")
                or rec.get("registration_number") or ""
            ),
            "strength":            rec.get("strength") or "",
            "dosage_form":         rec.get("dosage_form") or "",
            "price_local":         price_val,
            "market_segment":      _SOURCE_SEGMENT.get(source_key, "unknown"),
            "currency":            "IDR",
            "confidence":          0.85,
            "outlier_flagged":     False,
            "country_specific":    _crawl_country_specific(source_key, rec),
        }
        if upsert_product(row):
            saved += 1
    return saved


def fetch_crawl_cache(
    product_id: str,
    source_key: str,
    max_age_hours: int = 168,    # 기본 7일 캐시
) -> list[dict[str, Any]]:
    """DB에서 최근 크롤 캐시 로드.

    product_id + source_key 기준, max_age_hours 이내 데이터 반환.
    없으면 빈 리스트.
    """
    sb = get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    try:
        r = (
            sb.table("products")
            .select(
                "trade_name,active_ingredient,"
                "registration_number,strength,dosage_form,"
                "price_local,country_specific,crawled_at"
            )
            .eq("country", COUNTRY_CODE)
            .eq("source_name", source_key)
            .eq("product_id", product_id)
            .gte("crawled_at", cutoff)
            .is_("deleted_at", "null")
            .execute()
        )
        return r.data or []
    except Exception:
        return []


def fetch_all_crawl_data(product_id: str) -> dict[str, list[dict[str, Any]]]:
    """특정 품목의 전체 소스 캐시를 한번에 조회.

    반환 형태: {"ID:bpom": [...], "ID:ekatalog": [...], ...}
    """
    sb = get_client()
    try:
        r = (
            sb.table("products")
            .select(
                "source_name,trade_name,active_ingredient,"
                "registration_number,strength,dosage_form,"
                "price_local,country_specific,crawled_at"
            )
            .eq("country", COUNTRY_CODE)
            .eq("product_id", product_id)
            .in_("source_name", list(_SOURCE_SEGMENT.keys()))
            .is_("deleted_at", "null")
            .execute()
        )
        rows = r.data or []
    except Exception:
        rows = []

    result: dict[str, list[dict[str, Any]]] = {k: [] for k in _SOURCE_SEGMENT}
    for row in rows:
        sn = row.get("source_name", "")
        if sn in result:
            result[sn].append(row)
    return result
