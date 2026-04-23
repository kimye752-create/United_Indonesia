"""Perplexity API로 품목별 관련 논문·레퍼런스 검색.

PERPLEXITY_API_KEY 설정 시 자동 실행.
미설정 시 빈 리스트 반환 (UI에서 "API 키 미설정" 표시).

쿼리 방향 (공통):
  - 등재 품목: 임상 근거 + 현지 시장 데이터
  - 미등재 품목(개량신약): 규제 진입 경로 + 복합제 승인 사례 중심

지원 국가:
  - SG (Singapore): HSA / NDF / GeBIZ 기반 쿼리
  - ID (Indonesia): BPOM / FORNAS / e-Katalog / BPJS-Kesehatan 기반 쿼리

출력 (품목별):
  [
    {"title": "...", "url": "https://...", "reason": "한 줄 근거", "source": "PubMed 등"},
    ...
  ]
"""

from __future__ import annotations

import os
from typing import Any

# ── Singapore (SG) 품목 쿼리 ──────────────────────────────────────────────────
_SG_QUERIES: dict[str, str] = {
    "SG_hydrine_hydroxyurea_500": (
        "hydroxyurea hospital procurement Singapore MOH tender clinical evidence "
        "sickle cell chronic myeloid leukemia treatment guidelines Asia"
    ),
    "SG_gadvoa_gadobutrol_604": (
        "gadobutrol MRI contrast agent HSA Singapore registration macrocyclic GBCA "
        "safety efficacy radiology hospital formulary Southeast Asia"
    ),
    "SG_sereterol_activair": (
        "fluticasone salmeterol fixed dose combination HSA Singapore registration "
        "asthma COPD inhaler GINA GOLD guideline Southeast Asia market"
    ),
    "SG_omethyl_omega3_2g": (
        "omega-3 ethyl esters 2g single capsule HSA Singapore new drug application "
        "hypertriglyceridemia NDA registration pathway REDUCE-IT cardiovascular"
    ),
    "SG_rosumeg_combigel": (
        "rosuvastatin omega-3 fixed dose combination HSA Singapore approval pathway "
        "NDA registration dyslipidemia combination product regulatory Southeast Asia"
    ),
    "SG_atmeg_combigel": (
        "atorvastatin omega-3 fixed dose combination approval pathway Singapore "
        "HSA NDA registration IMD incrementally modified drug dyslipidemia Asia"
    ),
    "SG_ciloduo_cilosta_rosuva": (
        "cilostazol new drug registration Asia Singapore HSA NDA approval pathway "
        "peripheral artery disease rosuvastatin combination regulatory evidence"
    ),
    "SG_gastiin_cr_mosapride": (
        "mosapride regulatory approval Southeast Asia Singapore HSA new market entry "
        "prokinetic gastric motility NDA registration sustained release clinical"
    ),
}

# ── Indonesia (ID) 품목 쿼리 ──────────────────────────────────────────────────
_ID_QUERIES: dict[str, str] = {
    "ID_rosumeg_combigel": (
        "rosuvastatin omega-3 fixed dose combination BPOM Indonesia registration "
        "FORNAS dyslipidemia combination product regulatory approval e-Katalog BPJS"
    ),
    "ID_atmeg_combigel": (
        "atorvastatin omega-3 fixed dose combination BPOM Indonesia approval pathway "
        "FORNAS registration IMD incrementally modified drug dyslipidemia BPJS-Kesehatan"
    ),
    "ID_ciloduo": (
        "cilostazol rosuvastatin fixed dose combination BPOM Indonesia registration "
        "peripheral artery disease cardiovascular e-Katalog FORNAS clinical evidence"
    ),
    "ID_omethyl_cutielet": (
        "omega-3 ethyl esters 2g seamless capsule BPOM Indonesia registration "
        "hypertriglyceridemia NDA FORNAS BPJS-Kesehatan cardiovascular clinical"
    ),
    "ID_gastiin_cr": (
        "mosapride sustained release BPOM Indonesia registration approval pathway "
        "functional dyspepsia prokinetic CR tablet FORNAS market entry Southeast Asia"
    ),
    "ID_sereterol_activair": (
        "fluticasone salmeterol DPI inhaler BPOM Indonesia registration FORNAS "
        "asthma COPD GINA GOLD guideline PDPI BPJS-Kesehatan clinical evidence"
    ),
    "ID_gadvoa_inj": (
        "gadobutrol MRI contrast agent BPOM Indonesia registration macrocyclic GBCA "
        "e-Katalog hospital procurement PDSRI radiology formulary Southeast Asia"
    ),
    "ID_hydrine": (
        "hydroxyurea BPOM Indonesia registration FORNAS oncology procurement "
        "CML sickle cell e-Katalog BPJS-Kesehatan hospital cancer treatment"
    ),
}

