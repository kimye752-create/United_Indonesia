/**
 * 인도네시아 진출 전략 보고서 생성기
 * SG 템플릿 기반 · 맑은 고딕 · A4
 *
 * 사용법:
 *   node gen_id_report.js <data.json> <output.docx> [--type final|p1|p2|p3]
 *
 * data.json 구조:
 *   { meta, p1, p2, p3 }
 */

'use strict';
const fs   = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber, PageBreak, Header, Footer,
  LevelFormat, UnderlineType,
} = require('docx');

// ── 상수 ──────────────────────────────────────────────────────────────────────
const F      = '맑은 고딕';   // 기본 폰트
const NAVY   = '173F78';
const NAVY2  = '1B3A6B';
const ORANGE = 'E07120';
const GREEN  = '1A7A3C';
const MUTED  = '6B7280';
const LIGHT  = 'F4F6FA';
const WHITE  = 'FFFFFF';
const BORDER = 'D0D7E3';
const DARK   = '1A1A1A';

// A4, 마진 1134 DXA (0.79인치)
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1134;
const CONTENT_W = PAGE_W - MARGIN * 2; // 9638

const TODAY = new Date().toISOString().slice(0, 10);

// ── 헬퍼 ──────────────────────────────────────────────────────────────────────
function safe(v, fallback = '—') {
  if (v === null || v === undefined || v === '' || v === '-') return fallback;
  return String(v);
}
function fmt_idr(n) {
  if (!n || isNaN(Number(n))) return '—';
  return 'IDR ' + Math.round(Number(n)).toLocaleString('ko-KR');
}
function fmt_usd(idr, usd_idr) {
  if (!idr || !usd_idr || usd_idr <= 0) return '—';
  return '$' + (Number(idr) / Number(usd_idr)).toFixed(2) + ' USD';
}

function run(text, opts = {}) {
  return new TextRun({
    text: safe(text, ''),
    font: opts.font || F,
    size: opts.size || 22,       // 11pt default
    bold: opts.bold || false,
    color: opts.color || DARK,
    italics: opts.italics || false,
  });
}

function p(children, opts = {}) {
  const runs = Array.isArray(children)
    ? children
    : [typeof children === 'string' ? run(children, opts) : children];
  return new Paragraph({
    children: runs,
    alignment: opts.align || AlignmentType.LEFT,
    spacing: {
      before: opts.before != null ? opts.before : 60,
      after:  opts.after  != null ? opts.after  : 60,
      line:   opts.line   || 360,
    },
    indent: opts.indent ? { left: opts.indent } : undefined,
    pageBreakBefore: opts.pageBreak || false,
    border: opts.border || undefined,
  });
}

function h1(text, opts = {}) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, font: F, size: 28, bold: true, color: NAVY })],
    spacing: { before: 240, after: 120 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 4 },
    },
    pageBreakBefore: opts.pageBreak || false,
  });
}

function h2(text, opts = {}) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: F, size: 24, bold: true, color: NAVY2 })],
    spacing: { before: 180, after: 80 },
    pageBreakBefore: opts.pageBreak || false,
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, font: F, size: 22, bold: true, color: NAVY2 })],
    spacing: { before: 120, after: 60 },
  });
}

function body(text, opts = {}) {
  return p([run(text, { size: 21, color: opts.color || DARK })], {
    before: 40, after: 40, line: 380, ...opts,
  });
}

function note(text) {
  return p([run(text, { size: 18, color: MUTED })], {
    before: 20, after: 20,
  });
}

function spacer(n = 1) {
  return Array.from({ length: n }, () => p('', { before: 0, after: 0, line: 200 }));
}

// ── 테이블 헬퍼 ────────────────────────────────────────────────────────────────
function borderSet(color = BORDER) {
  const b = { style: BorderStyle.SINGLE, size: 6, color };
  return { top: b, bottom: b, left: b, right: b };
}

function tc(text, opts = {}) {
  const isHdr = opts.header || false;
  const children = typeof text === 'string'
    ? [p([run(text, {
        size: opts.size || (isHdr ? 19 : 20),
        bold: opts.bold != null ? opts.bold : isHdr,
        color: isHdr ? (opts.headerColor || NAVY) : (opts.color || DARK),
      })], { before: 60, after: 60 })]
    : text;

  return new TableCell({
    width: opts.width ? { size: opts.width, type: WidthType.DXA } : undefined,
    borders: borderSet(opts.borderColor || BORDER),
    shading: opts.fill
      ? { fill: opts.fill, type: ShadingType.CLEAR }
      : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    columnSpan: opts.span || 1,
    children,
  });
}

function thc(text, opts = {}) {
  return tc(text, { header: true, fill: LIGHT, ...opts });
}

function tbl(rows, colWidths, opts = {}) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: colWidths,
    rows,
  });
}

