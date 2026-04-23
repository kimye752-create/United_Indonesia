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
        "patent_tech":      "복합 정제 (임상 연구 기반) — 실로스타졸 CR(서방형) 제제 기술 보유",
        "product_type":     "개량신약 (복합제, CR 서방형)",
        "hs_code":          "3004.90",
        "mims_class":       "Class 2: Cardiovascular & Hematopoietic System",
        "medical_society":  "PERKI (심혈관)",
        "key_risk":         "경쟁사 IR 제네릭 가격: Pletaal 17,164 IDR, Citaz 18,896 IDR, Stazol 17,177 IDR, Bernofarm 13,928 IDR (K24Klik 기준). "
                            "CR 제제 목표 HET 32,000~36,000 IDR. "
                            "배제 파트너: Kalbe(Citaz 보유), Dexa Medica(Stazol/Aggravan 보유), Otsuka(Pletaal 오리지널). "
                            "유망 파트너: Pharos Indonesia(Ascardia 시너지), Sanbe Farma(항혈전 공백), Novell Pharma(In-licensing 특화). "
                            "IK-CEPA 관세 0%, PMK-131 VAT 실효 11%.",
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

_SYSTEM_PROMPT = (
    # ── 페르소나 & 임무 ──────────────────────────────────────────────────────────
    "당신은 한국유나이티드제약의 인도네시아 수출 전략 전문 애널리스트입니다. "
    "한국 제약사의 인도네시아 완제의약품 수출 적합성을 "
    "BPOM 규제·FORNAS 급여·e-Katalog 조달·PBF 유통·의학회 가이드라인 5개 축으로 분석합니다. "
    "분석 결과는 실제 수출 전략 보고서에 그대로 삽입되므로, 모든 내용을 구체적·실무적으로 작성하세요. "
    "회사 표기는 반드시 '한국유나이티드제약'만 사용합니다.\n\n"

    # ── 데이터 원칙 (최우선) ─────────────────────────────────────────────────────
    "【데이터 원칙 — 최우선】\n"
    "1. 크롤링 JSON(BPOM·e-Katalog·FORNAS·MIMS·K24Klik·SwipeRx)에 있는 수치·코드·브랜드명·가격을 최우선으로 사용합니다.\n"
    "2. 크롤 데이터에 없는 수치·가격·코드·등재 여부는 절대 창작하지 않습니다. "
    "추정이 불가한 경우 '미확보(현지 확인 필요)'로 명시합니다. "
    "추정이 가능한 경우에도 해당 수치 뒤에 반드시 '(추정)' 태그를 붙입니다. "
    "예) 'Rp 12,000/정(추정)', 'FORNAS Tingkat 2 등재 가능(추정)'.\n"
    "3. BPOM 등록번호(NIE), e-Katalog 등재 가격, 경쟁사 목록, HET(최고 판매가)는 실제 크롤 데이터와 정합시킵니다.\n"
    "4. 크롤 컨텍스트에 '[e-Katalog 크롤링 실패]' · '[e-Katalog] … 조달 등록 없음' 등이 표시된 경우, "
    "해당 소스 관련 모든 수치(조달가·HET·급여가·도매가·FORNAS 등재·SwipeRx B2B가)는 '(추정)' 없이 제시할 수 없습니다.\n"
    "5. 추정치는 반드시 출처·연도를 명시한 후 '(추정)' 태그를 붙입니다. "
    "예) 'Rp 12,000~15,000/정 (IQVIA 2024 유사 성분 기준, 추정)'.\n\n"

    # ── 분석 원칙 ────────────────────────────────────────────────────────────────
    "【분석 원칙】\n"
    "5. 판정은 반드시 '적합' / '조건부' / '부적합' 중 하나 (TKDN·BPOM 등록 여부 기준).\n"
    "6. 모든 근거는 두괄식(결론 먼저, 근거 후술).\n"
    "7. 가격 추정은 IDR 단위 표기 (예: Rp 15,000/정). KRW 환산 필요 시 1 IDR ≈ 0.085 KRW 기준.\n"
    "8. 개량신약·복합제는 CERDAS 원칙(합리성·비용효과성·임상 근거) 근거로 FORNAS 등재 전략 제시.\n"
    "9. FORNAS 미등재 시 민간채널(Halodoc·K24Klik·SwipeRx B2B) 대안 전략 제시 필수.\n"
    "10. 모든 수치(유병률·시장규모·가격)는 출처·연도를 괄호 안에 명시 (예: IDF 2023, IQVIA 2024).\n"
    "11. FOB 수출가 역산: "
    "Logic A(공공) = e-Katalog 목표 입찰가(USD) × 0.30, "
    "Logic B(민간) = 목표 HET ÷ 1.11 ÷ 1.28 ÷ 1.15 ÷ 1.05. "
    "IK-CEPA 관세 0%, 실효 VAT 11% 반드시 반영.\n"
    "12. 파트너 추천 시 동일성분 보유사(자가잠식 리스크)를 우선 배제하고, "
    "순환기·대사질환 파이프라인 보유사와의 교차판매 시너지를 핵심 선정 기준으로 제시.\n\n"

    # ── 인도네시아 특화 약어 정의 ────────────────────────────────────────────────
    "【인도네시아 특화 정의 — 최초 노출 시 풀어서 쓸 것】\n"
    "- BPOM (Badan Pengawas Obat dan Makanan · 인도네시아 식약처): ML=수입 허가 코드, MD=국내 생산 코드.\n"
    "- JKN (Jaminan Kesehatan Nasional · 국가건강보험): BPJS-Kesehatan이 운영, FORNAS 등재 = JKN 급여 자동 인정.\n"
    "- TKDN (Tingkat Komponen Dalam Negeri · 현지 부품/제조 비중): 낮으면 공공조달(e-Katalog) 제한.\n"
    "- NIE (Nomor Izin Edar · 품목 허가 번호): BPOM 발행, 5년 주기 갱신.\n"
    "- PBF (Pedagang Besar Farmasi · 의약품 도매업체): 현지 유통 필수 경유, 마진 15~25%.\n"
    "- FORNAS: 국가 필수의약품 처방집(Formularium Nasional), 등재 시 JKN 급여 자동 인정.\n"
    "- HET (Harga Eceran Tertinggi · 최고 소매가): 정부 고시 상한가.\n"
    "- LKPP: 국가조달청, e-Katalog 운영 기관.\n\n"

    # ── 출력 JSON 스키마 ─────────────────────────────────────────────────────────
    "【출력 JSON 스키마 — 모든 필드 필수, 빈 문자열 금지】\n"
    "{\n"
    '  "verdict": "적합|조건부|부적합",\n'
    '  "verdict_en": "suitable|conditional|unsuitable",\n'
    '  "rationale": "종합 판정 근거 (2~3문장 두괄식) — 핵심 적합/부적합 이유와 전제 조건",\n\n'

    '  "basis_market_medical": "의료 거시환경 + 치료분야 시장 분석 (3~5문장) — 인도네시아 의약품 시장 현황·JKN 보급률, 이 제품 치료분야 유병률·처방 트렌드·경쟁구도. 출처·연도 필수",\n'
    '  "disease_prevalence": "이 치료 분야 인도네시아 유병률·추정 환자 수 (예: \'천식·COPD 유병률 약 7.8%, 추정 환자 1,800만 명 — WHO 2023\')",\n'
    '  "related_market": "이 제품 관련 세부 시장 규모·성장률 (예: \'인도네시아 호흡기 의약품 시장 USD 4.2억, 연 8% 성장 — IQVIA 2024\')",\n\n'

    '  "basis_regulatory": "BPOM 인허가 전략 (3~4문장) — 크롤 데이터 기반 동일 성분 기등록 NIE 현황, ML 코드 신청 절차, 특허 연계(Patent Linkage) 리스크 평가, 예상 심사 기간 및 비용",\n'
    '  "bpom_reg": "BPOM 등록 실행 계획 (2~3문장) — abridged/full NDA 경로 선택, 현지 MAH 선정 전략, 예상 타임라인(개월) 및 등록 비용 추정(USD)",\n\n'

    '  "basis_procurement": "FORNAS·e-Katalog 조달 전략 (3~4문장) — FORNAS 등재 가능성·분류(Tingkat 1/2/3), JKN HET 가격 산정, e-Katalog 입찰 전략, LKPP 공개 조달가 비교",\n'
    '  "ekatalog_price_hint": "e-Katalog 예상 조달가 (예: \'Rp 12,500~15,000/정. 현재 동성분 제네릭 조달가 Rp 8,000~10,000/정 대비 프리미엄 근거: 개량제형 임상 우위\')",\n\n'

    '  "basis_distribution": "PBF 유통·마진 구조 (2~3문장) — 권장 PBF 파트너 선정 기준, 공공채널(PBF→공공병원·BPJS) vs 민간채널(PBF→민간병원·약국·디지털) 마진율(%) 구분, 스프레드 전략",\n'
    '  "basis_clinical": "임상·학회 포지셔닝 전략 (2~3문장) — 관련 인도네시아 의학회(PERKI/PDPI/PGI/PERHOMPEDIN/PDSRI 등) 가이드라인 근거, KOL 확보·학술 발표 전략, 처방 확대 로드맵",\n\n'

    '  "entry_pathway": "단계별 시장 진출 로드맵 (기간 명시, 예: \'1단계(0~12개월): 현지 MAH 계약+BPOM ML 신청 → 2단계(12~18개월): FORNAS 등재 신청+KOL 활동 → 3단계(18~24개월): e-Katalog 등록+공공병원 입찰\')",\n\n'

    '  "ref_price_text": "인도네시아 시장 참고 가격 — 크롤 데이터 기반 경쟁 제품 현재 시장가(K24Klik·SwipeRx), 이 제품 권장 포지셔닝 가격대 (공공/민간 구분, IDR 표기)",\n'
    '  "price_positioning_pbs": "가격 포지셔닝 전략 (2~3문장) — 경쟁약 대비 포지셔닝 근거, BPJS 급여 HET 추정, 민간 채널 소비자가 추정 (IDR 표기, 필요 시 KRW 환산 병기)",\n\n'

    '  "risks_conditions": "주요 리스크 3가지와 대응 — 각각 \'▸ 리스크: [내용] / 대응: [내용]\' 형식으로",\n'
    '  "key_factors": ["핵심 성공요인 1 (구체적)", "핵심 성공요인 2 (구체적)", "핵심 성공요인 3 (구체적)"],\n'
    '  "sources": ["출처1 (기관+연도)", "출처2 (기관+연도)", "출처3 (기관+연도)"],\n'
    '  "confidence_note": "분석 신뢰도 (높음/중간/낮음) + 이유 (예: \'중간 — e-Katalog 조달가 확보, FORNAS 등재 여부 현지 확인 필요\')"\n'
    "}\n\n"

    # ── 절대 금지 ────────────────────────────────────────────────────────────────
    "【환각 금지】 크롤 JSON에 없는 숫자·NIE 코드·브랜드명·가격을 절대 창작하지 않습니다.\n"
    "【마크다운 금지】 **, ##, 백틱(`), 하이퍼링크 문법을 절대 사용하지 않습니다.\n"
    "【출력 형식】 JSON 객체 하나만 출력합니다. 설명·서두·코드블록 없이 { 로 시작하여 } 로 끝냅니다."
)


