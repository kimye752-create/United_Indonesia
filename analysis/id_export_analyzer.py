"""인도네시아(ID) 완제의약품 수출 적합성 분석 엔진.

LLM 우선순위:
  1. Claude API (claude-haiku-4-5-20251001) — BPOM/FORNAS/e-Katalog 컨텍스트 기반 분석
  2. Perplexity API (sonar-pro)            — Claude 불확실 판정 시 보조 검색
  3. 정적 폴백                             — API 미설정 시

분석 출력 스키마 (품목별):
  product_id, trade_name, inn_label,
  verdict(적합/부적합/조건부),
  rationale               — 종합 판정 근거 (두괄식)
  basis_regulatory        — BPOM 인허가·특허 연계 분석
  basis_procurement       — FORNAS/e-Katalog 급여·조달 전략
  basis_distribution      — PBF 유통·마진 구조 분석
  basis_clinical          — 의학회 가이드라인 처방 포지셔닝
  entry_pathway           — 시장 진출 단계별 권고
  ekatalog_price_hint     — e-Katalog 조달가 추정 (IDR/정)
  risks_conditions        — 리스크 및 충족 조건
  key_factors             — 핵심 요인 목록
  sources                 — 인용 출처
  confidence_note         — 신뢰도 노트
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

# ── 8개 타겟 품목 메타 ─────────────────────────────────────────────────────────

_PRODUCT_META: list[dict[str, str]] = [
    {
        "product_id":       "ID_rosumeg_combigel",
        "trade_name":       "Rosumeg Combigel",
        "inn":              "Rosuvastatin 5mg + Omega-3-acid ethyl esters 1g",
        "dosage_form":      "Soft Capsule (CombiGel)",
        "therapeutic_area": "순환기 / 혼합형 이상지질혈증 (Type IIb)",
        "atc":              "C10AA07 / C10AX06",
        "patent_tech":      "CombiGel® (특허 1752700, 1950907) — Oil-proof Coating",
        "product_type":     "개량신약 (IMD, 복합제)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 2: Cardiovascular & Hematopoietic System",
        "medical_society":  "PERKI (심혈관)",
        "key_risk":         "복합제 FORNAS 등재 미정, ML 경쟁 현황 불명확",
        "priority":         "high",
    },
    {
        "product_id":       "ID_atmeg_combigel",
        "trade_name":       "Atmeg Combigel",
        "inn":              "Atorvastatin 10mg + Omega-3-acid ethyl esters 1g",
        "dosage_form":      "Soft Capsule (CombiGel)",
        "therapeutic_area": "순환기 / 혼합형 이상지질혈증 (Type IIb)",
        "atc":              "C10AA05 / C10AX06",
        "patent_tech":      "CombiGel® (특허 1752700, 1950907)",
        "product_type":     "개량신약 (IMD, 복합제)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 2: Cardiovascular & Hematopoietic System",
        "medical_society":  "PERKI (심혈관)",
        "key_risk":         "Atorvastatin MD(국내) 경쟁 강도, Omega-3 병용 근거 필요",
        "priority":         "medium",
    },
    {
        "product_id":       "ID_ciloduo",
        "trade_name":       "Ciloduo",
        "inn":              "Cilostazol 100/200mg + Rosuvastatin 10/20mg",
        "dosage_form":      "Tablet",
        "therapeutic_area": "순환기 / 말초동맥질환 + 이상지질혈증 복합 치료",
        "atc":              "B01AC23 / C10AA07",
        "patent_tech":      "복합 정제 (임상 연구 기반)",
        "product_type":     "개량신약 (복합제)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 2: Cardiovascular & Hematopoietic System",
        "medical_society":  "PERKI (심혈관)",
        "key_risk":         "인도네시아 기존 진출 이력 — 파트너사 확인 필요",
        "priority":         "high",
    },
    {
        "product_id":       "ID_omethyl_cutielet",
        "trade_name":       "Omethyl Cutielet",
        "inn":              "Omega-3-acid ethyl esters 90, 2g/pouch",
        "dosage_form":      "Seamless Soft Capsule (Aluminium foil Pouch)",
        "therapeutic_area": "순환기 / 고중성지방혈증 (Type IV)",
        "atc":              "C10AX06",
        "patent_tech":      "Seamless Pouch — 한국 최초 Omega-3 2g 제형, 비린내 감소",
        "product_type":     "개량신약 (제형 개선)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 2: Cardiovascular & Hematopoietic System",
        "medical_society":  "PERKI (심혈관)",
        "key_risk":         "OTC Omega-3와 카테고리 혼동 위험 — Rx 포지셔닝 명확화 필요",
        "priority":         "medium",
    },
    {
        "product_id":       "ID_gastiin_cr",
        "trade_name":       "Gastiin CR",
        "inn":              "Mosapride citrate 15mg",
        "dosage_form":      "CR Tablet (BILDAS 이중층 서방)",
        "therapeutic_area": "소화기 / 기능성 소화불량",
        "atc":              "A03FA",
        "patent_tech":      "BILDAS® (특허 1612931) — 속방 5mg + 서방 10mg, 1일 1회",
        "product_type":     "개량신약 (CR 서방형)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 1: Gastrointestinal & Hepatobiliary System",
        "medical_society":  "PGI (소화기)",
        "key_risk":         "일반 Mosapride 5mg×3회 대비 가격 프리미엄 정당화",
        "priority":         "medium",
    },
    {
        "product_id":       "ID_sereterol_activair",
        "trade_name":       "Sereterol Activair",
        "inn":              "Salmeterol 50μg + Fluticasone propionate 250/500μg",
        "dosage_form":      "DPI Inhaler (건조분말 흡입기, Activair 디바이스)",
        "therapeutic_area": "호흡기 / 천식·COPD 유지요법",
        "atc":              "R03AK06",
        "patent_tech":      "Activair DPI 자체 디바이스 — GSK Seretide Diskus 동일 계열",
        "product_type":     "개량신약 (자체 디바이스)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 3: Respiratory System",
        "medical_society":  "PDPI (호흡기)",
        "key_risk":         "GSK/AstraZeneca 다국적 점유율, GINA 가이드라인 ICS-LABA 포지셔닝 필요",
        "priority":         "medium",
    },
    {
        "product_id":       "ID_gadvoa_inj",
        "trade_name":       "Gadvoa Inj.",
        "inn":              "Gadobutrol monohydrate 622.73mg (= Gadobutrol 604.72mg) / 1mL",
        "dosage_form":      "Pre-filled Syringe (PFS) 주사제",
        "therapeutic_area": "영상진단 / MRI 조영제 (두개골·척수·CE-MRA·전신)",
        "atc":              "V08CA09",
        "patent_tech":      "1.0M Macrocyclic GBCA — 타 GBCA(0.5M) 대비 2배 농도, NSF·뇌침착 위험 최소",
        "product_type":     "전문의약품 (조영제)",
        "hs_code":          "3006.30",
        "mims_class":       "의료영상 조영제 (별도 분류)",
        "medical_society":  "PDSRI (영상의학)",
        "key_risk":         "병원 조달 전용 — 방사선과 KOL 및 영상의학회 입점 필요",
        "priority":         "medium",
    },
    {
        "product_id":       "ID_hydrine",
        "trade_name":       "Hydrine",
        "inn":              "Hydroxyurea 500mg",
        "dosage_form":      "Capsule",
        "therapeutic_area": "종양학 / CML·흑색종·두경부암·난소암",
        "atc":              "L01XX05",
        "patent_tech":      "Ribonucleotide reductase 억제 (항암 기전)",
        "product_type":     "항암 화학요법제",
        "hs_code":          "3004.90.1000",
        "mims_class":       "Class 9: Oncology",
        "medical_society":  "PERHOMPEDIN (혈액종양)",
        "key_risk":         "FORNAS 항암제 급여 등재 요건, MD(국내 생산) 경쟁 여부",
        "priority":         "medium",
    },
]


def _get_product_meta() -> list[dict[str, str]]:
    return _PRODUCT_META


def _read_env_secret(*keys: str) -> str | None:
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return None


def _claude_analysis_model_id() -> str:
    return os.environ.get("CLAUDE_ANALYSIS_MODEL", "claude-haiku-4-5-20251001")


# ── Claude 분석 프롬프트 ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 인도네시아 완제의약품 시장 진출 전문가입니다.
한국 제약사의 수출 적합성을 BPOM 규제·FORNAS 급여·e-Katalog 조달·PBF 유통·의학회 가이드라인 5개 축으로 분석합니다.

분석 원칙:
1. 판정은 반드시 "적합" / "조건부" / "부적합" 중 하나
2. 모든 근거는 두괄식(결론 먼저, 근거 후술)
3. 가격 추정은 IDR 단위로 표기 (예: Rp 15,000/정)
4. 개량신약 복합제의 경우 CERDAS 원칙(합리성·비용 효과성) 활용
5. FORNAS 미등재 시 대안 전략 제시 필수

출력 JSON 스키마:
{
  "verdict": "적합|조건부|부적합",
  "verdict_en": "suitable|conditional|unsuitable",
  "rationale": "종합 판정 근거 (2~3문장 두괄식)",
  "basis_regulatory": "BPOM 인허가·ML/MD 경쟁·특허 연계 분석",
  "basis_procurement": "FORNAS 등재 전략·e-Katalog 조달가 추정",
  "basis_distribution": "PBF 유통 마진 구조·가격 스프레드 분석",
  "basis_clinical": "의학회 가이드라인 처방 포지셔닝·KOL 전략",
  "entry_pathway": "시장 진출 단계별 권고 (BPOM 신청 → FORNAS → e-Katalog 순)",
  "ekatalog_price_hint": "e-Katalog 조달가 추정 (IDR/단위)",
  "risks_conditions": "주요 리스크 3가지·충족 조건",
  "key_factors": ["핵심요인1", "핵심요인2", "핵심요인3"],
  "sources": ["BPOM", "FORNAS", "e-Katalog", "PERKI/PGI 등"],
  "confidence_note": "분석 신뢰도 (높음/중간/낮음) + 근거"
}"""