function tr(cells, opts = {}) {
  return new TableRow({
    tableHeader: opts.header || false,
    cantSplit: true,
    children: cells,
  });
}

// ── 표지 생성 ─────────────────────────────────────────────────────────────────
function buildCover(meta) {
  const country  = safe(meta.country, '인도네시아');
  const company  = safe(meta.company, '한국유나이티드제약');
  const date     = safe(meta.date, TODAY);
  const subtitle = safe(meta.subtitle, '수출가격 전략  ·  바이어 후보 리스트  ·  시장분석');

  return [
    ...spacer(8),
    new Paragraph({
      children: [new TextRun({ text: `${country} 진출 전략 보고서`, font: F, size: 52, bold: true, color: NAVY })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 240 },
    }),
    new Paragraph({
      children: [new TextRun({ text: company, font: F, size: 28, color: MUTED })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 120 },
    }),
    new Paragraph({
      children: [new TextRun({ text: date, font: F, size: 22, color: MUTED })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 240 },
    }),
    new Paragraph({
      children: [new TextRun({ text: subtitle, font: F, size: 22, color: NAVY, bold: true })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 0 },
      border: {
        top:    { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 8 },
        bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 8 },
      },
    }),
  ];
}

// ── P2 수출가격 전략 보고서 ───────────────────────────────────────────────────
function buildP2(p2, meta) {
  if (!p2) return [p('P2 데이터 없음', { color: MUTED })];

  const extracted  = p2.extracted  || {};
  const analysis   = p2.analysis   || {};
  const rates      = p2.exchange_rates || {};
  const usd_idr    = Number(rates.usd_idr) || 16200;
  const idr_krw    = Number(rates.idr_krw) || 0.0864;
  const product    = safe(extracted.product_name, safe(meta.product_name, '미상'));
  const inn        = safe(meta.inn, '');
  const date       = safe(meta.date, TODAY);

  const elems = [];

  // 표제
  elems.push(h1(`인도네시아 수출 가격 전략 보고서 — ${product}`, { pageBreak: true }));
  elems.push(p([
    run(`${product}${inn ? ' (' + inn + ')' : ''}  |  ${date}`, { size: 20, color: MUTED }),
  ], { before: 0, after: 180 }));

  // 1. 거시 시장 요약
  elems.push(h2('1. 인도네시아 거시 시장'));
  const marketCtx = safe(extracted.market_context, analysis.rationale || '');
  if (marketCtx && marketCtx !== '—') {
    elems.push(body(marketCtx));
  } else {
    elems.push(body('인도네시아는 인구 2억 8천만 명의 동남아시아 최대 의약품 시장으로, ' +
      `연간 의약품 시장 규모 USD 87억(2024E)에 달합니다. ` +
      'BPOM 등록 및 BPJS-Kesehatan 급여 등재를 통한 공공·민간 채널 진출이 핵심입니다.'));
  }

  // 2. 단가 (시장 기준가)
  elems.push(h2('2. 단가 (시장 기준가)'));
  const refIdr = Number(extracted.ref_price_sgd) || 0;
  const refUsd = refIdr > 0 && usd_idr > 0 ? (refIdr / usd_idr).toFixed(2) : '—';
  const refKrw = refIdr > 0 && idr_krw > 0 ? Math.round(refIdr * idr_krw).toLocaleString('ko-KR') : '—';

  elems.push(tbl([
    tr([thc('기준 가격', { width: 2200 }),
        tc(safe(extracted.ref_price_text,
          refIdr > 0 ? `IDR ${refIdr.toLocaleString('ko-KR')} / $${refUsd} USD / ₩${refKrw} KRW` : '보고서에서 추출 중'), { width: 7438 })]),
    tr([thc('산정 방식', { width: 2200 }),
        tc('AI 분석 (Claude) — 경쟁사 가격 및 인도네시아 시장 특성 반영', { width: 7438 })]),
    tr([thc('시장 구분', { width: 2200 }),
        tc('공공 시장 (e-Katalog / BPJS-Kesehatan) · 민간 시장 (병원·약국·체인)', { width: 7438 })]),
    tr([thc('환율 기준', { width: 2200 }),
        tc(`1 USD = IDR ${Math.round(usd_idr).toLocaleString('ko-KR')} / 1 IDR = ₩${idr_krw.toFixed(4)} (${safe(rates.source, '폴백값')})`, { width: 7438 })]),
  ], [2200, 7438]));

  // 3. 거래처 참고 가격
  elems.push(h2('3. 거래처 참고 가격'));
  const competitors = Array.isArray(extracted.competitor_prices) ? extracted.competitor_prices : [];
  if (competitors.length > 0) {
    const rows = [
      tr([thc('업체명', { width: 2000 }), thc('제품명 / 성분', { width: 4000 }),
          thc('시장가', { width: 2000 }), thc('출처', { width: 1638 })], { header: true }),
    ];
    for (const c of competitors) {
      const priceIdr = Number(c.price_sgd || c.price_idr) || 0;
      rows.push(tr([
        tc(safe(c.name, c.company || '—'), { width: 2000 }),
        tc(safe(c.product || c.inn, '—'), { width: 4000 }),
        tc(priceIdr > 0 ? `IDR ${priceIdr.toLocaleString('ko-KR')}` : safe(c.price_text, '—'), { width: 2000 }),
        tc(safe(c.source, 'Perplexity'), { width: 1638, size: 18 }),
      ]));
    }
    elems.push(tbl(rows, [2000, 4000, 2000, 1638]));
  } else {
    elems.push(note('경쟁사 참고가 데이터가 없습니다. 보고서 PDF에서 경쟁가를 추출합니다.'));
  }

  // 4. 가격 시나리오
  elems.push(h2('4. 가격 시나리오'));

  const COL_NAMES = { agg: '저가 진입', avg: '기준가', cons: '프리미엄' };
  const COL_COLORS = { agg: ORANGE, avg: NAVY, cons: GREEN };

  function buildMarketSection(mktData, mktLabel) {
    if (!mktData || !Array.isArray(mktData.scenarios)) return [];
    const elems2 = [];
    elems2.push(h3(mktLabel));
    if (mktData.market_note) {
      elems2.push(note('데이터 소스: ' + mktData.market_note));
    }
    const scenarios = mktData.scenarios;
    for (let i = 0; i < scenarios.length; i++) {
      const sc = scenarios[i];
      const name  = safe(sc.name, Object.values(COL_NAMES)[i] || `시나리오 ${i+1}`);
      const color = Object.values(COL_COLORS)[i] || NAVY;
      const priceIdr = Number(sc.price_idr) || 0;
      const fobIdr   = Number(sc.fob_result_idr) || 0;
      const priceUsd = usd_idr > 0 && priceIdr > 0 ? '$' + (priceIdr / usd_idr).toFixed(2) + ' USD' : '—';
      const fobUsd   = usd_idr > 0 && fobIdr > 0   ? '$' + (fobIdr   / usd_idr).toFixed(2) + ' USD' : '—';

      // 시나리오 제목 + 가격
      elems2.push(new Paragraph({
        children: [
          new TextRun({ text: `[${name}]  `, font: F, size: 24, bold: true, color }),
          new TextRun({ text: `${fmt_idr(priceIdr)} / ${priceUsd}`, font: F, size: 22, bold: true, color: DARK }),
        ],
        spacing: { before: 120, after: 40 },
      }));

      // 근거
      if (sc.reason && sc.reason !== '—') {
        elems2.push(tbl([
          tr([thc('근거', { width: 1400, headerColor: color }), tc(sc.reason, { width: 8238 })]),
        ], [1400, 8238]));
      }

      // FOB 역산식
      const fobFactors = Array.isArray(sc.fob_factors) ? sc.fob_factors : [];
      if (fobFactors.length > 0) {
        // 역산식 텍스트 생성
        let formulaParts = [`IDR ${Math.round(priceIdr).toLocaleString('ko-KR')}`];
        let cur = priceIdr;
        for (const f of fobFactors) {
          const v = Number(f.value) || 0;
          if (f.type === 'pct_deduct') {
            formulaParts.push(`÷ (1 + ${f.name} ${v}%)`);
            cur /= (1 + v / 100);
          } else if (f.type === 'pct_add') {
            formulaParts.push(`× (1 + ${f.name} ${v}%)`);
            cur *= (1 + v / 100);
          } else if (f.type === 'abs_deduct') {
            formulaParts.push(`- ${f.name} IDR ${v.toLocaleString('ko-KR')}`);
            cur -= v;
          }
        }
        const fobCalc = Math.max(0, Math.round(fobIdr || cur));
        const fobCalcUsd = usd_idr > 0 ? '$' + (fobCalc / usd_idr).toFixed(2) + ' USD' : '—';
        const formula = formulaParts.join(' ') + ` ≈ IDR ${fobCalc.toLocaleString('ko-KR')} / ${fobCalcUsd}`;

        elems2.push(tbl([
          tr([thc('FOB 수출가 역산식', { width: 2400, headerColor: color }), tc(formula, { width: 7238, size: 19 })]),
        ], [2400, 7238]));
      } else if (fobIdr > 0) {
        elems2.push(tbl([
          tr([thc('FOB 수출가', { width: 2400, headerColor: color }),
              tc(`${fmt_idr(fobIdr)} / ${fobUsd}`, { width: 7238 })]),
        ], [2400, 7238]));
      }
      if (i < scenarios.length - 1) elems2.push(p('', { before: 0, after: 80 }));
    }
    return elems2;
  }

  if (analysis.public) {
    elems.push(...buildMarketSection(analysis.public, '▶ 4-1. 공공 시장  (e-Katalog · BPJS-Kesehatan)'));
    elems.push(p('', { before: 0, after: 120 }));
  }
  if (analysis.private) {
    elems.push(...buildMarketSection(analysis.private, '▶ 4-2. 민간 시장  (병원 · 약국 · 체인 채널)'));
  }

  // 5. 면책 문구
  elems.push(h2('5. 유의사항'));
  elems.push(note('※ 본 산출 결과는 AI 분석(Claude Haiku)에 기반한 추정치이므로, 최종 의사결정 전 반드시 담당자의 검토 및 확인이 필요합니다.'));
  elems.push(note('※ BPOM 등록 상태, FORNAS 등재 여부, 현지 파트너 계약 조건에 따라 실제 공급가격은 달라질 수 있습니다.'));
  elems.push(note(`※ 환율 기준: 1 USD = IDR ${Math.round(usd_idr).toLocaleString('ko-KR')} (보고서 생성 시점 기준)`));

  return elems;
}