def _build_user_prompt(meta: dict[str, str], crawl_context: str = "") -> str:
    # 개량신약·복합제 전용 추가 컨텍스트
    imd_note = ""
    if "개량신약" in meta.get("product_type", "") or "복합제" in meta.get("product_type", ""):
        imd_note = (
            "\n[개량신약·복합제 특수 분석 요건]\n"
            "- CERDAS(Cara, Efisiensi, Rasional, Daftar, Aman, Sesuai) 원칙 적용 여부 평가\n"
            "- 인도네시아 내 단일성분 제품 대비 복합제 FORNAS 등재 기준(Formularium Tingkat) 명시\n"
            "- CombiGel/Seamless Pouch 등 특허 제형의 현지 경쟁 대체품 부재 여부 평가\n"
            f"- 특허 기술({meta.get('patent_tech','')}) 관련 BPOM Patent Linkage 리스크 평가 필수\n"
        )

    crawl_section = crawl_context.strip() if crawl_context.strip() else (
        "크롤링 데이터 없음 — 크롤러 타임아웃 또는 해당 성분 미등록. "
        "시스템 프롬프트의 인도네시아 시장 컨텍스트와 제품 메타 기반으로 최선 추정값 제시."
    )

    # ── 누락 소스별 추정 경고 동적 생성 ──────────────────────────────────────────
    missing_warnings: list[str] = []
    if "[e-Katalog 크롤링 실패" in crawl_section or "조달 등록 없음" in crawl_section:
        missing_warnings.append(
            "⚠ e-Katalog 실데이터 없음 → ekatalog_price_hint·basis_procurement의 조달가·HET 수치는 "
            "모두 '(추정)' 태그 필수"
        )
    if "[FORNAS 크롤링 실패" in crawl_section or "국가처방집 미등재" in crawl_section:
        missing_warnings.append(
            "⚠ FORNAS 실데이터 없음 → FORNAS 분류·급여 등재 가능성 수치는 모두 '(추정)' 태그 필수"
        )
    if "[SwipeRx 크롤링 실패" in crawl_section or "B2B 미등록" in crawl_section:
        missing_warnings.append(
            "⚠ SwipeRx 실데이터 없음 → B2B 도매가·ref_price_text 도매 수치는 모두 '(추정)' 태그 필수"
        )
    if "[BPOM 크롤링 실패" in crawl_section or "NIE 등록 제품 없음" in crawl_section:
        missing_warnings.append(
            "⚠ BPOM 실데이터 없음 → NIE 코드·ML/MD 유형·등록 현황은 모두 '(추정)' 또는 '미확보' 표기 필수"
        )
    if "[MIMS 크롤링 실패" in crawl_section or "검색 결과 없음" in crawl_section:
        missing_warnings.append(
            "⚠ MIMS 실데이터 없음 → 경쟁 제품 목록·MIMS 분류는 '(추정)' 또는 '미확보' 표기 필수"
        )
    if "[K24Klik 크롤링 실패" in crawl_section or "소매가 데이터 없음" in crawl_section:
        missing_warnings.append(
            "⚠ K24Klik 실데이터 없음 → 소매가·ref_price_text 소매 수치는 모두 '(추정)' 태그 필수"
        )
    missing_warnings_section = (
        "\n[추정 표기 필수 항목 — 아래 소스 데이터 부재로 추정 수치에 반드시 '(추정)' 태그 부착]\n"
        + "\n".join(missing_warnings)
    ) if missing_warnings else ""

    return f"""[분석 대상 제품 — 한국유나이티드제약]
제품명(브랜드): {meta['trade_name']}
INN/성분·규격: {meta['inn']}
제형: {meta['dosage_form']}
치료 분야: {meta['therapeutic_area']}
ATC 코드: {meta['atc']}
특허·기술: {meta['patent_tech']}
제품 유형: {meta['product_type']}
HS Code: {meta['hs_code']}
MIMS 분류: {meta['mims_class']}
연관 인도네시아 의학회: {meta['medical_society']}
사전 식별 핵심 리스크: {meta.get('key_risk', '미식별')}
{imd_note}
[인도네시아 거시 시장 컨텍스트 — 분석의 배경값으로 활용]
- 인구: 2억 8,100만 명 (2024, BPS Indonesia)
- 1인당 GDP: USD 4,941 (2024, IMF) · 구매력 기준 USD 15,836
- 의약품 시장 규모: USD 87억 (2024E, IQVIA/GlobalData), 연 7~9% 성장
- 보건 지출: GDP 대비 약 3.2% (WHO 2023)
- 의약품 수입 의존도(원료): 약 90% (Kemenkes RI)
- JKN/BPJS-Kesehatan 가입률: 전체 인구 약 84% (BPJS 2024)
- FORNAS 등재 = JKN(국가건강보험) 급여 자동 인정 · LKPP e-Katalog 조달 가능
- BPOM ML(수입) 등록: 통상 12~24개월, 비용 USD 3,000~8,000
- 특허 연계(Patent Linkage): BPOM 신청 시 DGIP 특허 첨부 의무
- TKDN 현지화 요건: 수입(ML) 제품 공공조달 참여 시 일부 제한
- PBF 의무 경유 마진: 공공 15~22%, 민간 20~35%
- 수입 관세: IK-CEPA(한-인니 CEPA, 2023년 발효) 적용 시 완제의약품 HS 3004.xx 관세 0% (MFN 세율 최대 15% 대비 결정적 우위)
- PPN 부가가치세: PMK-131/2024 개정으로 표준세율 12% — 단, 의약품 등 비사치재는 과세표준 11/12 적용 → 실효세율 11% 유지 (2025.01.01 시행)
- 환율 기준: 1 USD ≈ Rp 15,750, 1 IDR ≈ 0.085 KRW
- FOB 수출가 역산 로직 A (공공 e-Katalog 시장): 목표 입찰가(IDR) × 0.30 계수 → FOB (수입원가·유통마진·파트너이익 포함)
- FOB 수출가 역산 로직 B (민간 소매 시장): 목표 HET ÷ 1.11(VAT) ÷ 1.28(약국 마진) ÷ 1.15(PBF 마진) ÷ 1.05(운임·보험) = FOB
- 파트너 필터 조건: 동일성분 미보유사 우선 (자가잠식 방지), 순환기 파이프라인 보유사 = 교차판매 시너지 극대화

[크롤링 수집 데이터 — BPOM·e-Katalog·FORNAS·MIMS·K24Klik·SwipeRx]
{crawl_section}

{missing_warnings_section}
[작성 지시]
위 제품에 대해 시스템 프롬프트의 JSON 스키마를 정확히 따라 분석 보고서를 작성하세요.
- 크롤 데이터에 있는 NIE·가격·제품명은 반드시 그대로 인용합니다.
- 크롤 데이터에 없는 항목은 시장 컨텍스트+제품 특성 기반 추정치를 출처·연도와 함께 제시하되, 수치 뒤에 반드시 '(추정)' 태그를 붙입니다.
- 모든 IDR 가격은 Rp X,XXX 형식으로 표기합니다.
- JSON 객체 하나만 반환합니다. {{ 로 시작하여 }} 로 끝내며, 코드블록·서두 설명 없이 출력합니다."""