# ── 통합 쿼리 (SG + ID) ─────────────────────────────────────────────────────
_QUERIES: dict[str, str] = {**_SG_QUERIES, **_ID_QUERIES}

# ── 쿼리 초점 유형 ──────────────────────────────────────────────────────────
_SG_QUERY_FOCUS: dict[str, str] = {
    "SG_hydrine_hydroxyurea_500": "clinical_evidence",
    "SG_gadvoa_gadobutrol_604": "clinical_evidence",
    "SG_sereterol_activair": "clinical_evidence",
    "SG_omethyl_omega3_2g": "regulatory_pathway",
    "SG_rosumeg_combigel": "regulatory_pathway",
    "SG_atmeg_combigel": "regulatory_pathway",
    "SG_ciloduo_cilosta_rosuva": "regulatory_pathway",
    "SG_gastiin_cr_mosapride": "regulatory_pathway",
}

_ID_QUERY_FOCUS: dict[str, str] = {
    "ID_rosumeg_combigel":   "regulatory_pathway",
    "ID_atmeg_combigel":     "regulatory_pathway",
    "ID_ciloduo":            "regulatory_pathway",
    "ID_omethyl_cutielet":   "regulatory_pathway",
    "ID_gastiin_cr":         "regulatory_pathway",
    "ID_sereterol_activair": "clinical_evidence",
    "ID_gadvoa_inj":         "clinical_evidence",
    "ID_hydrine":            "clinical_evidence",
}

_QUERY_FOCUS: dict[str, str] = {**_SG_QUERY_FOCUS, **_ID_QUERY_FOCUS}


def _is_indonesia(product_id: str) -> bool:
    return product_id.startswith("ID_")


def _system_msg(product_id: str, focus: str) -> str:
    """국가별 시스템 메시지 반환."""
    if _is_indonesia(product_id):
        if focus == "regulatory_pathway":
            return (
                "You are a pharmaceutical regulatory expert specializing in Indonesia BPOM "
                "and ASEAN drug registration. Focus on BPOM registration pathways (ML/MD codes), "
                "FORNAS listing, BPJS-Kesehatan coverage, e-Katalog procurement, and "
                "combination product registration precedents in Indonesia."
            )
        else:
            return (
                "You are a pharmaceutical research assistant specializing in Indonesia "
                "and Southeast Asian pharmaceutical markets. Focus on clinical evidence, "
                "BPOM/FORNAS guidelines, BPJS-Kesehatan formulary, and market data."
            )
    else:
        if focus == "regulatory_pathway":
            return (
                "You are a pharmaceutical regulatory expert specializing in Singapore HSA "
                "and Southeast Asian drug registration. Focus on regulatory approval pathways, "
                "NDA requirements, combination product registration, and market entry precedents."
            )
        else:
            return (
                "You are a pharmaceutical research assistant specializing in Singapore "
                "and Southeast Asian markets. Focus on clinical evidence, market data, "
                "and Singapore MOH/HSA guidelines."
            )


def _reason_instruction(product_id: str, focus: str) -> str:
    """국가별 reason 작성 지시문 반환."""
    if _is_indonesia(product_id):
        if focus == "regulatory_pathway":
            return "반드시 한국어로: 이 자료가 인도네시아 BPOM 등록·FORNAS 등재 진입 경로 판단에 관련 있는 이유를 한 문장으로 요약"
        else:
            return "반드시 한국어로: 이 논문/자료가 인도네시아 수출 적합성 판단에 관련 있는 이유를 한 문장으로 요약"
    else:
        if focus == "regulatory_pathway":
            return "반드시 한국어로: 이 자료가 싱가포르 HSA 등록 진입 경로 판단에 관련 있는 이유를 한 문장으로 요약"
        else:
            return "반드시 한국어로: 이 논문/자료가 싱가포르 수출 적합성 판단에 관련 있는 이유를 한 문장으로 요약"