// ── P3 바이어 후보 리스트 보고서 ──────────────────────────────────────────────
function buildP3(p3, meta) {
  if (!p3) return [p('P3 데이터 없음', { color: MUTED })];

  const buyers   = Array.isArray(p3.buyers) ? p3.buyers : [];
  const product  = safe(meta.product_name, '미상');
  const inn      = safe(meta.inn, '');
  const date     = safe(meta.date, TODAY);
  const elems    = [];

  // 표제
  elems.push(h1(`인도네시아 바이어 후보 리스트 — ${product}`, { pageBreak: true }));
  elems.push(p([
    run(`${product}${inn ? ' (' + inn + ')' : ''}  |  ${date}`, { size: 20, color: MUTED }),
  ], { before: 0, after: 120 }));
  elems.push(note('※ 아래 바이어 후보는 CPHI 전시회 등록 및 Perplexity 웹 분석을 통해 도출되었으며, ' +
    '개별 기업의 인도네시아 진출 현황 및 제품 연관성은 추가 실사가 필요합니다.'));

  // 바이어 이름 헬퍼 (buyer_enricher가 name 또는 company_name 사용)
  function bName(b) { return safe(b.company_name || b.name); }
  function bEmail(b) { return safe(b.email); }
  function bWebsite(b) { return safe(b.website || b.homepage); }
  function bCountry(b) { return safe(b.country); }
  function bCategory(b) { return safe(b.category || b.type); }
  function bAddress(b) { return safe(b.address); }
  function bPhone(b) { return safe(b.phone || b.tel); }
  // enriched 데이터는 b 자체에 병합되어 있거나 b.enriched에 있을 수 있음
  function enriched(b) { return (b.enriched && typeof b.enriched === 'object') ? b.enriched : b; }
  function yn(v) {
    if (v === true)  return '있음 ✓';
    if (v === false) return '없음 ✗';
    return '-';
  }

  // 1. 후보 리스트 요약
  elems.push(h2('1. 인도네시아 현지 바이어 후보 리스트'));
  if (buyers.length === 0) {
    elems.push(note('바이어 발굴 결과가 없습니다.'));
  } else {
    const listRows = [
      tr([thc('순위', { width: 600 }), thc('기업명', { width: 3200 }),
          thc('국가', { width: 1200 }), thc('분류', { width: 1500 }), thc('이메일', { width: 3138 })], { header: true }),
    ];
    for (let i = 0; i < buyers.length; i++) {
      const b = buyers[i];
      listRows.push(tr([
        tc(String(i + 1),   { width: 600 }),
        tc(bName(b),        { width: 3200, bold: true }),
        tc(bCountry(b),     { width: 1200 }),
        tc(bCategory(b),    { width: 1500 }),
        tc(bEmail(b),       { width: 3138, size: 18 }),
      ]));
    }
    elems.push(tbl(listRows, [600, 3200, 1200, 1500, 3138]));
  }

  // 2. 우선 접촉 바이어 상세 정보
  elems.push(h2('2. 우선 접촉 바이어 상세 정보'));
  elems.push(note(
    '※ 아래 기업들은 CPHI 전시회 등록 데이터, Perplexity 실시간 검색, Claude AI 분석을 종합 평가하여 선정되었습니다. ' +
    '최종 파트너 선정 전 실사(Due Diligence)를 권장합니다.'
  ));

  for (let i = 0; i < Math.min(buyers.length, 10); i++) {
    const b  = buyers[i];
    const e  = enriched(b);
    const nm = bName(b);

    // 기업 헤더
    elems.push(new Paragraph({
      children: [new TextRun({ text: `${i + 1}. ${nm}`, font: F, size: 24, bold: true, color: NAVY }),
                 new TextRun({ text: `  |  ${bCategory(b)}  ${bCountry(b) ? '· ' + bCountry(b) : ''}`, font: F, size: 20, color: MUTED })],
      spacing: { before: i === 0 ? 180 : 400, after: 100 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: NAVY, space: 2 } },
    }));

    // 기업 개요
    const overview = safe(e.company_overview_kr || b.company_overview_kr, null);
    if (overview && overview !== '—') {
      elems.push(tbl([
        tr([thc('기업 개요', { width: 1400 }), tc(overview, { width: 8238 })]),
      ], [1400, 8238]));
    }

    // 추천 이유 (① ~ ⑤)
    const reason = safe(e.recommendation_reason || b.recommendation_reason, null);
    const certs       = (e.certifications || b.certifications || []).join(', ') || '—';
    const territories = (e.territories || b.territories || []).join(', ') || '—';
    const revenue     = safe(e.revenue || b.revenue, '—');
    const employees   = safe(e.employees || b.employees, '—');

    elems.push(tbl([
      tr([thc('추천 이유', { width: 1400 }), tc([
        p([run('① 매출 규모:  ', { bold: true, size: 20 }),
           run(`${revenue}  (직원 수: ${employees})`, { size: 20 })], { before: 40, after: 16 }),
        p([run('② 파이프라인:  ', { bold: true, size: 20 }),
           run(reason ? reason.slice(0, 250) : '제품 연관 파이프라인 정보 확인 필요', { size: 20 })], { before: 16, after: 16 }),
        p([run('③ 제조·인증:  ', { bold: true, size: 20 }),
           run(`GMP 인증: ${yn(e.has_gmp ?? b.has_gmp)} · 보유 인증: ${certs}`, { size: 20 })], { before: 16, after: 16 }),
        p([run('④ 수입 경험:  ', { bold: true, size: 20 }),
           run(`수입 이력: ${yn(e.import_history ?? b.import_history)} · 공공조달: ${yn(e.procurement_history ?? b.procurement_history)} · 한국 거래: ${safe(e.korea_experience || b.korea_experience, '—')}`, { size: 20 })], { before: 16, after: 16 }),
        p([run('⑤ 채널 적합성:  ', { bold: true, size: 20 }),
           run(`공공 채널: ${yn(e.public_channel ?? b.public_channel)} · 민간 채널: ${yn(e.private_channel ?? b.private_channel)} · MAH 대행: ${yn(e.mah_capable ?? b.mah_capable)} · 약국체인: ${yn(e.has_pharmacy_chain ?? b.has_pharmacy_chain)}`, { size: 20 })], { before: 16, after: 40 }),
      ], { width: 8238 })]),
    ], [1400, 8238]));

    // 기본 정보
    const infoRows = [];
    const addrVal = bAddress(b) || '—';
    const phoneVal = bPhone(b) || '—';
    const emailVal = bEmail(b) || '—';
    const siteVal  = bWebsite(b) || '—';
    const sizeStr  = [
      employees !== '—' ? `직원 ${employees}명` : null,
      revenue   !== '—' ? `연 매출 ${revenue}` : null,
      (e.founded || b.founded) ? `설립 ${e.founded || b.founded}년` : null,
    ].filter(Boolean).join(' · ') || '—';

    infoRows.push(tr([thc('주소', { width: 1400 }), tc(addrVal, { width: 4119 }), thc('전화', { width: 1400 }), tc(phoneVal, { width: 2719 })]));
    infoRows.push(tr([thc('이메일', { width: 1400 }), tc(emailVal, { width: 4119 }), thc('홈페이지', { width: 1400 }), tc(siteVal, { width: 2719, size: 17 })]));
    infoRows.push(tr([thc('기업 규모', { width: 1400 }), tc(sizeStr, { width: 4119 }), thc('영업 지역', { width: 1400 }), tc(territories, { width: 2719 })]));
    elems.push(tbl(infoRows, [1400, 4119, 1400, 2719]));

    // BPOM 등록 제품 (있을 경우)
    const regProds = e.registered_products || b.registered_products || [];
    if (regProds.length > 0) {
      elems.push(tbl([
        tr([thc('등록 제품', { width: 1400 }), tc(regProds.slice(0, 5).join(', '), { width: 8238 })]),
      ], [1400, 8238]));
    }

    // 출처
    const srcUrls = (e.source_urls || b.source_urls || []).slice(0, 3);
    elems.push(note(`※ 출처: CPHI 전시회 등록 DB, Perplexity 실시간 검색${srcUrls.length > 0 ? '  |  ' + srcUrls[0] : ''}`));
  }

  return elems;
}

