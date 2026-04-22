"""인도네시아(ID) 완제의약품 수출 적합성 분석 엔진.

LLM 우선순위:
  1. Claude API (claude-haiku-4-5-20251001) — 6개 소스 크롤 컨텍스트 기반 분석
  2. 정적 폴백                             — API 미설정 시

크롤링 소스 (병렬, 각 15초 타임아웃):
  BPOM · e-Katalog · FORNAS · MIMS · K24Klik · SwipeRx

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
분석 결과는 실제 수출 전략 보고서에 그대로 삽입되므로, 모든 내용을 구체적·실무적으로 작성하세요.

분석 원칙:
1. 판정은 반드시 "적합" / "조건부" / "부적합" 중 하나
2. 모든 근거는 두괄식(결론 먼저, 근거 후술)
3. 가격 추정은 IDR 단위로 표기 (예: Rp 15,000/정)
4. 개량신약 복합제의 경우 CERDAS 원칙(합리성·비용 효과성) 활용
5. FORNAS 미등재 시 대안 전략 제시 필수
6. 모든 수치(유병률, 시장규모, 가격)는 출처와 연도를 명시
7. '-' 또는 null 은 정보가 없을 때만 사용 — 추정이 가능하면 반드시 추정치 제시

출력 JSON 스키마 (모든 필드 필수):
{
  "verdict": "적합|조건부|부적합",
  "verdict_en": "suitable|conditional|unsuitable",
  "rationale": "종합 판정 근거 (2~3문장 두괄식) — 이 제품이 인도네시아 시장에 적합/부적합한 핵심 이유",

  "basis_market_medical": "의료 거시환경 종합 분석 (3~5문장) — 인도네시아 전반 의약품 시장 현황 + 이 제품 치료분야의 구체적 시장 상황(유병률, 처방 트렌드, 경쟁구도)",
  "disease_prevalence": "이 제품 치료 분야 인도네시아 유병률/환자 수 (예: '천식·COPD 유병률 약 7.8%, 추정 환자 1,800만 명 — WHO 2023')",
  "related_market": "이 제품 관련 세부 시장 규모 (예: '인도네시아 호흡기 의약품 시장 USD 4.2억, 연 8% 성장 — IQVIA 2024')",

  "basis_regulatory": "BPOM 인허가 현황 및 전략 (3~4문장) — ML 코드 신청 절차, 동일 성분 기등록 제품 현황, 특허 연계(Patent Linkage) 리스크, 예상 심사 기간",
  "bpom_reg": "BPOM 등록 전략 요약 (2~3문장) — 이 제품의 구체적 등록 경로(abridged/full NDA), 현지 MAH 선정 전략, 예상 타임라인",

  "basis_procurement": "FORNAS 급여 및 e-Katalog 조달 전략 (3~4문장) — FORNAS 등재 가능성, JKN 급여 전략, e-Katalog 입찰 가격 추정",
  "ekatalog_price_hint": "e-Katalog 예상 조달가 (IDR/단위) — 동일 성분 현재 조달가 비교 포함 (예: 'Rp 12,500~15,000/정. 현재 제네릭 조달가 Rp 8,000~10,000/정 대비 프리미엄 가격 정당화 필요')",

  "basis_distribution": "PBF 유통·마진 구조 분석 (2~3문장) — 현지 PBF 파트너 전략, 공공·민간 채널별 마진율, 가격 스프레드",
  "basis_clinical": "임상·학회 포지셔닝 전략 (2~3문장) — 관련 인도네시아 의학회(PERKI/PDPI/PGI 등) 가이드라인 반영, KOL 확보 전략",

  "entry_pathway": "단계별 시장 진출 로드맵 (구체적 단계와 기간 포함, 예: '1단계(6~12개월): BPOM ML 신청 → 2단계(12~18개월): FORNAS 등재 신청 → 3단계: e-Katalog 등록')",

  "ref_price_text": "인도네시아 시장 참고 가격 (텍스트) — 경쟁 제품 시장가, 이 제품의 권장 포지셔닝 가격대 (예: 'GSK Seretide IDR 180,000~220,000/inhaler. Sereterol 목표가 IDR 130,000~160,000 (20~30% 하회)')",
  "price_positioning_pbs": "가격 포지셔닝 전략 (2~3문장) — 경쟁약 대비 가격 포지셔닝, BPJS 급여 등재 시 최대 급여가(HET) 추정, 민간 채널 소비자가 추정",

  "risks_conditions": "주요 리스크 3가지와 충족 조건 (각 리스크를 '▸ 리스크: 내용 / 대응: 내용' 형식으로)",
  "key_factors": ["핵심 성공요인 1", "핵심 성공요인 2", "핵심 성공요인 3"],
  "sources": ["인용 출처 1 (기관명+연도)", "인용 출처 2", "인용 출처 3"],
  "confidence_note": "분석 신뢰도 (높음/중간/낮음) + 근거 한 문장"
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
- 인구: 2억 8,100만 명 (2024, BPS Indonesia)
- 1인당 GDP: USD 4,941 (2024, IMF)
- 의약품 시장 규모: USD 87억 (2024E, IQVIA/GlobalData), 연 7~9% 성장
- 보건 지출: GDP 대비 약 3.2% (WHO 2023)
- 의약품 수입 의존도: 원료의약품 기준 약 90% (Kemenkes RI)
- 국가 건강보험(JKN/BPJS-Kesehatan): 전체 인구 84% 가입, FORNAS 등재 = JKN 급여 인정
- BPOM 등록: ML(수입) vs MD(국내) 코드, 5년 주기 갱신, 통상 12~24개월 소요
- e-Katalog/LKPP: 공공병원 의약품 조달 시스템, HET(최고 판매가) 설정
- 특허 연계(Patent Linkage): BPOM 허가 신청 시 DGIP 특허 검색 첨부 의무
- TKDN: 현지화 요건 — 수입(ML) 제품 공공조달 제한 가능성
- PBF(Pedagang Besar Farmasi): 의무 현지 유통사 경유, 마진 15~25%
- PPN(부가가치세): 11% (2022년 개정, 의약품 면세 적용 제한적)

[크롤링 수집 데이터]
{crawl_context if crawl_context else "현재 크롤링 데이터 없음 — Claude 추론 기반 분석"}

위 제품의 인도네시아 수출 전략 분석 보고서를 위한 JSON을 작성하세요.
반드시 모든 필드를 채우고, 수치는 출처·연도를 괄호 안에 명시하세요.
추정값도 '-' 대신 근거와 함께 구체적으로 작성하세요."""
    return base