async def fetch_references(
    product_id: str,
    max_refs: int = 4,
) -> list[dict[str, str]]:
    """Perplexity sonar-pro로 관련 논문·규제 사례 검색.

    Returns:
        [{"title", "url", "reason", "source"}, ...]
        API 키 없으면 빈 리스트.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return []

    query = _QUERIES.get(product_id)
    if not query:
        return []

    try:
        import httpx
    except ImportError:
        return []

    focus = _QUERY_FOCUS.get(product_id, "clinical_evidence")
    system_msg = _system_msg(product_id, focus)
    reason_inst = _reason_instruction(product_id, focus)

    prompt = f"""Find {max_refs} relevant academic papers, regulatory documents, or clinical studies for:
"{query}"

IMPORTANT: The "reason" field MUST be written in Korean (한국어). Do not use English for the reason field.

Return ONLY valid JSON array, no other text:
[
  {{
    "title": "<paper or document title in original language>",
    "url": "<direct URL to paper, PubMed, or regulatory document>",
    "reason": "<{reason_inst} — 반드시 한국어 한 문장>",
    "source": "<PubMed / Lancet / NEJM / BPOM / FORNAS / MOH / WHO 등>"
  }}
]"""

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 800,
                    "return_citations": True,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            if "```" in content:
                for part in content.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("["):
                        content = part
                        break

            import json
            refs = json.loads(content)
            return [r for r in refs if r.get("url")][:max_refs]

    except Exception:
        return []


async def fetch_references_for_custom(
    trade_name: str,
    inn: str,
    target_country: str = "Indonesia",
    max_refs: int = 4,
) -> list[dict[str, str]]:
    """신약(커스텀 입력) 논문·규제 사례 검색.

    Args:
        trade_name: 상품명
        inn:        성분명
        target_country: "Indonesia" 또는 "Singapore"
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return []
    try:
        import httpx
    except ImportError:
        return []

    is_id = target_country.lower() in ("indonesia", "id")

    if is_id:
        query = (
            f"BPOM Indonesia registration status, FORNAS listing, e-Katalog procurement, "
            f"clinical evidence and market data for {trade_name} ({inn}). "
            f"Include BPJS-Kesehatan coverage, BPOM ML/MD registration pathway, "
            f"and any Indonesia regulatory decisions."
        )
        system_msg = (
            "You are a pharmaceutical regulatory expert specializing in Indonesia BPOM "
            "and ASEAN drug registration. Focus on BPOM registration, FORNAS listing, "
            "BPJS-Kesehatan coverage, and e-Katalog procurement."
        )
        reason_inst = "반드시 한국어로: 이 자료가 인도네시아 BPOM 등록·수출 적합성 판단에 관련 있는 이유를 한 문장으로 요약"
    else:
        query = (
            f"Singapore HSA regulatory approval status, clinical evidence, and market data "
            f"for {trade_name} ({inn}). Include registration precedents, formulary listing, "
            f"and any Singapore MOH or HSA decisions."
        )
        system_msg = (
            "You are a pharmaceutical regulatory expert specializing in Singapore HSA."
        )
        reason_inst = "반드시 한국어로: 이 자료가 싱가포르 HSA 등록 판단에 관련 있는 이유를 한 문장으로 요약"

    prompt = f"""Find {max_refs} relevant academic papers, regulatory documents, or clinical studies for:
"{query}"

IMPORTANT: The "reason" field MUST be written in Korean (한국어). Do not use English for the reason field.

Return ONLY valid JSON array, no other text:
[
  {{
    "title": "<paper or document title in original language>",
    "url": "<direct URL to paper, PubMed, or regulatory document>",
    "reason": "<{reason_inst}>",
    "source": "<PubMed / Lancet / NEJM / BPOM / FORNAS / HSA / MOH / WHO 등>"
  }}
]"""

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 800,
                    "return_citations": True,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if "```" in content:
                for part in content.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("["):
                        content = part
                        break
            import json as _json
            refs = _json.loads(content)
            return [r for r in refs if r.get("url")][:max_refs]
    except Exception:
        return []


async def fetch_all_references(
    product_ids: list[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """전체 품목 논문·규제 사례 검색. product_ids 미지정 시 현재 국가(ID) 기준 전체."""
    import asyncio

    if product_ids:
        targets = product_ids
    else:
        # 기본: Indonesia 품목 전체
        targets = list(_ID_QUERIES.keys())

    tasks = {pid: fetch_references(pid) for pid in targets}
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))