# ── 크롤링 데이터 통합 ─────────────────────────────────────────────────────────

def _inn_primary(inn: str) -> str:
    """복합제 INN에서 주성분 첫 단어 추출.
    예) 'Rosuvastatin 5mg + Omega-3...' → 'Rosuvastatin'
        'Salmeterol 50μg + Fluticasone...' → 'Salmeterol'
    """
    return inn.split(" ")[0]


# ── 제품별 크롤 검색어 오버라이드 ──────────────────────────────────────────────
# _inn_primary()가 잘못된 키워드를 추출하는 제품에 대해 명시적으로 지정.
# 예) Gadobutrol → 인도네시아 검색어 "gadobutrol" (단일 단어로도 매칭 미흡)
#     Omega-3-acid ethyl esters → "omega-3" (첫 단어 추출 시 영양제 혼동)
_CRAWL_KEYWORD_OVERRIDE: dict[str, str] = {
    "ID_gadvoa_inj":       "gadobutrol",
    "ID_omethyl_cutielet": "omega-3",
}


def _crawl_keyword(meta: dict[str, str]) -> str:
    """크롤 검색어 결정.

    제품별 오버라이드(_CRAWL_KEYWORD_OVERRIDE)가 있으면 그것을 사용하고,
    없으면 INN 첫 단어(_inn_primary)로 폴백한다.
    """
    return _CRAWL_KEYWORD_OVERRIDE.get(meta["product_id"]) or _inn_primary(meta["inn"])


