"""인도네시아 수출 분석 보고서 PDF 생성기 (ReportLab).

섹션 구성:
  표지  — 제품명 / 회사 / 날짜 / Indonesia
  P1   — 1공정: 시장조사 분석 (판정·근거·규제·가격·리스크·논문)
  P2   — 2공정: 수출 가격 전략 (시나리오·FOB·공공·민간)
  P3   — 3공정: 바이어 발굴 (요약 테이블·기업 상세)

공개 API:
  generate(data_dict, output_path, report_type="final")
    data_dict  : gen_id_report.js와 동일한 JSON 구조
    output_path: Path | str
    report_type: "p1" | "p2" | "p3" | "final"

통화 표시 원칙:
  모든 금액 → IDR XX,XXX / USD X.XX / ₩X,XXX KRW (3중 표기)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── 한글 폰트 등록 ────────────────────────────────────────────────────────────

def _register_korean_fonts() -> tuple[str, str]:
    """Malgun Gothic (Windows) → NanumGothic (내장 폴더) → Helvetica 순으로 폴백."""
    candidates = [
        # Windows 기본 한글 폰트
        (r"C:\Windows\Fonts\malgun.ttf",   r"C:\Windows\Fonts\malgunbd.ttf"),
        # 프로젝트 내장 폰트
        (str(Path(__file__).resolve().parents[1] / "fonts" / "NanumGothic.ttf"),
         str(Path(__file__).resolve().parents[1] / "fonts" / "NanumGothicBold.ttf")),
        # macOS/Linux NanumGothic
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ]
    for reg_path, bold_path in candidates:
        if Path(reg_path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("KR",      reg_path))
                if Path(bold_path).is_file():
                    pdfmetrics.registerFont(TTFont("KR-Bold", bold_path))
                    return "KR", "KR-Bold"
                else:
                    pdfmetrics.registerFont(TTFont("KR-Bold", reg_path))  # same as regular
                    return "KR", "KR-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


_FONT, _FONT_B = _register_korean_fonts()

# ── 색상 팔레트 ────────────────────────────────────────────────────────────────
_NAVY    = colors.Color(23 / 255,  63 / 255, 120 / 255)   # 헤더 네이비
_GREEN   = colors.Color(39 / 255, 174 / 255,  96 / 255)   # 적합 판정
_ORANGE  = colors.Color(230 / 255, 126 / 255, 34 / 255)   # 경고
_RED     = colors.Color(192 / 255,  57 / 255, 43 / 255)   # 부적합
_LIGHT   = colors.Color(245 / 255, 247 / 255, 250 / 255)  # 테이블 짝수행
_MUTED   = colors.Color(120 / 255, 130 / 255, 150 / 255)  # 부제
_REASON  = colors.Color(235 / 255, 245 / 255, 255 / 255)  # 강조 박스
_AMBER   = colors.Color(255 / 255, 248 / 255, 225 / 255)  # 리스크 박스
_WHITE   = colors.white
_BLACK   = colors.black

W, H = A4
_MARGIN_L = 18 * mm
_MARGIN_R = 18 * mm
_MARGIN_T = 16 * mm
_MARGIN_B = 16 * mm
_CONTENT_W = W - _MARGIN_L - _MARGIN_R  # ≈ 159 mm


# ── 스타일 팩토리 ──────────────────────────────────────────────────────────────

def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    def s(name: str, parent: str = "Normal", **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        # ── 표지 ──
        "cover_company": s("cover_company", fontSize=11, leading=15,
                           textColor=_MUTED, fontName=_FONT, spaceAfter=6),
        "cover_title":   s("cover_title",   fontSize=26, leading=34,
                           textColor=_NAVY, fontName=_FONT_B, spaceAfter=4),
        "cover_inn":     s("cover_inn",     fontSize=13, leading=18,
                           textColor=_MUTED, fontName=_FONT, spaceAfter=10),
        "cover_meta":    s("cover_meta",    fontSize=10, leading=14,
                           textColor=_BLACK, fontName=_FONT, spaceAfter=2),

        # ── 섹션 / 내용 ──
        "h1":    s("h1",    fontSize=14, leading=20, textColor=_NAVY,
                   fontName=_FONT_B, spaceBefore=10, spaceAfter=4),
        "h2":    s("h2",    fontSize=11, leading=16, textColor=_NAVY,
                   fontName=_FONT_B, spaceBefore=6, spaceAfter=2),
        "h3":    s("h3",    fontSize=10, leading=14, textColor=_MUTED,
                   fontName=_FONT_B, spaceBefore=4, spaceAfter=2),
        "body":  s("body",  fontSize=9,  leading=14, textColor=_BLACK,
                   fontName=_FONT, spaceAfter=2),
        "small": s("small", fontSize=8,  leading=12, textColor=_MUTED,
                   fontName=_FONT),
        "bold":  s("bold",  fontSize=9,  leading=14, textColor=_BLACK,
                   fontName=_FONT_B),

        # ── 특수 박스 ──
        "verdict_ok":   s("verdict_ok",   fontSize=13, leading=18,
                          textColor=_WHITE, fontName=_FONT_B,
                          backColor=_GREEN, borderPadding=(6, 10, 6, 10)),
        "verdict_cond": s("verdict_cond", fontSize=13, leading=18,
                          textColor=_WHITE, fontName=_FONT_B,
                          backColor=_ORANGE, borderPadding=(6, 10, 6, 10)),
        "verdict_no":   s("verdict_no",   fontSize=13, leading=18,
                          textColor=_WHITE, fontName=_FONT_B,
                          backColor=_RED, borderPadding=(6, 10, 6, 10)),
        "highlight":    s("highlight",    fontSize=9,  leading=14,
                          textColor=_BLACK, fontName=_FONT,
                          backColor=_REASON, borderPadding=(6, 8, 6, 8)),
        "risk_box":     s("risk_box",     fontSize=9,  leading=14,
                          textColor=_BLACK, fontName=_FONT,
                          backColor=_AMBER, borderPadding=(6, 8, 6, 8)),
        "link":         s("link",         fontSize=8,  leading=12,
                          textColor=colors.blue, fontName=_FONT),
    }


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _safe(val: Any, default: str = "—") -> str:
    if val is None:
        return default
    v = str(val).strip()
    return v if v else default


def _yn(val: Any) -> str:
    if val is True:  return "있음"
    if val is False: return "없음"
    return "-"


def _fmt_idr(idr_val: float | int | None) -> str:
    """IDR 숫자를 읽기 쉬운 형식으로."""
    if idr_val is None:
        return "—"
    try:
        return f"IDR {int(idr_val):,}"
    except Exception:
        return str(idr_val)


def _triple_currency(
    idr: float | int | None,
    usd_idr: float = 15750.0,
    idr_krw: float = 0.085,
) -> str:
    """IDR → IDR / USD / KRW 3중 표기 문자열 반환."""
    if idr is None:
        return "—"
    try:
        idr_f   = float(idr)
        usd_f   = idr_f / usd_idr
        krw_f   = idr_f * idr_krw
        return (
            f"IDR {int(idr_f):,}"
            f" / USD {usd_f:.2f}"
            f" / ₩{int(krw_f):,} KRW"
        )
    except Exception:
        return str(idr)


def _section_rule(elems: list, color: Any = _NAVY) -> None:
    elems.append(HRFlowable(width="100%", thickness=1.2, color=color, spaceAfter=3))


def _tbl_style(
    header_rows: int = 1,
    grid_color: Any = _MUTED,
    hdr_bg: Any = _NAVY,
) -> TableStyle:
    cmds = [
        ("BACKGROUND",    (0, 0), (-1, header_rows - 1), hdr_bg),
        ("TEXTCOLOR",     (0, 0), (-1, header_rows - 1), _WHITE),
        ("FONTNAME",      (0, 0), (-1, header_rows - 1), _FONT_B),
        ("FONTNAME",      (0, header_rows), (-1, -1), _FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, header_rows), (-1, -1), [_LIGHT, _WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.3, grid_color),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]
    return TableStyle(cmds)


# ══════════════════════════════════════════════════════════════════════════════
# 표지 (Cover)
# ══════════════════════════════════════════════════════════════════════════════

def _build_cover(meta: dict, styles: dict) -> list:
    company   = _safe(meta.get("company"),      "한국유나이티드제약(주)")
    prod_name = _safe(meta.get("product_name"), "제품명 미상")
    inn       = _safe(meta.get("inn"),          "")
    date_str  = _safe(meta.get("date"),         "")
    hs_code   = _safe(meta.get("hs_code"),      "")
    country   = _safe(meta.get("country"),      "Indonesia")

    elems: list = [Spacer(1, 40 * mm)]

    # 회사명
    elems.append(Paragraph(company, styles["cover_company"]))

    # 제품명 대제목
    elems.append(Paragraph(prod_name, styles["cover_title"]))

    # INN + 메타 바
    sub_parts = [inn] if inn and inn != "—" else []
    if hs_code and hs_code != "—":
        sub_parts.append(f"HS CODE: {hs_code}")
    sub_parts.append(country)
    if date_str and date_str != "—":
        sub_parts.append(date_str)
    elems.append(Paragraph("  |  ".join(sub_parts), styles["cover_inn"]))

    elems.append(Spacer(1, 6 * mm))
    _section_rule(elems)
    elems.append(Spacer(1, 4 * mm))

    elems.append(Paragraph(
        "본 보고서는 Claude AI 심층분석 및 BPOM/FORNAS/e-Katalog/BPJS-Kesehatan 데이터를 기반으로 "
        "자동 생성된 인도네시아 의약품 수출 전략 분석 결과입니다.",
        styles["body"],
    ))
    elems.append(Spacer(1, 6 * mm))

    # 섹션 목차 박스
    toc_data = [
        ["섹션", "내용"],
        ["P1", "시장조사 분석 — 판정 · 시장근거 · 규제 · 무역 · 가격"],
        ["P2", "수출 가격 전략 — 시나리오 · FOB 역산 · 공공·민간"],
        ["P3", "바이어 발굴 — 후보 목록 · 기업 상세 · 추천 이유"],
    ]
    toc_tbl = Table(toc_data, colWidths=[20 * mm, _CONTENT_W - 20 * mm])
    toc_tbl.setStyle(_tbl_style())
    elems.append(toc_tbl)

    elems.append(PageBreak())
    return elems


# ══════════════════════════════════════════════════════════════════════════════
# P1 — 시장조사 분석
# ══════════════════════════════════════════════════════════════════════════════

def _verdict_style(verdict: str, styles: dict) -> ParagraphStyle:
    m = {"적합": "verdict_ok", "조건부": "verdict_cond", "부적합": "verdict_no"}
    return styles.get(m.get(verdict, "verdict_cond"), styles["verdict_cond"])


def _build_p1(p1: dict, meta: dict, styles: dict) -> list:
    prod_name    = _safe(p1.get("product_name") or meta.get("product_name"), "")
    inn          = _safe(p1.get("inn") or meta.get("inn"), "")
    verdict      = _safe(p1.get("verdict"), "미분석")
    verdict_lbl  = _safe(p1.get("verdict_label"), verdict)
    hs_code      = _safe(p1.get("hs_code") or meta.get("hs_code"), "")
    date_str     = _safe(meta.get("date"), "")

    elems: list = []

    # ── 섹션 헤더 ──────────────────────────────────────────────────────────
    elems.append(Paragraph("P1  시장조사 분석", styles["h1"]))
    _section_rule(elems)
    sub_parts = [inn]
    if hs_code and hs_code != "—":
        sub_parts.append(f"HS CODE: {hs_code}")
    sub_parts += ["Indonesia", date_str]
    elems.append(Paragraph("  |  ".join(p for p in sub_parts if p and p != "—"), styles["small"]))
    elems.append(Spacer(1, 4 * mm))

    # ── 1. 판정 ────────────────────────────────────────────────────────────
    elems.append(Paragraph("① 수출 적합성 판정", styles["h2"]))
    vstyle = _verdict_style(verdict, styles)
    elems.append(Paragraph(f"  {verdict_lbl}  ", vstyle))
    elems.append(Spacer(1, 2 * mm))

    summary = _safe(p1.get("summary") or p1.get("rationale"), "")
    if summary and summary != "—":
        elems.append(Paragraph(summary, styles["highlight"]))
    elems.append(Spacer(1, 3 * mm))

    # ── 2. 국가·시장 개요 ──────────────────────────────────────────────────
    elems.append(Paragraph("② 인도네시아 시장 개요", styles["h2"]))
    macro_rows = []
    pairs = [
        ("인구",           p1.get("population")),
        ("1인당 GDP",      p1.get("gdp_per_capita")),
        ("의약품 시장",    p1.get("pharma_market")),
        ("보건 지출",      p1.get("health_spend")),
        ("수입 의존도",    p1.get("import_dep")),
        ("질환 유병률",    p1.get("disease_prevalence")),
        ("관련 시장",      p1.get("related_market")),
    ]
    row: list = []
    for label, val in pairs:
        if val:
            row.append(Paragraph(label, styles["small"]))
            row.append(Paragraph(_safe(val), styles["body"]))
            if len(row) == 4:
                macro_rows.append(row)
                row = []
    if row:
        while len(row) < 4:
            row.append(Paragraph("", styles["body"]))
        macro_rows.append(row)

    if macro_rows:
        macro_tbl = Table(
            macro_rows,
            colWidths=[28 * mm, 51 * mm, 28 * mm, 51 * mm],
        )
        macro_tbl.setStyle(TableStyle([
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [_LIGHT, _WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.2, _MUTED),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(macro_tbl)
    elems.append(Spacer(1, 3 * mm))

    # ── 3. 시장·의학적 근거 ────────────────────────────────────────────────
    basis_market = _safe(p1.get("basis_market_medical"), "")
    if basis_market and basis_market != "—":
        elems.append(Paragraph("③ 시장·의학적 근거", styles["h2"]))
        elems.append(Paragraph(basis_market, styles["body"]))
        elems.append(Spacer(1, 2 * mm))

    # ── 4. 규제·BPOM ───────────────────────────────────────────────────────
    bpom_reg   = _safe(p1.get("bpom_reg") or p1.get("basis_regulatory"), "")
    entry_path = _safe(p1.get("entry_pathway"), "")
    if bpom_reg and bpom_reg != "—":
        elems.append(Paragraph("④ BPOM 등록 및 규제 절차", styles["h2"]))
        elems.append(Paragraph(bpom_reg, styles["body"]))
        elems.append(Spacer(1, 1 * mm))
    if entry_path and entry_path != "—":
        elems.append(Paragraph("▸ 진입 경로", styles["h3"]))
        for line in entry_path.split("\n"):
            line = line.strip()
            if line:
                elems.append(Paragraph(line, styles["body"]))
        elems.append(Spacer(1, 2 * mm))

    # ── 5. 무역·유통 ───────────────────────────────────────────────────────
    basis_trade = _safe(p1.get("basis_trade"), "")
    if basis_trade and basis_trade != "—":
        elems.append(Paragraph("⑤ 무역·유통 구조", styles["h2"]))
        elems.append(Paragraph(basis_trade, styles["body"]))
        elems.append(Spacer(1, 2 * mm))

    # ── 6. 참고 가격 ────────────────────────────────────────────────────────
    ref_price  = _safe(p1.get("ref_price_text"), "")
    price_pos  = _safe(p1.get("price_positioning_pbs"), "")
    eka_hint   = _safe(p1.get("ekatalog_price_hint"), "")
    if any(v and v != "—" for v in [ref_price, price_pos, eka_hint]):
        elems.append(Paragraph("⑥ 참고 가격 정보", styles["h2"]))
        for label, val in [
            ("FORNAS/e-Katalog 기준가", ref_price),
            ("포지셔닝 제안",           price_pos),
            ("e-Katalog 경쟁가 힌트",   eka_hint),
        ]:
            if val and val != "—":
                elems.append(Paragraph(f"▸ {label}: {val}", styles["body"]))
        elems.append(Spacer(1, 2 * mm))

    # ── 7. 리스크·조건 ──────────────────────────────────────────────────────
    risks = _safe(p1.get("risks_conditions"), "")
    if risks and risks != "—":
        elems.append(Paragraph("⑦ 리스크 및 조건", styles["h2"]))
        for line in risks.split("\n"):
            line = line.strip()
            if line:
                elems.append(Paragraph(line, styles["risk_box"]))
                elems.append(Spacer(1, 1 * mm))
        elems.append(Spacer(1, 2 * mm))

    # ── 8. 관련 논문 ────────────────────────────────────────────────────────
    papers = p1.get("papers", []) or []
    if papers:
        elems.append(Paragraph("⑧ 관련 논문 · 규제 문서", styles["h2"]))
        ref_rows = [["#", "제목", "출처", "근거"]]
        for i, p in enumerate(papers[:6], 1):
            title  = _safe(p.get("title"),      "")[:60]
            source = _safe(p.get("source"),     "")[:20]
            reason = _safe(p.get("summary_ko") or p.get("reason"), "")[:80]
            url    = p.get("url", "")
            title_cell = (
                Paragraph(f'<a href="{url}"><u>{title}</u></a>', styles["link"])
                if url
                else Paragraph(title, styles["small"])
            )
            ref_rows.append([
                Paragraph(str(i), styles["small"]),
                title_cell,
                Paragraph(source, styles["small"]),
                Paragraph(reason, styles["small"]),
            ])
        ref_tbl = Table(
            ref_rows,
            colWidths=[8 * mm, 62 * mm, 28 * mm, 61 * mm],
            repeatRows=1,
        )
        ref_tbl.setStyle(_tbl_style())
        elems.append(ref_tbl)
        elems.append(Spacer(1, 2 * mm))

    # ── 9. 출처 ────────────────────────────────────────────────────────────
    sources = p1.get("sources", []) or []
    if sources:
        elems.append(Paragraph("⑨ 데이터 출처", styles["h2"]))
        for src in sources[:8]:
            elems.append(Paragraph(f"• {_safe(src)}", styles["small"]))

    elems.append(PageBreak())
    return elems


# ══════════════════════════════════════════════════════════════════════════════
# P2 — 수출 가격 전략
# ══════════════════════════════════════════════════════════════════════════════

def _build_p2(p2: dict, meta: dict, styles: dict) -> list:
    """P2 섹션 빌드."""
    rates     = p2.get("exchange_rates", {}) or {}
    usd_idr   = float(rates.get("usd_idr", 15750) or 15750)
    idr_krw   = float(rates.get("idr_krw", 0.085) or 0.085)

    extracted = p2.get("extracted", {}) or {}
    analysis  = p2.get("analysis", {}) or {}
    scenarios = analysis.get("scenarios", []) or []

    prod_name = _safe(meta.get("product_name"), "")
    hs_code   = _safe(meta.get("hs_code"), "")
    date_str  = _safe(meta.get("date"), "")

    elems: list = []

    # ── 섹션 헤더 ──────────────────────────────────────────────────────────
    elems.append(Paragraph("P2  수출 가격 전략", styles["h1"]))
    _section_rule(elems)
    sub_parts = [_safe(extracted.get("dosage_form") or meta.get("inn"), "")]
    if hs_code and hs_code != "—":
        sub_parts.append(f"HS CODE: {hs_code}")
    sub_parts += ["Indonesia", date_str]
    elems.append(Paragraph("  |  ".join(p for p in sub_parts if p and p != "—"), styles["small"]))
    elems.append(Spacer(1, 4 * mm))

    # ── 환율 정보 ──────────────────────────────────────────────────────────
    elems.append(Paragraph("① 적용 환율", styles["h2"]))
    rate_rows = [
        ["통화 쌍",    "환율",                       "비고"],
        ["USD / IDR", f"1 USD = {usd_idr:,.0f} IDR", "인도네시아 루피아"],
        ["IDR / KRW", f"1 IDR ≈ {idr_krw:.4f} KRW",  "원화 환산"],
    ]
    rate_tbl = Table(rate_rows, colWidths=[40 * mm, 60 * mm, _CONTENT_W - 100 * mm])
    rate_tbl.setStyle(_tbl_style())
    elems.append(rate_tbl)
    elems.append(Spacer(1, 4 * mm))

    # ── 가격 시나리오 ──────────────────────────────────────────────────────
    if scenarios:
        elems.append(Paragraph("② 가격 시나리오별 FOB 역산", styles["h2"]))

        scen_rows = [["시나리오", "현지 소비자가", "추정 FOB", "전략 요약"]]
        for sc in scenarios:
            price_idr = sc.get("price_idr")
            fob_idr   = sc.get("fob_result_idr")
            name      = _safe(sc.get("name"), "")
            reason    = _safe(sc.get("reason"), "")[:60]

            price_txt = _triple_currency(price_idr, usd_idr, idr_krw) if price_idr else "—"
            fob_txt   = _triple_currency(fob_idr,   usd_idr, idr_krw) if fob_idr   else "—"

            scen_rows.append([
                Paragraph(name,      styles["bold"]),
                Paragraph(price_txt, styles["body"]),
                Paragraph(fob_txt,   styles["body"]),
                Paragraph(reason,    styles["small"]),
            ])
        scen_tbl = Table(
            scen_rows,
            colWidths=[22 * mm, 48 * mm, 48 * mm, _CONTENT_W - 118 * mm],
            repeatRows=1,
        )
        scen_tbl.setStyle(_tbl_style())
        elems.append(scen_tbl)
        elems.append(Spacer(1, 4 * mm))

        # 시나리오별 FOB 차감 상세
        for sc in scenarios:
            name    = _safe(sc.get("name"), "")
            factors = sc.get("fob_factors", []) or []
            if not factors:
                continue
            elems.append(Paragraph(f"▸ {name} 시나리오 — FOB 차감 구조", styles["h3"]))

            price_idr = sc.get("price_idr")
            fob_idr   = sc.get("fob_result_idr")
            factor_rows = [["항목", "차감율", "근거"]]
            for f in factors:
                factor_rows.append([
                    _safe(f.get("name"), ""),
                    f"{_safe(f.get('value', ''), '—')}%",
                    _safe(f.get("rationale"), ""),
                ])
            # 합계 행
            factor_rows.append([
                f"소비자가 → FOB 추정",
                f"{_triple_currency(price_idr, usd_idr, idr_krw)} → {_triple_currency(fob_idr, usd_idr, idr_krw)}",
                "차감 후 추정 FOB",
            ])
            factor_tbl = Table(
                factor_rows,
                colWidths=[40 * mm, 50 * mm, _CONTENT_W - 90 * mm],
                repeatRows=1,
            )
            factor_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
                ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
                ("FONTNAME",      (0, 0), (-1, 0), _FONT_B),
                ("FONTNAME",      (0, 1), (-1, -2), _FONT),
                ("FONTNAME",      (0, -1), (-1, -1), _FONT_B),
                ("BACKGROUND",    (0, -1), (-1, -1), colors.Color(230/255,230/255,240/255)),
                ("FONTSIZE",      (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS",(0, 1), (-1, -2), [_LIGHT, _WHITE]),
                ("GRID",          (0, 0), (-1, -1), 0.3, _MUTED),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING",   (0, 0), (-1, -1), 5),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ]))
            elems.append(factor_tbl)
            elems.append(Spacer(1, 3 * mm))

    # ── 권고 사항 ──────────────────────────────────────────────────────────
    recommendation = _safe(analysis.get("recommendation"), "")
    if recommendation and recommendation != "—":
        elems.append(Paragraph("③ 종합 권고", styles["h2"]))
        elems.append(Paragraph(recommendation, styles["highlight"]))
        elems.append(Spacer(1, 2 * mm))

    # ── 공공·민간 전략 ──────────────────────────────────────────────────────
    pub_strat  = _safe(analysis.get("public_market_strategy"),  "")
    priv_strat = _safe(analysis.get("private_market_strategy"), "")
    if pub_strat != "—" or priv_strat != "—":
        elems.append(Paragraph("④ 채널별 진출 전략", styles["h2"]))
        strat_rows = [["채널", "전략 요약"]]
        if pub_strat and pub_strat != "—":
            strat_rows.append(["공공 채널 (BPJS·e-Katalog)", pub_strat])
        if priv_strat and priv_strat != "—":
            strat_rows.append(["민간 채널 (약국·병원)", priv_strat])
        strat_tbl = Table(
            strat_rows,
            colWidths=[45 * mm, _CONTENT_W - 45 * mm],
        )
        strat_tbl.setStyle(_tbl_style())
        elems.append(strat_tbl)

    elems.append(PageBreak())
    return elems


# ══════════════════════════════════════════════════════════════════════════════
# P3 — 바이어 발굴
# ══════════════════════════════════════════════════════════════════════════════

def _build_p3_summary(buyers: list[dict], styles: dict) -> list:
    """P3 섹션 1 — 바이어 후보 전체 목록."""
    elems: list = []
    elems.append(Paragraph(f"P3  바이어 발굴  — 후보 목록 ({len(buyers)}개사)", styles["h1"]))
    _section_rule(elems)

    hdr = ["#", "기업명", "국가", "카테고리", "이메일", "웹사이트"]
    rows = [hdr]
    for i, c in enumerate(buyers, 1):
        rows.append([
            str(i),
            (_safe(c.get("company_name"), ""))[:30],
            (_safe(c.get("country"),      ""))[:12],
            (_safe(c.get("category"),     ""))[:22],
            (_safe(c.get("email"),        ""))[:30],
            (_safe(c.get("website"),      ""))[:32],
        ])
    col_w = [8 * mm, 42 * mm, 16 * mm, 30 * mm, 37 * mm, _CONTENT_W - 133 * mm]
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(_tbl_style())
    elems.append(tbl)
    elems.append(PageBreak())
    return elems


def _build_p3_detail(buyers: list[dict], styles: dict) -> list:
    """P3 섹션 2 — 상위 N개사 상세."""
    detail_count = min(len(buyers), 3)
    elems: list = []

    elems.append(Paragraph(
        f"P3  우선 접촉 바이어 상세  (상위 {detail_count}개사)",
        styles["h1"],
    ))
    _section_rule(elems)
    elems.append(Spacer(1, 4 * mm))

    for idx, c in enumerate(buyers[:detail_count], 1):
        name    = _safe(c.get("company_name"), "")
        country = _safe(c.get("country"),      "")
        cat     = _safe(c.get("category"),     "")
        e       = c.get("enriched", {}) or {}

        # 헤더 행 (이름 + 카테고리/국가)
        hdr_data = [[
            Paragraph(
                f"{idx}.  {name}",
                ParagraphStyle("_hdr", fontSize=13, textColor=_NAVY,
                               fontName=_FONT_B, leading=17),
            ),
            Paragraph(
                f"{country}  ·  {cat}",
                ParagraphStyle("_hdr_r", fontSize=9, textColor=_MUTED,
                               fontName=_FONT, leading=12),
            ),
        ]]
        hdr_tbl = Table(hdr_data, colWidths=[110 * mm, _CONTENT_W - 110 * mm])
        hdr_tbl.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
            ("LINEBELOW",     (0, 0), (-1, 0), 1.5, _NAVY),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ]))
        elems += [hdr_tbl, Spacer(1, 3 * mm)]

        # 기업 개요
        overview = _safe(e.get("company_overview_kr"), "")
        if overview and overview != "—":
            elems.append(Paragraph("▸ 기업 개요", styles["h3"]))
            elems.append(Paragraph(overview, styles["body"]))
            elems.append(Spacer(1, 2 * mm))

        # 추천 이유 (강조 박스)
        reason = _safe(e.get("recommendation_reason"), "")
        if reason and reason != "—":
            elems.append(Paragraph("▸ 추천 이유", styles["h3"]))
            elems.append(Paragraph(reason, styles["highlight"]))
            elems.append(Spacer(1, 3 * mm))

        # 기본 정보 테이블
        elems.append(Paragraph("▸ 기본 정보", styles["h3"]))
        website_val = _safe(c.get("website"), "")
        ws_cell = (
            Paragraph(f'<a href="{website_val}"><u>{website_val}</u></a>', styles["link"])
            if website_val and website_val != "—"
            else Paragraph("—", styles["body"])
        )
        info_rows = [
            [Paragraph("이메일",   styles["small"]), Paragraph(_safe(c.get("email"), ""), styles["body"]),
             Paragraph("설립",     styles["small"]), Paragraph(_safe(e.get("founded"), ""), styles["body"])],
            [Paragraph("웹사이트", styles["small"]), ws_cell,
             Paragraph("매출",     styles["small"]), Paragraph(_safe(e.get("revenue"), ""), styles["body"])],
            [Paragraph("임직원",   styles["small"]), Paragraph(_safe(e.get("employees"), ""), styles["body"]),
             Paragraph("사업지역", styles["small"]),
             Paragraph(", ".join(e.get("territories", []) or []) or "—", styles["body"])],
        ]
        info_tbl = Table(info_rows, colWidths=[22 * mm, 56 * mm, 22 * mm, 59 * mm])
        info_tbl.setStyle(TableStyle([
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [_LIGHT, _WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.2, _MUTED),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        elems += [info_tbl, Spacer(1, 3 * mm)]

        # 역량 테이블
        elems.append(Paragraph("▸ 역량 및 채널", styles["h3"]))
        cap_rows = [
            ["GMP 인증",       _yn(e.get("has_gmp")),
             "수입 이력",       _yn(e.get("import_history"))],
            ["공공 조달 이력",  _yn(e.get("procurement_history")),
             "공공 채널",       _yn(e.get("public_channel"))],
            ["민간 채널",       _yn(e.get("private_channel")),
             "약국 체인",       _yn(e.get("has_pharmacy_chain"))],
            ["MAH 대행 가능",   _yn(e.get("mah_capable")),
             "한국 거래 경험",  _safe(e.get("korea_experience"), "—")],
        ]
        cap_data = [
            [Paragraph(r[0], styles["small"]), Paragraph(r[1], styles["body"]),
             Paragraph(r[2], styles["small"]), Paragraph(r[3], styles["body"])]
            for r in cap_rows
        ]
        cap_tbl = Table(cap_data, colWidths=[30 * mm, 49 * mm, 30 * mm, 50 * mm])
        cap_tbl.setStyle(TableStyle([
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [_LIGHT, _WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.2, _MUTED),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        elems += [cap_tbl, Spacer(1, 3 * mm)]

        # 인증 목록
        certs = e.get("certifications", []) or []
        if certs:
            elems.append(Paragraph(
                "▸ 보유 인증: " + " · ".join(certs),
                styles["small"],
            ))
            elems.append(Spacer(1, 2 * mm))

        # 출처 URL
        src_urls = e.get("source_urls", []) or []
        if src_urls:
            elems.append(Paragraph("▸ 참조 출처", styles["h3"]))
            for url in src_urls[:4]:
                elems.append(Paragraph(
                    f'• <a href="{url}"><u>{url}</u></a>',
                    styles["link"],
                ))
            elems.append(Spacer(1, 1 * mm))

        elems.append(PageBreak())

    return elems


# ══════════════════════════════════════════════════════════════════════════════
# 공개 API: generate()
# ══════════════════════════════════════════════════════════════════════════════

def generate(
    data: dict[str, Any],
    output_path: str | Path,
    report_type: str = "final",
) -> Path:
    """인도네시아 PDF 보고서를 생성하고 출력 경로를 반환.

    Args:
        data        : gen_id_report.js 와 동일한 JSON 구조
                      keys: meta, p1, p2, p3
        output_path : 저장 경로 (.pdf)
        report_type : "p1" | "p2" | "p3" | "final"

    Returns:
        Path to the generated PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta = data.get("meta", {}) or {}
    p1   = data.get("p1")
    p2   = data.get("p2")
    p3   = data.get("p3")

    styles = _build_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=_MARGIN_L,
        rightMargin=_MARGIN_R,
        topMargin=_MARGIN_T,
        bottomMargin=_MARGIN_B,
        title=f"인도네시아 수출 분석 — {meta.get('product_name', '')}",
        author="한국유나이티드제약",
    )

    elems: list = []

    # 표지 (final 또는 단일 섹션 모두 포함)
    if report_type in ("final", "p1", "p2", "p3"):
        elems += _build_cover(meta, styles)

    # 섹션별 빌드
    if report_type in ("final", "p1") and p1:
        elems += _build_p1(p1, meta, styles)

    if report_type in ("final", "p2") and p2:
        elems += _build_p2(p2, meta, styles)

    if report_type in ("final", "p3") and p3:
        buyers = p3.get("buyers", []) or []
        if buyers:
            elems += _build_p3_summary(buyers, styles)
            elems += _build_p3_detail(buyers, styles)

    # 빈 문서 방지
    if not any(not isinstance(e, PageBreak) for e in elems):
        elems.append(Paragraph("데이터 없음 — 분석을 먼저 실행하세요.", styles["body"]))

    doc.build(elems)
    return output_path


# ── CLI (테스트용) ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json
    import argparse as _ap

    parser = _ap.ArgumentParser(description="인도네시아 PDF 보고서 생성기")
    parser.add_argument("json_path",   help="입력 JSON (test_docx_sample.json 등)")
    parser.add_argument("output_path", help="출력 PDF 경로")
    parser.add_argument("--type",      default="final",
                        choices=["p1", "p2", "p3", "final"],
                        help="보고서 유형 (기본: final)")
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        data = _json.load(f)

    out = generate(data, args.output_path, args.type)
    sys.stdout.buffer.write(f"PDF 생성 완료: {out}\n".encode("utf-8"))