def _build_user_prompt(meta: dict[str, str], crawl_context: str = "") -> str:
    base = f"""[분석 대상 제품]
제품명: {meta['trade_name']}
INN/성분: {meta['inn']}
제형: {meta['dosage_form']}
치료 분야: {meta['therapeutic_area']}
ATC 코드: {meta['atc']}
특허 기술: {meta['patent_tech']}
제품 유형: {meta['product_type']}
HS Code: {meta['hs_code']}
MIMS 분류: {meta['mims_class']}
연관 학회: {meta['medical_society']}
핵심 리스크: {meta['key_risk']}

[인도네시아 시장 컨텍스트]
- 국가 건강보험(JKN): 전체 인구 84% 가입, FORNAS 등재 = JKN 급여 인정
- BPOM 등록: ML(수입) vs MD(국내) 코드, 5년 주기 갱신
- e-Katalog: 공공병원 의약품 조달 시스템, 제네릭 단일 승자 경쟁
- 특허 연계(Patent Linkage): BPOM 허가 신청 시 DGIP 특허 검색 첨부 의무
- TKDN: 현지화 요건 — 수입(ML) 제품 조달 제한 가능성
- PBF(Pedagang Besar Farmasi): 의무 현지 유통사 경유

[크롤링 수집 데이터]
{crawl_context if crawl_context else "현재 크롤링 데이터 없음 — Claude 추론 기반 분석"}

위 제품의 인도네시아 시장 진출 적합성을 JSON으로 분석하세요."""
    return base