# ── 크롤링 데이터 통합 ─────────────────────────────────────────────────────────

def _inn_primary(inn: str) -> str:
    """복합제 INN에서 주성분 첫 단어 추출.
    예) 'Rosuvastatin 5mg + Omega-3...' → 'Rosuvastatin'
        'Salmeterol 50μg + Fluticasone...' → 'Salmeterol'
    """
    return inn.split(" ")[0]


async def _fetch_crawl_context(meta: dict[str, str]) -> str:
    """BPOM · e-Katalog · FORNAS · MIMS · K24Klik · SwipeRx 6개 소스
    병렬 크롤링 후 Claude 분석 컨텍스트 문자열로 반환.
    개별 크롤러 실패는 노트로 기록하되 전체를 중단하지 않는다.
    """
    kw = _inn_primary(meta["inn"])

    # ── 각 크롤러를 타임아웃 포함 래퍼로 실행 ──────────────────────────────────
    async def _safe(coro, label: str):
        try:
            return await asyncio.wait_for(coro, timeout=15.0)
        except asyncio.TimeoutError:
            return Exception(f"{label} timeout(15s)")
        except Exception as exc:
            return exc

    from utils.id_bpom_crawler      import search_bpom
    from utils.id_ekatalog_crawler  import search_ekatalog
    from utils.id_fornas_crawler    import search_fornas
    from utils.id_mims_crawler      import search_mims
    from utils.id_k24klik_crawler   import search_k24klik
    from utils.id_swiperx_crawler   import search_swiperx

    (bpom_r, ek_r, fornas_r, mims_r, k24_r, swrx_r) = await asyncio.gather(
        _safe(search_bpom(kw,     max_results=5), "BPOM"),
        _safe(search_ekatalog(kw, max_results=5), "e-Katalog"),
        _safe(search_fornas(kw,   max_results=5), "FORNAS"),
        _safe(search_mims(kw,     max_results=5), "MIMS"),
        _safe(search_k24klik(kw,  max_results=5), "K24Klik"),
        _safe(search_swiperx(kw,  max_results=5), "SwipeRx"),
    )

    lines: list[str] = []

    # ── BPOM 등록 현황 ─────────────────────────────────────────────────────────
    if isinstance(bpom_r, list):
        real = [r for r in bpom_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== BPOM 등록 현황 ===")
            for r in real:
                mfr = r.get("manufacturer") or r.get("registrar") or ""
                lines.append(
                    f"• {r.get('product_name','')} | 등록번호: {r.get('reg_no','')} "
                    f"| 제조사: {mfr} | 제형: {r.get('dosage_form','')} "
                    f"| 상태: {r.get('status','')} | ATC: {r.get('atc_code','')}"
                )
        else:
            lines.append(f"[BPOM] {kw}: 등록 제품 없음 (신규 ML 등록 필요)")
    else:
        lines.append(f"[BPOM 크롤링 실패: {bpom_r}]")

    # ── e-Katalog 조달가 ───────────────────────────────────────────────────────
    if isinstance(ek_r, list):
        real = [r for r in ek_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== e-Katalog 공공조달가 ===")
            for r in real:
                price = r.get("price_idr")
                ps = f"Rp {price:,}" if isinstance(price, (int, float)) and price else "가격 미상"
                lines.append(
                    f"• {r.get('product_name','')} | {ps} "
                    f"| 공급사: {r.get('supplier','')} | 단위: {r.get('satuan','')}"
                )
        else:
            lines.append(f"[e-Katalog] {kw}: 조달 등록 없음 (e-Katalog 신규 등록 전략 필요)")
    else:
        lines.append(f"[e-Katalog 크롤링 실패: {ek_r}]")

    # ── FORNAS 국가처방집 ─────────────────────────────────────────────────────
    if isinstance(fornas_r, list):
        real = [r for r in fornas_r if r.get("inn") or r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== FORNAS 국가처방집 등재 ===")
            for r in real:
                if r.get("error"):
                    continue
                name = r.get("inn") or r.get("product_name") or ""
                lines.append(
                    f"• {name} | {r.get('strength','')} | {r.get('dosage_form','')} "
                    f"| 제한: {r.get('restriction') or '없음'} | 분류: {r.get('fornas_class','')}"
                )
        else:
            lines.append(f"[FORNAS] {kw}: 국가처방집 미등재 — JKN 급여 진입 위한 FORNAS 등재 전략 필요")
    else:
        lines.append(f"[FORNAS 크롤링 실패: {fornas_r}]")

    # ── MIMS 경쟁 제품 ────────────────────────────────────────────────────────
    if isinstance(mims_r, list):
        real = [r for r in mims_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== MIMS Indonesia 경쟁 제품 ===")
            for r in real[:5]:
                lines.append(
                    f"• {r.get('product_name','')} [{r.get('drug_type','')}] "
                    f"| 성분: {r.get('inn','')} | MIMS 분류: {r.get('mims_class','')} "
                    f"| 제조사: {r.get('manufacturer','')}"
                )
        else:
            lines.append(f"[MIMS] {kw}: 검색 결과 없음")
    else:
        lines.append(f"[MIMS 크롤링 실패: {mims_r}]")

    # ── K24Klik 소매가 ────────────────────────────────────────────────────────
    if isinstance(k24_r, list):
        real = [r for r in k24_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== K24Klik 온라인 약국 소매가 ===")
            for r in real[:5]:
                price = r.get("price_idr")
                ps = f"Rp {price:,}{r.get('price_unit','')}" if isinstance(price, (int, float)) and price else "가격 미상"
                lines.append(f"• {r.get('product_name','')} | {ps}")
        else:
            lines.append(f"[K24Klik] {kw}: 검색 결과 없음")
    else:
        lines.append(f"[K24Klik 크롤링 실패: {k24_r}]")

    # ── SwipeRx B2B 도매가 ────────────────────────────────────────────────────
    if isinstance(swrx_r, list):
        real = [r for r in swrx_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append("=== SwipeRx B2B 도매가 ===")
            for r in real[:5]:
                price = r.get("price_idr")
                ps = f"Rp {price:,}" if isinstance(price, (int, float)) and price else "가격 미상"
                lines.append(
                    f"• {r.get('product_name','')} | {ps} "
                    f"| 제조사: {r.get('manufacturer','')} | 카테고리: {r.get('category','')}"
                )
        else:
            lines.append(f"[SwipeRx] {kw}: 검색 결과 없음 (B2B 로그인 필요 가능성)")
    else:
        lines.append(f"[SwipeRx 크롤링 실패: {swrx_r}]")

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
    ta = meta.get("therapeutic_area", "")
    tn = meta.get("trade_name", "")
    return {
        "verdict": None,
        "verdict_en": None,
        "rationale": f"Claude API 키 미설정 또는 분석 실패. ({error or ''})",
        "basis_market_medical": (
            f"인도네시아는 인구 2억 8,100만 명(2024)의 동남아시아 최대 의약품 시장으로, "
            f"시장 규모 USD 87억(2024E, IQVIA)이며 연 7~9% 성장 중입니다. "
            f"BPJS-Kesehatan 가입률 84%로 공공 조달 채널(e-Katalog/FORNAS)이 핵심입니다. "
            f"{tn}의 치료 분야({ta})는 인도네시아 내 수요가 지속 증가하고 있습니다."
        ),
        "disease_prevalence": f"{ta} 관련 유병률 데이터 — API 분석 필요",
        "related_market": f"{ta} 관련 시장 규모 — API 분석 필요",
        "basis_regulatory": "BPOM ML(수입 허가) 코드 신청 필요. 심사 기간 통상 12~24개월.",
        "bpom_reg": (
            f"BPOM ML 코드로 수입 허가 신청. 현지 MAH(Marketing Authorization Holder) 선정 후 "
            f"abridged NDA 또는 full NDA 경로 선택. 예상 등록 기간 12~18개월."
        ),
        "basis_procurement": "FORNAS 등재 전략 및 e-Katalog 입찰 가격 — API 분석 필요",
        "ekatalog_price_hint": "e-Katalog 조달가 추정 — API 분석 필요",
        "basis_distribution": "PBF 유통사 경유 필수. 공공 채널 마진 15~22%, 민간 채널 마진 20~35%.",
        "basis_clinical": f"{meta.get('medical_society', '관련 의학회')} 가이드라인 처방 포지셔닝 전략 — API 분석 필요",
        "entry_pathway": (
            "1단계(0~12개월): 현지 MAH 계약 및 BPOM ML 신청 → "
            "2단계(12~24개월): BPOM 허가 취득 후 FORNAS 등재 신청 → "
            "3단계(24개월~): e-Katalog 등록 및 공공병원 입찰 참여"
        ),
        "ref_price_text": "참고 가격 — API 분석 필요",
        "price_positioning_pbs": "가격 포지셔닝 전략 — API 분석 필요",
        "risks_conditions": (
            "▸ 리스크: BPOM 심사 지연(12~24개월) / 대응: 조기 MAH 확보 및 서류 사전 준비\n"
            "▸ 리스크: FORNAS 미등재 시 공공 채널 접근 제한 / 대응: 민간 채널(Halodoc·K24) 우선 진출\n"
            "▸ 리스크: TKDN 현지화 요건 강화 / 대응: 현지 파트너와 CMO 계약 검토"
        ),
        "key_factors": ["BPOM 조기 등록", "FORNAS 등재 전략", "현지 PBF 파트너 확보"],
        "sources": ["BPOM RI", "Kemenkes RI", "BPJS-Kesehatan", "e-Katalog LKPP", "IQVIA Indonesia 2024"],
        "confidence_note": "낮음 — API 미설정, 정적 폴백값 사용",
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

    # 거시지표는 id_macro에서 주입 (제품별 데이터는 Claude 결과 우선)
    from utils.id_macro import get_id_macro
    _macro = {m["label"]: m["value"] for m in get_id_macro()}

    return {
        "product_id":           meta["product_id"],
        "trade_name":           meta["trade_name"],
        "inn":                  meta["inn"],
        "inn_label":            f"{meta['inn']} | {meta['dosage_form']}",
        "dosage_form":          meta["dosage_form"],
        "therapeutic_area":     meta["therapeutic_area"],
        "product_type":         meta["product_type"],
        "hs_code":              meta["hs_code"],
        "mims_class":           meta["mims_class"],
        "medical_society":      meta["medical_society"],
        "priority":             meta["priority"],
        # ── 판정 ──────────────────────────────────────────────────
        "verdict":              result.get("verdict"),
        "verdict_en":           result.get("verdict_en"),
        "rationale":            result.get("rationale", ""),
        # ── P1 보고서 섹션 1: 거시환경 ──────────────────────────────
        "population":           _macro.get("인구",          "2억 8,100만 명"),
        "gdp_per_capita":       _macro.get("1인당 GDP",     "USD 4,941"),
        "pharma_market":        _macro.get("의약품 시장 규모","USD 87억"),
        "health_spend":         "GDP 대비 약 3.2%  (WHO 2023)",
        "import_dep":           _macro.get("의약품 수입 의존도", "약 90%"),
        "disease_prevalence":   result.get("disease_prevalence", ""),
        "related_market":       result.get("related_market", ""),
        "basis_market_medical": result.get("basis_market_medical", ""),
        # ── P1 보고서 섹션 2: 규제 환경 ────────────────────────────
        "basis_regulatory":     result.get("basis_regulatory", ""),
        "bpom_reg":             result.get("bpom_reg", ""),
        "entry_pathway":        result.get("entry_pathway", ""),
        "basis_trade":          result.get("basis_distribution", ""),   # 무역·유통 섹션
        # ── P1 보고서 섹션 3: 가격 ─────────────────────────────────
        "ref_price_text":       result.get("ref_price_text", ""),
        "price_positioning_pbs": result.get("price_positioning_pbs", ""),
        "ekatalog_price_hint":  result.get("ekatalog_price_hint", ""),
        # ── P1 보고서 섹션 4: 리스크 ────────────────────────────────
        "risks_conditions":     result.get("risks_conditions", ""),
        # ── 기타 분석 결과 ─────────────────────────────────────────
        "basis_procurement":    result.get("basis_procurement", ""),
        "basis_distribution":   result.get("basis_distribution", ""),
        "basis_clinical":       result.get("basis_clinical", ""),
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

    from utils.id_macro import get_id_macro
    _macro2 = {m["label"]: m["value"] for m in get_id_macro()}

    return {
        "product_id":          "custom",
        "trade_name":          trade_name,
        "inn":                 inn,
        "inn_label":           f"{inn} {dosage_form}".strip(),
        "dosage_form":         dosage_form,
        "therapeutic_area":    "",
        "product_type":        "신약",
        "verdict":             result.get("verdict"),
        "verdict_en":          result.get("verdict_en"),
        "rationale":           result.get("rationale", ""),
        "population":          _macro2.get("인구", "2억 8,100만 명"),
        "gdp_per_capita":      _macro2.get("1인당 GDP", "USD 4,941"),
        "pharma_market":       _macro2.get("의약품 시장 규모", "USD 87억"),
        "health_spend":        "GDP 대비 약 3.2%  (WHO 2023)",
        "import_dep":          _macro2.get("의약품 수입 의존도", "약 90%"),
        "disease_prevalence":  result.get("disease_prevalence", ""),
        "related_market":      result.get("related_market", ""),
        "basis_market_medical": result.get("basis_market_medical", ""),
        "basis_regulatory":    result.get("basis_regulatory", ""),
        "bpom_reg":            result.get("bpom_reg", ""),
        "entry_pathway":       result.get("entry_pathway", ""),
        "basis_trade":         result.get("basis_distribution", ""),
        "ref_price_text":      result.get("ref_price_text", ""),
        "price_positioning_pbs": result.get("price_positioning_pbs", ""),
        "ekatalog_price_hint": result.get("ekatalog_price_hint", ""),
        "risks_conditions":    result.get("risks_conditions", ""),
        "basis_procurement":   result.get("basis_procurement", ""),
        "basis_distribution":  result.get("basis_distribution", ""),
        "basis_clinical":      result.get("basis_clinical", ""),
        "key_factors":         result.get("key_factors", []),
        "sources":             result.get("sources", []),
        "confidence_note":     result.get("confidence_note", ""),
        "analysis_model":      claude_model if claude_key else "미설정",
        "analysis_error":      analysis_error,
        "analyzed_at":         datetime.now(timezone.utc).isoformat(),
    }