def _db_rows_to_crawl(source_key: str, db_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DB 저장 행을 크롤 원시 포맷으로 역변환.

    fetch_crawl_cache() 결과를 기존 크롤 딕셔너리 형식으로 변환하여
    _fetch_crawl_context() 포맷팅 코드를 재사용할 수 있게 함.
    """
    results: list[dict[str, Any]] = []
    for row in db_rows:
        cs = row.get("country_specific") or {}
        base: dict[str, Any] = {
            "product_name": row.get("trade_name", ""),
            "inn":          row.get("active_ingredient", ""),
            "strength":     row.get("strength", ""),
            "dosage_form":  row.get("dosage_form", ""),
            "_from_cache":  True,
            "_cached_at":   row.get("crawled_at", ""),
        }
        if source_key == "ID:bpom":
            base.update({
                "reg_no":       row.get("registration_number") or cs.get("nie", ""),
                "nie":          row.get("registration_number") or cs.get("nie", ""),
                "reg_type":     cs.get("ml_md", ""),
                "status":       cs.get("status", ""),
                "expiry_date":  cs.get("expiry_date", ""),
                "atc_code":     cs.get("atc_code", ""),
                "manufacturer": cs.get("manufacturer", ""),
                "registrar":    cs.get("manufacturer", ""),
            })
        elif source_key == "ID:ekatalog":
            base.update({
                "price_idr": cs.get("price_idr") or row.get("price_local"),
                "het_idr":   cs.get("het_idr"),
                "satuan":    cs.get("satuan", ""),
                "supplier":  cs.get("supplier", ""),
                "year":      cs.get("year", ""),
            })
        elif source_key == "ID:fornas":
            base.update({
                "fornas_class": cs.get("tingkat", ""),
                "tingkat":      cs.get("tingkat", ""),
                "restriction":  cs.get("restriction", ""),
                "indication":   cs.get("indication", ""),
            })
        elif source_key == "ID:mims":
            base.update({
                "drug_type":    cs.get("drug_type", ""),
                "mims_class":   cs.get("mims_class", ""),
                "indication":   cs.get("indication", ""),
                "detail_url":   cs.get("detail_url", ""),
                "manufacturer": "",
                "company":      "",
            })
        elif source_key == "ID:k24klik":
            base.update({
                "price_idr":    cs.get("price_idr") or row.get("price_local"),
                "price_unit":   cs.get("price_unit", ""),
                "stock_status": cs.get("stock_status", ""),
                "product_url":  cs.get("product_url", ""),
                "manufacturer": "",
            })
        elif source_key == "ID:swiperx":
            base.update({
                "price_idr":    cs.get("price_idr") or row.get("price_local"),
                "category":     cs.get("category", ""),
                "pack_size":    cs.get("pack_size", ""),
                "manufacturer": cs.get("manufacturer", ""),
            })
        results.append(base)
    return results


async def _fetch_crawl_context(meta: dict[str, str]) -> str:
    """BPOM · e-Katalog · FORNAS · MIMS · K24Klik · SwipeRx 6개 소스
    병렬 크롤링 후 Claude 분석 컨텍스트 문자열로 반환.

    DB 적재 & 캐시 폴백 전략:
      - 크롤 성공 → Supabase products 테이블에 즉시 upsert (누적 적재)
      - 크롤 실패·타임아웃 → 7일 이내 DB 캐시로 자동 폴백
      - 양쪽 모두 없으면 → 기존 오류 메시지 유지
    """
    product_id = meta["product_id"]
    kw = _crawl_keyword(meta)

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
    from utils.db import save_crawl_results, fetch_crawl_cache

    (bpom_r, ek_r, fornas_r, mims_r, k24_r, swrx_r) = await asyncio.gather(
        _safe(search_bpom(kw,     max_results=5), "BPOM"),
        _safe(search_ekatalog(kw, max_results=5), "e-Katalog"),
        _safe(search_fornas(kw,   max_results=5), "FORNAS"),
        _safe(search_mims(kw,     max_results=5), "MIMS"),
        _safe(search_k24klik(kw,  max_results=5), "K24Klik"),
        _safe(search_swiperx(kw,  max_results=5), "SwipeRx"),
    )

    # ── DB 적재 & 캐시 폴백 ───────────────────────────────────────────────────
    def _has_valid(r: Any) -> bool:
        return isinstance(r, list) and any(
            rec.get("product_name") and not rec.get("error") for rec in r
        )

    def _save_or_fallback(result: Any, source_key: str) -> Any:
        """유효 데이터 → DB 저장 후 원본 반환.
        빈/에러 → DB 캐시 폴백 (7일).
        """
        if _has_valid(result):
            valid = [r for r in result if r.get("product_name") and not r.get("error")]
            try:
                save_crawl_results(product_id, source_key, valid, kw)
            except Exception:
                pass   # DB 저장 실패해도 분석은 계속 진행
            return result
        # 폴백: DB 캐시
        cached = fetch_crawl_cache(product_id, source_key, max_age_hours=168)
        if cached:
            return _db_rows_to_crawl(source_key, cached)
        return result   # 캐시도 없으면 원본 에러 반환

    bpom_r   = _save_or_fallback(bpom_r,   "ID:bpom")
    ek_r     = _save_or_fallback(ek_r,     "ID:ekatalog")
    fornas_r = _save_or_fallback(fornas_r, "ID:fornas")
    mims_r   = _save_or_fallback(mims_r,   "ID:mims")
    k24_r    = _save_or_fallback(k24_r,    "ID:k24klik")
    swrx_r   = _save_or_fallback(swrx_r,   "ID:swiperx")

    # ── 2차 검색: MIMS 브랜드명 → BPOM·K24Klik 보강 ─────────────────────────
    # MIMS는 인도네시아 내 등록 브랜드 목록을 반환한다.
    # INN 검색만으로는 BPOM에서 브랜드 제품이 누락되고 K24Klik도 1건만 나오는
    # 문제를 MIMS 브랜드명 → 2차 검색으로 해결한다.
    _mims_brands: list[str] = []
    if isinstance(mims_r, list):
        seen_k24 = {
            (r.get("product_name") or "").lower()
            for r in (k24_r if isinstance(k24_r, list) else [])
            if r.get("product_name")
        }
        seen_bpom = {
            (r.get("product_name") or "").lower()
            for r in (bpom_r if isinstance(bpom_r, list) else [])
            if r.get("product_name")
        }
        for m in mims_r:
            brand = (m.get("product_name") or "").strip()
            if not brand or m.get("error"):
                continue
            _mims_brands.append(brand)

        if _mims_brands:
            # BPOM 2차: 브랜드별 인허가 상태 조회 (아직 없는 것만)
            bpom_extra: list[dict[str, Any]] = []
            for brand in _mims_brands[:6]:          # 최대 6개 브랜드
                if brand.lower() in seen_bpom:
                    continue
                extra = await _safe(search_bpom(brand, max_results=2), f"BPOM/{brand}")
                if isinstance(extra, list):
                    valid_extra = [
                        x for x in extra
                        if x.get("product_name") and not x.get("error")
                    ]
                    bpom_extra.extend(valid_extra)
                    if valid_extra:
                        try:
                            save_crawl_results(product_id, "ID:bpom", valid_extra, brand)
                        except Exception:
                            pass
            if bpom_extra:
                bpom_r = (bpom_r if isinstance(bpom_r, list) else []) + bpom_extra

            # K24Klik 2차: 브랜드별 소매가 조회 (아직 없는 것만)
            k24_extra: list[dict[str, Any]] = []
            for brand in _mims_brands[:6]:
                if brand.lower() in seen_k24:
                    continue
                extra = await _safe(search_k24klik(brand, max_results=2), f"K24/{brand}")
                if isinstance(extra, list):
                    valid_extra = [
                        x for x in extra
                        if x.get("product_name") and not x.get("error")
                    ]
                    k24_extra.extend(valid_extra)
                    if valid_extra:
                        try:
                            save_crawl_results(product_id, "ID:k24klik", valid_extra, brand)
                        except Exception:
                            pass
            if k24_extra:
                k24_r = (k24_r if isinstance(k24_r, list) else []) + k24_extra

    # ── 컨텍스트 문자열 빌드 ────────────────────────────────────────────────────
    lines: list[str] = []

    def _fmt_idr(val: object, unit: str = "") -> str:
        """숫자를 'Rp XX,XXX/unit' 형태로 포맷. 불명확하면 '가격 미상' 반환."""
        if isinstance(val, (int, float)) and val > 0:
            return f"Rp {int(val):,}{('/' + unit) if unit else ''}"
        return "가격 미상"

    def _cache_tag(rlist: list) -> str:
        """캐시 데이터인 경우 '(DB캐시)' 태그 반환."""
        if rlist and rlist[0].get("_from_cache"):
            ts = (rlist[0].get("_cached_at") or "")[:10]
            return f" [DB캐시 {ts}]"
        return ""

    # ── BPOM 등록 현황 ─────────────────────────────────────────────────────────
    if isinstance(bpom_r, list):
        real = [r for r in bpom_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append(f"=== BPOM 등록 현황 (NIE 보유 제품){_cache_tag(real)} ===")
            for r in real:
                mfr      = r.get("manufacturer") or r.get("registrar") or "미상"
                reg_type = r.get("reg_type") or ("ML" if "import" in mfr.lower() else "")
                exp_date = r.get("expiry_date") or r.get("exp_date") or ""
                lines.append(
                    f"• {r.get('product_name','')} "
                    f"| NIE: {r.get('reg_no', r.get('nie','미상'))} "
                    f"| 유형: {reg_type or '미상'} "
                    f"| 제형: {r.get('dosage_form','')} "
                    f"| 제조/등록사: {mfr} "
                    f"| 상태: {r.get('status','활성')} "
                    f"| 유효기간: {exp_date or '미상'} "
                    f"| ATC: {r.get('atc_code','')}"
                )
        else:
            lines.append(
                f"[BPOM] '{kw}' 관련 NIE 등록 제품 없음 "
                "→ 한국유나이티드제약 신규 ML 코드 등록 필요. 통상 12~24개월 소요."
            )
    else:
        lines.append(f"[BPOM 크롤링 실패: {bpom_r}]")

    # ── e-Katalog 공공조달가 ───────────────────────────────────────────────────
    if isinstance(ek_r, list):
        real = [r for r in ek_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append(f"=== e-Katalog LKPP 공공조달가{_cache_tag(real)} ===")
            for r in real:
                price_str = _fmt_idr(r.get("price_idr"), r.get("satuan", "단위"))
                het_str   = _fmt_idr(r.get("het_idr"), r.get("satuan", "단위")) if r.get("het_idr") else ""
                lines.append(
                    f"• {r.get('product_name','')} "
                    f"| 조달가: {price_str} "
                    f"| HET: {het_str or '미상'} "
                    f"| 공급사: {r.get('supplier', r.get('manufacturer','미상'))} "
                    f"| 단위: {r.get('satuan','')} "
                    f"| 연도: {r.get('year', r.get('tahun',''))}"
                )
        else:
            lines.append(
                f"[e-Katalog] '{kw}' 조달 등록 없음 "
                "→ BPOM ML 취득 후 LKPP e-Katalog 등록 필요 (FORNAS 등재 선행 권장)."
            )
    else:
        lines.append(f"[e-Katalog 크롤링 실패: {ek_r}]")

    # ── FORNAS 국가처방집 등재 현황 ──────────────────────────────────────────────
    if isinstance(fornas_r, list):
        real = [r for r in fornas_r if (r.get("inn") or r.get("product_name")) and not r.get("error")]
        if real:
            lines.append(f"=== FORNAS 국가처방집 등재 현황{_cache_tag(real)} ===")
            for r in real:
                name  = r.get("inn") or r.get("product_name") or ""
                tier  = r.get("fornas_class") or r.get("tingkat") or r.get("level") or "미상"
                restr = r.get("restriction") or r.get("pembatasan") or "없음"
                lines.append(
                    f"• {name} "
                    f"| 규격: {r.get('strength','')} "
                    f"| 제형: {r.get('dosage_form','')} "
                    f"| FORNAS 분류: {tier} "
                    f"| 급여 제한: {restr} "
                    f"| 적응증: {r.get('indication','')}"
                )
        else:
            lines.append(
                f"[FORNAS] '{kw}' 국가처방집 미등재 "
                "→ JKN(BPJS-Kesehatan) 급여 접근 불가. FORNAS 등재 전략 필수."
            )
    else:
        lines.append(f"[FORNAS 크롤링 실패: {fornas_r}]")

    # ── MIMS Indonesia 경쟁 제품 ──────────────────────────────────────────────
    if isinstance(mims_r, list):
        real = [r for r in mims_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append(f"=== MIMS Indonesia 경쟁 제품 (상위 {min(len(real), 5)}개){_cache_tag(real)} ===")
            for r in real[:5]:
                rx_otc    = r.get("drug_type") or r.get("prescription_type") or ""
                mfr       = r.get("manufacturer") or r.get("company") or "미상"
                price_str = _fmt_idr(r.get("price_idr"))
                lines.append(
                    f"• {r.get('product_name','')} "
                    f"| {rx_otc} "
                    f"| 성분: {r.get('inn','')} "
                    f"| MIMS 분류: {r.get('mims_class','')} "
                    f"| 제조사: {mfr} "
                    f"| 가격: {price_str}"
                )
        else:
            lines.append(f"[MIMS] '{kw}': 검색 결과 없음 — 경쟁 제품 현지 미입점 가능성")
    else:
        lines.append(f"[MIMS 크롤링 실패: {mims_r}]")

    # ── K24Klik 온라인 약국 소매가 ────────────────────────────────────────────
    if isinstance(k24_r, list):
        real = [r for r in k24_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append(f"=== K24Klik 온라인 약국 소매가{_cache_tag(real)} ===")
            for r in real[:5]:
                unit      = r.get("price_unit") or r.get("satuan") or "단위"
                price_str = _fmt_idr(r.get("price_idr"), unit)
                lines.append(
                    f"• {r.get('product_name','')} "
                    f"| 소매가: {price_str} "
                    f"| 제조사: {r.get('manufacturer','미상')} "
                    f"| 재고: {r.get('stock_status','미상')}"
                )
        else:
            lines.append(f"[K24Klik] '{kw}': 민간 온라인 약국 미입점 — 소매가 데이터 없음")
    else:
        lines.append(f"[K24Klik 크롤링 실패: {k24_r}]")

    # ── SwipeRx B2B 도매가 ────────────────────────────────────────────────────
    if isinstance(swrx_r, list):
        real = [r for r in swrx_r if r.get("product_name") and not r.get("error")]
        if real:
            lines.append(f"=== SwipeRx B2B 도매가 (약국·병원 대상){_cache_tag(real)} ===")
            for r in real[:5]:
                price_str = _fmt_idr(r.get("price_idr"))
                lines.append(
                    f"• {r.get('product_name','')} "
                    f"| B2B 도매가: {price_str} "
                    f"| 제조사: {r.get('manufacturer','미상')} "
                    f"| 카테고리: {r.get('category','')} "
                    f"| 포장단위: {r.get('pack_size','')}"
                )
        else:
            lines.append(f"[SwipeRx] '{kw}': B2B 미등록 또는 로그인 필요")
    else:
        lines.append(f"[SwipeRx 크롤링 실패: {swrx_r}]")

    # ── 데이터 품질 요약 ───────────────────────────────────────────────────────
    def _count_valid(r: Any, key: str = "product_name") -> bool:
        return isinstance(r, list) and bool(
            [x for x in r if (x.get(key) or x.get("product_name")) and not x.get("error")]
        )

    sources_ok = sum([
        _count_valid(bpom_r),
        _count_valid(ek_r),
        _count_valid(fornas_r, "inn"),
        _count_valid(mims_r),
        _count_valid(k24_r),
        _count_valid(swrx_r),
    ])
    from_cache = sum([
        isinstance(bpom_r,   list) and bool(bpom_r)   and bpom_r[0].get("_from_cache",   False),
        isinstance(ek_r,     list) and bool(ek_r)     and ek_r[0].get("_from_cache",     False),
        isinstance(fornas_r, list) and bool(fornas_r) and fornas_r[0].get("_from_cache", False),
        isinstance(mims_r,   list) and bool(mims_r)   and mims_r[0].get("_from_cache",   False),
        isinstance(k24_r,    list) and bool(k24_r)    and k24_r[0].get("_from_cache",    False),
        isinstance(swrx_r,   list) and bool(swrx_r)   and swrx_r[0].get("_from_cache",   False),
    ])
    lines.append(
        f"\n[크롤링 데이터 품질] 유효 데이터: {sources_ok}/6 소스 "
        f"(실시간 {sources_ok - from_cache}개 + DB캐시 {from_cache}개) "
        f"(BPOM/e-Katalog/FORNAS/MIMS/K24Klik/SwipeRx)"
    )

    return "\n".join(lines) if lines else ""


# ── Claude 호출 ───────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict[str, Any] | None:
    """응답 텍스트에서 JSON 객체를 추출합니다.
    전략 1: 코드블록 내 JSON (```json ... ```)
    전략 2: 중괄호 범위 추출 (가장 큰 { ... })
    전략 3: raw 전체 파싱
    """
    import re

    # 전략 1: ```json ... ``` 블록
    m = re.search(r"```json\s*(\{.*?\})\s*```", raw, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 전략 2: 가장 바깥 중괄호 범위 (중첩 대응)
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # 전략 3: raw 전체
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return None


async def _claude_analyze(
    meta: dict[str, str],
    crawl_context: str,
    claude_key: str,
    model: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Claude API 호출 → JSON 파싱 (재시도 1회 포함)."""
    import anthropic  # type: ignore

    client = anthropic.AsyncAnthropic(api_key=claude_key)
    user_prompt = _build_user_prompt(meta, crawl_context)

    for attempt in range(2):
        try:
            msg = await client.messages.create(
                model=model,
                max_tokens=3500,          # 15개 필드 × 3~5문장 → 충분한 여유 확보
                temperature=0.2 if attempt == 0 else 0.05,   # 재시도 시 결정론적
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = msg.content[0].text.strip()
            parsed = _extract_json(raw)
            if parsed is not None:
                return parsed, None

            # JSON 파싱 실패 — 재시도 전 잠깐 대기
            if attempt == 0:
                await asyncio.sleep(1)
                continue

            return None, f"json_parse_error: JSON 블록을 찾을 수 없습니다. 응답 앞부분: {raw[:200]}"

        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            return None, f"claude_failed: {e}"

    return None, "claude_failed: 재시도 모두 실패"


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
