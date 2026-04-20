/**
 * Mock AI 응답 - 나중에 OpenAI API로 교체 가능하도록 구조화
 */

const MOCK_DELAY_MS = 1200;

/** 공통 AI 호출 시그니처: (프롬프트/입력) => Promise<마크다운 문자열> */
export type AiGenerateFn = (input: unknown) => Promise<string>;

/** 더미 마크다운 응답 샘플 */
const DUMMY_BUYER_EMAIL = `## 바이어 맞춤 B2B 영업 이메일

| 바이어 | 국가 | 제품 | 상태 |
|--------|------|------|------|
| John Smith | USA | 전자부품 | 생성됨 |
| Maria Garcia | Spain | 산업기계 | 생성됨 |

---

### 샘플 이메일 (John Smith)

**Subject:** Premium Electronic Components for Your Production Line

Dear Mr. John Smith,

We understand that **USA** is a key market for electronic components. Our **전자부품** line is designed to meet the highest standards of reliability and performance.

We would be glad to arrange a short call at your convenience.

Best regards,  
TradeAX Sales Team
`;

const DUMMY_SALES_ANALYSIS = `## 영업 실적 분석 (MoM & 국가별)

### 1. 전월 대비 성장 Top 3
| 순위 | 항목 | 성장률 |
|------|------|--------|
| 1 | 제품 A - 미국 | +24% |
| 2 | 제품 B - 베트남 | +18% |
| 3 | 제품 C - 독일 | +12% |

### 2. 국가별 트렌드
- **미국**: 지속적 성장, H2 집중 타깃 권장
- **EU**: 규제 이슈 모니터링 필요
- **동남아**: 신규 시장으로 적극 공략 권장

### 3. H2 권장 타깃 시장
1. **북미** – 프리미엄 라인 확대
2. **베트남/인도네시아** – 가격 경쟁력 제품
3. **독일/폴란드** – B2B OEM 채널
`;

const DUMMY_LOCALIZED_SPEC = `## 현지화된 제품 스펙 (B2B 톤)

**Target language:** English (for regional buyers)

---

### Product Specifications (Localized)

| 항목 | 내용 |
|------|------|
| Product Name | [로컬라이즈된 명칭] |
| Key Features | Professional-grade components suitable for OEM and distribution channels. |
| Compliance | Meets international standards (CE, RoHS) for target markets. |

*This translation is adapted for B2B business communication, not literal.*
`;

const DUMMY_PRICE_MATRIX = `## 경쟁사 가격 포지셔닝 분석

### 가격 포지션
| 구분 | 우리 | 경쟁사 A | 경쟁사 B |
|------|------|----------|----------|
| 포지션 | **Mid-Premium** | Low | Premium |

### 차별화 포인트
1. **가격 대비 스펙** – 중간 가격대에서 최고 성능
2. **A/S 네트워크** – 현지 서비스로 프리미엄 대비 우위
3. **MOQ 유연성** – 소량 시험 주문 가능

### 협상 시 유리한 논거 3가지
1. **TCO(총소유비용)** – 장기 사용 시 우리 제품이 유리
2. **리드타임** – 재고 및 배송 일정 보장
3. **맞춤 옵션** – 최소 수량부터 커스텀 가능
`;

const DUMMY_EXHIBITION_REPORT = `## 전시회 실행 보고서 (경영진용 요약)

| 항목 | 내용 |
|------|------|
| **전시회명** | [입력된 전시회명] |
| **기간** | [입력된 기간] |
| **상담 건수** | [입력된 상담 수] |
| **주요 바이어** | [입력된 주요 바이어] |
| **예상 매출** | [입력된 예상 매출] |

---

### 1. 개요
본 전시회를 통해 [요약 내용]. 상담 건수 및 예상 매출 기준으로 [결론 요약].

### 2. 주요 성과
- 상담 품질 및 잠재 고객 풀 확대
- 후속 미팅 및 견적 요청 건수 확보

### 3. 권고 사항
- H2 타깃 시장 반영
- 후속 액션 플랜 수립 권고

---
*본 문서는 AI 기반 초안이며, 필요 시 수정·보완하여 사용하시기 바랍니다.*
`;

/** 툴별 Mock 응답 반환 (setTimeout 시뮬레이션) */
export async function mockAiBuyerEmail(): Promise<string> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS));
  return DUMMY_BUYER_EMAIL;
}

export async function mockAiSalesAnalyzer(): Promise<string> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS));
  return DUMMY_SALES_ANALYSIS;
}

export async function mockAiSpecLocalizer(): Promise<string> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS));
  return DUMMY_LOCALIZED_SPEC;
}

export async function mockAiPriceMatrix(): Promise<string> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS));
  return DUMMY_PRICE_MATRIX;
}

export async function mockAiExhibitionReport(): Promise<string> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS));
  return DUMMY_EXHIBITION_REPORT;
}
