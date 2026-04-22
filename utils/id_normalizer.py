"""
id_normalizer.py — 인도네시아 의약품 데이터 정규화

Saudi Pharma Crawler(normalizer.py) 기반 포팅 — IDR 통화 + 인도네시아 제형 특성 반영.

핵심 규칙:
- 함량: 숫자+단위 사이 공백 1개, 단위 소문자, 복합제는 " + " 구분
- 제형: 사전 기반 매핑 (인니어 명칭 포함)
- 가격: 'Rp'·'IDR'·'.' 구분자 제거, 정수 반환
- 성분명: NFKC 정규화
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


# ─── Completeness 기반 confidence 감점 ──────────────────
def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _apply_completeness_penalty(record: dict, base_confidence: float) -> float:
    """핵심 필드 결측 시 confidence 감점 (하한 0.30)."""
    penalty_per_field = 0.08
    floor = 0.30
    missing = 0
    if _is_missing_value(record.get("price_idr")):
        missing += 1
    if _is_missing_value(record.get("strength")):
        missing += 1
    if _is_missing_value(record.get("dosage_form")):
        missing += 1
    adjusted = base_confidence - (missing * penalty_per_field)
    return max(floor, adjusted)


# ─── 1. 함량 정규화 ────────────────────────────────────
_UNIT_ALIASES: dict[str, str] = {
    "mg": "mg", "MG": "mg", "Mg": "mg", "milligram": "mg", "milligrams": "mg",
    "g":  "g",  "G":  "g",  "gram": "g",  "grams": "g",
    "kg": "kg",
    "mcg": "mcg", "µg": "mcg", "ug": "mcg", "microgram": "mcg",
    "ml": "ml",  "mL": "ml",  "ML": "ml",  "milliliter": "ml",
    "l":  "l",   "L":  "l",
    "iu": "iu",  "IU": "iu",  "U": "iu", "units": "iu",
    "%":  "%",
    "mcg/ml": "mcg/ml",
    "mg/ml":  "mg/ml",
    "mg/5ml": "mg/5ml",
}

_STRENGTH_RE   = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Zµ%/]+)", re.UNICODE)
_COMBO_SPLIT_RE = re.compile(r"\s*(?:[+/,]|\band\b|&)\s*", re.IGNORECASE)
_NUMBER_ONLY_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")


def _clean_number(num_raw: str) -> str:
    try:
        d = Decimal(num_raw)
    except InvalidOperation:
        return num_raw
    if d == d.to_integral_value():
        return str(int(d))
    s = f"{d:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def normalize_strength(raw: str | None) -> str | None:
    """'500mg' → '500 mg', '500/125mg' → '500 mg + 125 mg'"""
    if not raw:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    parts = [p.strip() for p in _COMBO_SPLIT_RE.split(text) if p.strip()]
    if not parts:
        return None

    parsed: list[tuple[str | None, str | None, str]] = []
    for part in parts:
        match = _STRENGTH_RE.search(part)
        if match:
            num_str = _clean_number(match.group("num").replace(",", "."))
            unit_raw = match.group("unit")
            unit = _UNIT_ALIASES.get(unit_raw, unit_raw.lower())
            parsed.append((num_str, unit, part))
            continue
        num_only = _NUMBER_ONLY_RE.match(part)
        if num_only:
            parsed.append((_clean_number(num_only.group(1).replace(",", ".")), None, part))
            continue
        parsed.append((None, None, part))

    # 단위 전파 (뒤→앞)
    last_unit: str | None = None
    for i in range(len(parsed) - 1, -1, -1):
        num, unit, orig = parsed[i]
        if unit:
            last_unit = unit
        elif num and last_unit:
            parsed[i] = (num, last_unit, orig)

    rendered = []
    for num, unit, orig in parsed:
        if num and unit:
            rendered.append(f"{num} {unit}")
        else:
            rendered.append(orig)
    return " + ".join(rendered)


# ─── 2. 제형 정규화 (인니어 포함) ──────────────────────
_DOSAGE_FORM_MAP: dict[str, str] = {
    # 정제
    "tablet": "tablet",    "tablets": "tablet",
    "tab":    "tablet",    "tab.": "tablet",
    "film-coated tablet": "tablet",
    "film coated tablet": "tablet",
    "salut selaput": "tablet",     # 인니어: 필름코팅정
    "salut gula": "tablet",        # 인니어: 당의정
    "kaplet": "tablet",            # 인니어: caplet
    "kaptab": "tablet",
    # 캡슐
    "capsule": "capsule",  "capsules": "capsule",
    "cap":     "capsule",  "cap.": "capsule",
    "kapsul":  "capsule",           # 인니어
    "soft capsule": "soft_capsule",
    "soft gelatin capsule": "soft_capsule",
    "kapsul lunak": "soft_capsule", # 인니어: 연질캡슐
    "softgel": "soft_capsule",
    # 주사
    "injection": "injection", "inj": "injection",
    "injeksi":   "injection",       # 인니어
    "infusion":  "infusion",
    "infus":     "infusion",        # 인니어
    "prefilled syringe": "prefilled_syringe",
    # 경구 액제
    "syrup":       "syrup",
    "sirup":       "syrup",         # 인니어
    "oral solution": "solution",
    "larutan":     "solution",      # 인니어
    "suspension":  "suspension",
    "suspensi":    "suspension",    # 인니어
    # 외용
    "cream":   "cream",    "krim": "cream",
    "ointment": "ointment", "salep": "ointment",   # 인니어: 연고
    "gel":     "gel",
    "lotion":  "lotion",
    # 점적
    "eye drops": "drops",   "tetes mata": "drops",
    "ear drops": "drops",   "tetes telinga": "drops",
    "drops":     "drops",   "tetes": "drops",
    # 흡입/기타
    "inhaler": "inhaler",  "inhalasi": "inhaler",
    "patch":   "patch",
    "suppository": "suppository", "suppositoria": "suppository",
    "powder":  "powder",   "serbuk": "powder",
    "sachet":  "pouch",    "puyer": "powder",
    "solution": "solution",
}

_VALID_FORMS = set(_DOSAGE_FORM_MAP.values())


def normalize_dosage_form(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip().lower()
    text = re.sub(r"\s+", " ", text)
    if text in _DOSAGE_FORM_MAP:
        return _DOSAGE_FORM_MAP[text]
    for key in sorted(_DOSAGE_FORM_MAP.keys(), key=len, reverse=True):
        if key in text:
            return _DOSAGE_FORM_MAP[key]
    compact = text.replace(" ", "_")
    if compact in _VALID_FORMS:
        return compact
    return None


# ─── 3. 가격 정규화 (IDR) ──────────────────────────────
_PRICE_CLEAN_RE = re.compile(r"[^\d.,]")


def normalize_price_idr(raw: str | float | int | None) -> int | None:
    """'Rp 15.000' → 15000, 'IDR 15,000.50' → 15001 (반올림)

    인도네시아 포맷 주의:
      - '.' 는 천 단위 구분자 (예: 15.000 = 15000)
      - ',' 는 소수점 구분자 (거의 안 씀)
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        val = round(float(raw))
        return val if val > 0 else None

    text = str(raw).strip()
    text = re.sub(r"[Rp\s]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"IDR\s*", "", text, flags=re.IGNORECASE)
    text = _PRICE_CLEAN_RE.sub("", text)

    if not text:
        return None

    # 인도네시아 포맷: '.' 가 천 단위 구분자인 경우 제거
    # "15.000" → 15000, "15.000,50" → 15001
    if "," in text and "." in text:
        # 유럽식: 1.234,56 → 1234.56
        text = text.replace(".", "").replace(",", ".")
    elif "." in text:
        # 인니 포맷: 15.000 → 15000 (소수점 없는 경우)
        # 단, "15.50" 처럼 소수 2자리 이하면 소수점 가능성
        parts = text.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2 and len(parts[1]) > 0:
            # "15.50" → 15.50 (소수점으로 해석)
            pass
        else:
            # "15.000" → 15000 (천 단위 구분자)
            text = text.replace(".", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        val = round(float(text))
        return val if val > 0 else None
    except ValueError:
        return None


# ─── 4. 성분명 정규화 ──────────────────────────────────
def normalize_scientific_name(raw: str | None) -> str | None:
    if not raw:
        return None
    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


# ─── 5. 통합 엔트리포인트 ──────────────────────────────
def normalize_record(record: dict) -> dict:
    """products 테이블 삽입 전 정규화. 원본 불변, 사본 반환."""
    out = dict(record)
    if "strength" in out:
        out["strength"] = normalize_strength(out.get("strength"))
    if "dosage_form" in out:
        out["dosage_form"] = normalize_dosage_form(out.get("dosage_form"))
    if "price_idr" in out:
        out["price_idr"] = normalize_price_idr(out.get("price_idr"))
    if "scientific_name" in out or "inn" in out:
        key = "scientific_name" if "scientific_name" in out else "inn"
        out[key] = normalize_scientific_name(out.get(key))
    if "confidence" in out:
        try:
            base_conf = float(out.get("confidence") or 0.0)
        except (TypeError, ValueError):
            base_conf = 0.0
        out["confidence"] = _apply_completeness_penalty(out, base_conf)
    return out


# ─── 자가 테스트 ────────────────────────────────────────
if __name__ == "__main__":
    assert normalize_strength("500mg") == "500 mg"
    assert normalize_strength("500/125mg") == "500 mg + 125 mg"
    assert normalize_strength(None) is None

    assert normalize_dosage_form("Tablet") == "tablet"
    assert normalize_dosage_form("Kapsul") == "capsule"
    assert normalize_dosage_form("Sirup") == "syrup"
    assert normalize_dosage_form("Injeksi") == "injection"

    assert normalize_price_idr("Rp 15.000") == 15000
    assert normalize_price_idr("IDR 150,000") == 150000
    assert normalize_price_idr(15000) == 15000
    assert normalize_price_idr("0") is None
    assert normalize_price_idr(None) is None

    print("id_normalizer self-tests passed")