// ── P1 시장보고서 ─────────────────────────────────────────────────────────────
function buildP1(p1, meta) {
  if (!p1) return [p('P1 데이터 없음', { color: MUTED })];

  const product = safe(meta.product_name || p1.product_name, '미상');
  const inn     = safe(meta.inn || p1.inn, '');
  const date    = safe(meta.date, TODAY);
  const verdict = safe(p1.verdict_label || p1.verdict, '');
  const elems   = [];

  // 표제
  elems.push(h1(`인도네시아 시장보고서 — ${product}`, { pageBreak: true }));
  elems.push(p([
    run(`${product}${inn ? ' (' + inn + ')' : ''}`, { size: 22, bold: true }),
    run(`  |  ${date}`, { size: 20, color: MUTED }),
    ...(verdict ? [run(`  |  판정: ${verdict}`, { size: 20, bold: true, color: verdict.includes('적합') && !verdict.includes('부') ? GREEN : verdict.includes('조건') ? ORANGE : NAVY })] : []),
  ], { before: 0, after: 180 }));

  // 수출 적합성 판정 요약
  const rationale = safe(p1.rationale, null);
  if (rationale && rationale !== '—') {
    elems.push(tbl([
      tr([thc('수출 적합성 판정', { width: 1800 }), tc(rationale, { width: 7838 })]),
    ], [1800, 7838]));
    elems.push(p('', { before: 0, after: 80 }));
  }

  // 1. 의료 거시환경
  elems.push(h2('1. 의료 거시환경 파악'));
  const macroRows = [
    ['인구',              safe(p1.population,    '2억 8,100만 명  (BPS Indonesia, 2024)')],
    ['1인당 GDP',         safe(p1.gdp_per_capita,'USD 4,941  (IMF, 2024)')],
    ['의약품 시장 규모',   safe(p1.pharma_market, 'USD 87억  (2024E, IQVIA / GlobalData)')],
    ['보건 지출',         safe(p1.health_spend,  'GDP 대비 약 3.2%  (WHO, 2023)')],
    ['의약품 수입 의존도', safe(p1.import_dep,    '약 90%  (원료의약품 기준, Kemenkes RI)')],
  ];
  // 제품별 추가 지표 (있을 경우에만)
  if (p1.disease_prevalence && p1.disease_prevalence !== '—')
    macroRows.push(['유병률 / 환자 수', p1.disease_prevalence]);
  if (p1.related_market && p1.related_market !== '—')
    macroRows.push(['관련 세부 시장', p1.related_market]);

  const macroTblRows = macroRows.map(([k, v]) =>
    tr([thc(k, { width: 2200 }), tc(v, { width: 7438 })])
  );
  elems.push(tbl(macroTblRows, [2200, 7438]));

  // 거시환경 분석 본문
  const marketMedical = safe(p1.basis_market_medical, null);
  if (marketMedical && marketMedical !== '—') {
    elems.push(body(marketMedical, { before: 120 }));
  } else {
    elems.push(body(
      '인도네시아는 동남아시아 최대 의약품 시장으로, BPJS-Kesehatan 가입자 2억 3,700만 명(전체 인구의 84%)을 바탕으로 ' +
      '공공 조달(e-Katalog/FORNAS)과 민간 채널(PBF 유통)이 병존하는 이원적 시장 구조를 가집니다. ' +
      '완제의약품의 원료 수입 의존도가 약 90%에 달해 한국 제약사의 직접 진출 기회가 큽니다.',
      { before: 120 }
    ));
  }

  // 2. 무역/규제 환경
  elems.push(h2('2. 무역 · 규제 환경'));

  // BPOM 등록 현황
  elems.push(h3('BPOM 등록 현황'));
  const bpomReg = safe(p1.bpom_reg, null);
  if (bpomReg && bpomReg !== '—') {
    elems.push(body(bpomReg));
  } else {
    elems.push(body(
      'BPOM(Badan Pengawas Obat dan Makanan, 인도네시아 식품의약품안전처)에 ML(수입) 코드로 허가 신청이 필요합니다. ' +
      '현지 MAH(Marketing Authorization Holder)를 선정하여 abridged NDA 또는 full NDA 경로를 통해 등록하며, ' +
      '심사 기간은 통상 12~24개월입니다. 등록 후 5년 주기로 갱신이 필요합니다.'
    ));
  }

  // 진입 채널 권고
  elems.push(h3('진입 채널 권고'));
  const entryPath = safe(p1.entry_pathway, null);
  if (entryPath && entryPath !== '—') {
    // 단계별 진입 경로 — 줄바꿈 기준으로 분리하여 각 단계를 별도 단락으로
    const steps = entryPath.split(/\n|→|·/).filter(s => s.trim());
    if (steps.length > 1) {
      for (const step of steps) {
        const t = step.trim();
        if (t) elems.push(body(t.startsWith('1단계') || t.startsWith('2단계') || t.startsWith('3단계') ? t : '▸ ' + t, { before: 40, after: 30 }));
      }
    } else {
      elems.push(body(entryPath));
    }
  } else {
    elems.push(body('▸ 1단계(0~12개월): 현지 MAH 계약 및 BPOM ML 허가 신청. DJKI 특허 검색 첨부.'));
    elems.push(body('▸ 2단계(12~24개월): BPOM 허가 취득 후 FORNAS(국가처방집) 등재 신청 및 BPJS-Kesehatan 급여 심사.'));
    elems.push(body('▸ 3단계(24개월~): e-Katalog(LKPP) 등록 → 공공병원 입찰 참여 / 민간 채널: PBF 유통사·Halodoc·K24Klik 입점.'));
  }

  // 관세 및 무역
  elems.push(h3('관세 및 무역'));
  const tradeBasis = safe(p1.basis_trade, null);
  if (tradeBasis && tradeBasis !== '—') {
    elems.push(body(tradeBasis));
  } else {
    elems.push(tbl([
      tr([thc('수입관세(Bea Masuk)', { width: 2400 }), tc('완제의약품 HS 3004: 0~5% (ASEAN FTA 적용 시 0%). 일반세율 5%.', { width: 7238 })]),
      tr([thc('PPN 부가가치세',      { width: 2400 }), tc('11% (2022년 개정). 의약품 중 일부 면세 대상 별도 확인 필요.', { width: 7238 })]),
      tr([thc('TKDN 현지화',        { width: 2400 }), tc('공공조달 제품에 TKDN(현지화 비중) 요건 적용. ML(수입) 제품은 공공 조달 가점 불리.', { width: 7238 })]),
      tr([thc('PBF 유통',           { width: 2400 }), tc('PBF(Pedagang Besar Farmasi) 경유 의무. 유통 마진 공공 15~22%, 민간 20~35%.', { width: 7238 })]),
    ], [2400, 7238]));
  }

  // 3. 참고 가격
  elems.push(h2('3. 참고 가격'));
  const pricePos = safe(p1.price_positioning_pbs, null);
  const refText2 = safe(p1.ref_price_text, null);
  const ekaHint  = safe(p1.ekatalog_price_hint, null);

  if (pricePos && pricePos !== '—') {
    elems.push(body(pricePos));
  } else if (refText2 && refText2 !== '—') {
    elems.push(body(refText2));
  }
  if (ekaHint && ekaHint !== '—') {
    elems.push(tbl([
      tr([thc('e-Katalog 조달가 추정', { width: 2400 }), tc(ekaHint, { width: 7238 })]),
    ], [2400, 7238]));
  }
  if (!pricePos && !refText2 && !ekaHint) {
    elems.push(note('※ 참고 가격은 2공정(가격전략) 분석 보고서를 참고하십시오.'));
  }

  // 4. 리스크 / 조건
  elems.push(h2('4. 리스크 · 조건'));
  const risks = safe(p1.risks_conditions, null);
  if (risks && risks !== '—') {
    const parts = risks.split(/\n/).filter(s => s.trim());
    for (const part of parts) {
      const t = part.trim();
      if (!t) continue;
      // ▸ 로 시작하지 않으면 추가
      elems.push(body(t.startsWith('▸') ? t : '▸ ' + t, { before: 60, after: 40 }));
    }
  } else {
    elems.push(body('▸ 리스크: BPOM 심사 지연(12~24개월) / 대응: 신청 서류 사전 완비, 조기 MAH 확보'));
    elems.push(body('▸ 리스크: FORNAS 미등재 시 공공 채널 접근 제한 / 대응: 급여 등재 전 민간 채널(Halodoc·K24) 우선 진출'));
    elems.push(body('▸ 리스크: TKDN 현지화 요건 강화로 공공조달 경쟁 불리 / 대응: 현지 파트너와 CMO 위탁생산 검토'));
  }

  // 5. 근거 및 출처
  elems.push(h2('5. 근거 및 출처'));
  const papers = Array.isArray(p1.papers) ? p1.papers : [];
  if (papers.length > 0) {
    elems.push(h3('5-1. Perplexity 추천 논문 / 자료'));
    for (let j = 0; j < papers.length; j++) {
      const pp = papers[j];
      const ptitle = safe(pp.title || pp.name, `참고자료 ${j+1}`);
      elems.push(p([
        run(`No.${j + 1}  ${ptitle}`, { bold: true, size: 20 }),
      ], { before: 80, after: 20 }));
      const summary = pp.summary_ko || pp.summary || pp.abstract_ko || '';
      if (summary) elems.push(body(summary, { before: 0, after: 20 }));
      const url = pp.url || pp.link || '';
      if (url) elems.push(note('출처: ' + url));
    }
  }

  const sources = Array.isArray(p1.sources) ? p1.sources : [];
  if (sources.length > 0) {
    elems.push(h3('5-2. 사용된 DB / 기관'));
    for (const src of sources) {
      const name = safe(src.name || src);
      const desc = safe(src.description || src.desc, '');
      elems.push(p([
        run('•  ', { size: 20 }),
        run(name, { bold: true, size: 20 }),
        run(desc ? ' — ' + desc : '', { size: 20 }),
      ], { before: 20, after: 20 }));
    }
  }

  // 기본 출처 (데이터 없으면)
  if (papers.length === 0 && sources.length === 0) {
    const defaultSrcs = [
      'BPOM RI (Badan Pengawas Obat dan Makanan) — 의약품 등록 DB',
      'Kementerian Kesehatan RI (Kemenkes) — 보건부 정책·통계',
      'BPJS Kesehatan — 공공 의료보험 급여 정보',
      'LKPP / e-Katalog — 공공 조달 플랫폼',
      'Perplexity 실시간 규제·시장 정보 (2024~2026)',
    ];
    for (const s of defaultSrcs) {
      elems.push(p([run('•  ', { size: 20 }), run(s, { size: 20 })], { before: 20, after: 20 }));
    }
  }

  return elems;
}