# ── 크롤링 데이터 통합 ─────────────────────────────────────────────────────────

async def _fetch_crawl_context(meta: dict[str, str]) -> str:
    """BPOM + e-Katalog 크롤링 결과를 분석 컨텍스트 문자열로 반환."""
    lines: list[str] = []

    try:
        from utils.id_bpom_crawler import search_bpom
        inn_keyword = meta["inn"].split(" ")[0]  # 첫 번째 성분명만
        bpom_rows = await search_bpom(inn_keyword, max_results=5)
        if bpom_rows:
            lines.append("=== BPOM Cek 수집 결과 ===")
            for r in bpom_rows:
                lines.append(
                    f"• {r.get('product_name','')} | {r.get('reg_no','')} "
                    f"| {r.get('holder','')} | {r.get('form','')}"
                )
    except Exception as exc:
        lines.append(f"[BPOM 크롤링 실패: {exc}]")

    try:
        from utils.id_ekatalog_crawler import search_ekatalog
        inn_keyword = meta["inn"].split(" ")[0]
        ek_rows = await search_ekatalog(inn_keyword, max_results=5)
        if ek_rows:
            lines.append("=== e-Katalog 조달가 수집 결과 ===")
            for r in ek_rows:
                lines.append(
                    f"• {r.get('product_name','')} | Rp {r.get('price_idr','-'):,} "
                    f"| {r.get('supplier','')} | {r.get('satuan','')}"
                )
    except Exception as exc:
        lines.append(f"[e-Katalog 크롤링 실패: {exc}]")

    return "\n".join(lines) if lines else ""


