# TradeAX Copilot

글로벌 무역·수출 영업 전문가를 위한 AI 어시스턴트 대시보드입니다.

## 기술 스택

- **Next.js 14** (App Router), **React**, **TypeScript**, **Tailwind CSS**
- **lucide-react** (아이콘), **papaparse** / **xlsx** (CSV·Excel 파싱), **react-markdown** (AI 결과 렌더링)

## 실행 방법

```bash
npm install
npm run dev
```

브라우저에서 [http://localhost:3000](http://localhost:3000) 접속.

## 5가지 핵심 기능

| 메뉴 | 설명 |
|------|------|
| 바이어 이메일 생성기 | CSV/Excel 바이어 목록 업로드 → 바이어별 맞춤 B2B 영업 이메일 생성 |
| 영업 실적 분석기 | 월별 수출 실적 CSV/Excel → MoM 성장 Top 3, 국가별 트렌드, H2 권장 시장 분석 |
| 다국어 스펙 현지화 | 한국어 제품 스펙 + 대상 언어(영/중/스페인어) → B2B 톤 현지화 문구 생성 |
| 경쟁사 가격 매트릭스 | 우리 vs 경쟁사 가격(CSV/텍스트) → 포지셔닝, 차별화 포인트, 협상 논거 3가지 |
| 전시회 실행 보고서 | 전시회명·기간·상담 수·주요 바이어·예상 매출 등 → 경영진용 2페이지 한글 요약 보고서 |

## 데이터 형식 (CSV/Excel)

- **바이어 목록**: 바이어명(Buyer Name), 국가(Country), 제품정보(Product) 등 한·영 컬럼 지원
- **영업 실적**: 월(Month), 국가(Country), 금액/매출(Amount, Revenue) 등
- **가격 매트릭스**: 제품명, 우리가격(Our Price), 경쟁사A/B/C 등

실제 컬럼명이 다르면 `src/lib/csvParser.ts`의 `*_HEADER_MAP`에서 매핑을 추가하면 됩니다.

## OpenAI API 연동

- **서버**: `POST /api/analyze` 라우트에서만 `OPENAI_API_KEY`를 사용해 OpenAI를 호출합니다. API 키는 클라이언트에 노출되지 않습니다.
- **설정**: 프로젝트 루트에 `.env.local`을 만들고 `OPENAI_API_KEY=sk-...` 를 설정하세요. 참고용으로 `.env.example`이 있습니다.
- **모델**: `gpt-4o-mini` (속도·비용 고려). 5개 작업별 시스템 프롬프트가 API 라우트에 정의되어 있습니다.

## 프로젝트 구조

```
src/
  app/              # 페이지 (/, /sales-analyzer, /spec-localizer, /price-matrix, /exhibition-report)
  components/
    layout/         # DashboardLayout, Sidebar
    output/         # OutputZone (ReactMarkdown, 복사, 내보내기)
    tools/          # 5개 도구별 Input 컴포넌트 + ToolSection
  lib/              # csvParser, mockAi
  types/            # BuyerRow, SalesRow, PriceRow, ExhibitionFormData 등
```

변경 이력은 루트의 `CHANGELOG.md`에 기록합니다.