// ── 헤더/푸터 ─────────────────────────────────────────────────────────────────
function makeHeaderFooter(title) {
  return {
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [
            new TextRun({ text: title, font: F, size: 18, color: MUTED }),
            new TextRun({ text: '\t한국유나이티드제약 해외사업팀', font: F, size: 18, color: MUTED }),
          ],
          tabStops: [{ type: 'right', position: 9638 }],
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BORDER, space: 4 } },
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          children: [
            new TextRun({ text: 'CONFIDENTIAL — 대외비  ', font: F, size: 16, color: MUTED }),
            new TextRun({ text: '\t', font: F, size: 16 }),
            new TextRun({ children: [PageNumber.CURRENT], font: F, size: 16, color: MUTED }),
            new TextRun({ text: ' / ', font: F, size: 16, color: MUTED }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: F, size: 16, color: MUTED }),
          ],
          tabStops: [{ type: 'right', position: 9638 }],
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: BORDER, space: 4 } },
        })],
      }),
    },
  };
}

// ── 문서 생성 ─────────────────────────────────────────────────────────────────
function buildDocument(data, reportType) {
  const meta    = data.meta    || {};
  const p1Data  = data.p1      || null;
  const p2Data  = data.p2      || null;
  const p3Data  = data.p3      || null;
  const country = safe(meta.country, '인도네시아');
  const product = safe(meta.product_name, '미상');

  const styles = {
    default: {
      document: { run: { font: F, size: 22 } },
    },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run:  { size: 28, bold: true, font: F, color: NAVY },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run:  { size: 24, bold: true, font: F, color: NAVY2 },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run:  { size: 22, bold: true, font: F },
        paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2 } },
    ],
  };

  const pageProps = {
    size:   { width: PAGE_W, height: PAGE_H },
    margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
  };

  const hf = makeHeaderFooter(`${country} 진출 전략 보고서 — ${product}`);

  // 보고서 타입별 섹션 구성
  let sections = [];

  if (reportType === 'p2') {
    sections = [{
      properties: { page: pageProps },
      ...hf,
      children: buildP2(p2Data, meta),
    }];
  } else if (reportType === 'p3') {
    sections = [{
      properties: { page: pageProps },
      ...hf,
      children: buildP3(p3Data, meta),
    }];
  } else if (reportType === 'p1') {
    sections = [{
      properties: { page: pageProps },
      ...hf,
      children: buildP1(p1Data, meta),
    }];
  } else {
    // final: 표지 + P2 + P3 + P1
    sections = [
      // 표지
      {
        properties: { page: pageProps },
        children: buildCover(meta),
      },
      // P2
      {
        properties: { page: pageProps },
        ...hf,
        children: buildP2(p2Data, meta),
      },
      // P3
      {
        properties: { page: pageProps },
        ...hf,
        children: buildP3(p3Data, meta),
      },
      // P1
      {
        properties: { page: pageProps },
        ...hf,
        children: buildP1(p1Data, meta),
      },
    ];
  }

  return new Document({ styles, sections });
}

// ── CLI 진입점 ────────────────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: node gen_id_report.js <data.json> <output.docx> [--type final|p1|p2|p3]');
    process.exit(1);
  }

  const dataPath   = args[0];
  const outputPath = args[1];
  const typeIdx    = args.indexOf('--type');
  const reportType = typeIdx >= 0 ? args[typeIdx + 1] : 'final';

  if (!fs.existsSync(dataPath)) {
    console.error(`데이터 파일을 찾을 수 없습니다: ${dataPath}`);
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
  const doc  = buildDocument(data, reportType);

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`✅ 생성 완료: ${outputPath} (${Math.round(buffer.length / 1024)}KB)`);
}

main().catch(err => {
  console.error('오류:', err.message);
  process.exit(1);
});