# ── Claude 호출 ───────────────────────────────────────────────────────────────

async def _claude_analyze(
    meta: dict[str, str],
    crawl_context: str,
    claude_key: str,
    model: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Claude API 호출 → JSON 파싱."""
    try:
        import anthropic  # type: ignore

        client = anthropic.AsyncAnthropic(api_key=claude_key)
        msg = await client.messages.create(
            model=model,
            max_tokens=1800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(meta, crawl_context)}],
        )
        raw = msg.content[0].text.strip()

        # JSON 블록 추출
        import re
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            return json.loads(m.group(0)), None
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"json_parse_error: {e}"
    except Exception as e:
        return None, f"claude_failed: {e}"


def _fallback_result(meta: dict[str, str], error: str | None) -> dict[str, Any]:
    return {
        "verdict": None,
        "verdict_en": None,
        "rationale": f"Claude API 키 미설정 또는 분석 실패. ({error or ''})",
        "basis_regulatory": "",
        "basis_procurement": "",
        "basis_distribution": "",
        "basis_clinical": "",
        "entry_pathway": "",
        "ekatalog_price_hint": "",
        "risks_conditions": "",
        "key_factors": [],
        "sources": [],
        "confidence_note": "미분석",
    }


# ── 단일 품목 분석 ─────────────────────────────────────────────────────────────

async def analyze_product(product_id: str) -> dict[str, Any]:
    """단일 품목 수출 적합성 분석."""
    meta_list = {m["product_id"]: m for m in _get_product_meta()}
    meta = meta_list.get(product_id)
    if not meta:
        return {"product_id": product_id, "error": "product_id not found"}

    claude_key = _read_env_secret("CLAUDE_API_KEY", "ANTHROPIC_API_KEY")
    claude_model = _claude_analysis_model_id()

    crawl_context = await _fetch_crawl_context(meta)

    result: dict[str, Any] | None = None
    analysis_error: str | None = None

    if claude_key:
        result, analysis_error = await _claude_analyze(meta, crawl_context, claude_key, claude_model)

    if result is None:
        result = _fallback_result(meta, analysis_error)

    return {
        "product_id":           meta["product_id"],
        "trade_name":           meta["trade_name"],
        "inn":                  meta["inn"],
        "inn_label":            f"{meta['inn']} | {meta['dosage_form']}",
        "therapeutic_area":     meta["therapeutic_area"],
        "product_type":         meta["product_type"],
        "hs_code":              meta["hs_code"],
        "mims_class":           meta["mims_class"],
        "medical_society":      meta["medical_society"],
        "priority":             meta["priority"],
        "verdict":              result.get("verdict"),
        "verdict_en":           result.get("verdict_en"),
        "rationale":            result.get("rationale", ""),
        "basis_regulatory":     result.get("basis_regulatory", ""),
        "basis_procurement":    result.get("basis_procurement", ""),
        "basis_distribution":   result.get("basis_distribution", ""),
        "basis_clinical":       result.get("basis_clinical", ""),
        "entry_pathway":        result.get("entry_pathway", ""),
        "ekatalog_price_hint":  result.get("ekatalog_price_hint", ""),
        "risks_conditions":     result.get("risks_conditions", ""),
        "key_factors":          result.get("key_factors", []),
        "sources":              result.get("sources", []),
        "confidence_note":      result.get("confidence_note", ""),
        "crawl_context_lines":  len([l for l in crawl_context.splitlines() if l.strip()]),
        "analysis_model":       claude_model if claude_key else "미설정",
        "analysis_error":       analysis_error,
        "analyzed_at":          datetime.now(timezone.utc).isoformat(),
    }


# ── 전체 8품목 배치 분석 ──────────────────────────────────────────────────────

async def analyze_all(*, use_perplexity: bool = True) -> list[dict[str, Any]]:
    """8품목 전체 수출 적합성 분석 (병렬 실행)."""
    tasks = [analyze_product(m["product_id"]) for m in _get_product_meta()]
    return list(await asyncio.gather(*tasks))


# ── 커스텀(신약) 분석 ─────────────────────────────────────────────────────────

async def analyze_custom_product(
    trade_name: str,
    inn: str,
    dosage_form: str = "",
) -> dict[str, Any]:
    """사용자 입력 신약에 대한 인도네시아 수출 적합성 분석."""
    meta: dict[str, str] = {
        "product_id":       "custom",
        "trade_name":       trade_name,
        "inn":              inn,
        "dosage_form":      dosage_form,
        "therapeutic_area": "미입력",
        "atc":              "",
        "patent_tech":      "미입력",
        "product_type":     "신약",
        "hs_code":          "3004.90",
        "mims_class":       "",
        "medical_society":  "",
        "key_risk":         "",
        "priority":         "unknown",
    }

    claude_key = _read_env_secret("CLAUDE_API_KEY", "ANTHROPIC_API_KEY")
    claude_model = _claude_analysis_model_id()
    crawl_context = await _fetch_crawl_context(meta)

    result: dict[str, Any] | None = None
    analysis_error: str | None = None

    if claude_key:
        result, analysis_error = await _claude_analyze(meta, crawl_context, claude_key, claude_model)

    if result is None:
        result = _fallback_result(meta, analysis_error)

    return {
        "product_id":          "custom",
        "trade_name":          trade_name,
        "inn":                 inn,
        "inn_label":           f"{inn} {dosage_form}".strip(),
        "therapeutic_area":    "",
        "product_type":        "신약",
        "verdict":             result.get("verdict"),
        "verdict_en":          result.get("verdict_en"),
        "rationale":           result.get("rationale", ""),
        "basis_regulatory":    result.get("basis_regulatory", ""),
        "basis_procurement":   result.get("basis_procurement", ""),
        "basis_distribution":  result.get("basis_distribution", ""),
        "basis_clinical":      result.get("basis_clinical", ""),
        "entry_pathway":       result.get("entry_pathway", ""),
        "ekatalog_price_hint": result.get("ekatalog_price_hint", ""),
        "risks_conditions":    result.get("risks_conditions", ""),
        "key_factors":         result.get("key_factors", []),
        "sources":             result.get("sources", []),
        "confidence_note":     result.get("confidence_note", ""),
        "analysis_model":      claude_model if claude_key else "미설정",
        "analysis_error":      analysis_error,
        "analyzed_at":         datetime.now(timezone.utc).isoformat(),
    }
