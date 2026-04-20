# Vibe Coding Log / 변경 이력

## 2025-03-18

### TradeAX Copilot 초기 구축

- **프로젝트 생성**
  - Next.js 14 (App Router), TypeScript, Tailwind CSS 기반 프로젝트 구조 수동 생성
  - 의존성: `lucide-react`, `papaparse`, `xlsx`, `react-markdown` 추가

- **공통 레이아웃**
  - `src/app/layout.tsx`: 루트 레이아웃, Inter 폰트, `DashboardLayout` 적용
  - `src/components/layout/DashboardLayout.tsx`: 좌측 사이드바 + 메인 영역 구조
  - `src/components/layout/Sidebar.tsx`: 5개 핵심 기능 네비게이션 (바이어 이메일, 영업 실적 분석, 다국어 스펙 현지화, 경쟁사 가격 매트릭스, 전시회 실행 보고서)

- **타입 정의** (`src/types/index.ts`)
  - `BuyerRow`, `SalesRow`, `PriceRow`, `ExhibitionFormData`, `ToolId`, `NavItem` 정의
  - CSV/Excel 한·영 컬럼 매핑을 고려한 유연한 인터페이스

- **CSV/Excel 파싱** (`src/lib/csvParser.ts`)
  - `parseBuyerCsv`, `parseSalesCsv`, `parsePriceCsv` 및 Excel 변환 `xlsxToCsvString`, `parseBuyerExcel`, `parseSalesExcel`, `parsePriceExcel` 구현
  - 한글·영어 헤더 매핑 (바이어명/Buyer Name, 국가/Country, 월/Month 등)

- **Mock AI** (`src/lib/mockAi.ts`)
  - 툴별 더미 마크다운 응답 및 `setTimeout` 기반 지연 시뮬레이션
  - 추후 OpenAI API 연동 시 교체 가능하도록 함수 단위 구조

- **출력 영역** (`src/components/output/OutputZone.tsx`)
  - `ReactMarkdown`으로 AI 응답 렌더링
  - 클립보드 복사, Markdown 파일 내보내기, Word(.doc) 내보내기 버튼
  - 로딩 상태 표시

- **5개 도구 입력 컴포넌트**
  - `BuyerEmailInput`: CSV/Excel 업로드, 바이어 테이블 미리보기
  - `SalesAnalyzerInput`: 월별 실적 CSV/Excel 업로드
  - `SpecLocalizerInput`: 한국어 스펙 텍스트 + 대상 언어(영/중/스페인어) 선택
  - `PriceMatrixInput`: CSV/Excel 또는 텍스트 입력
  - `ExhibitionReportInput`: 전시회명, 기간, 상담 수, 주요 바이어, 예상 매출, 비고 폼

- **5개 페이지**
  - `/`: 바이어 이메일 생성기
  - `/sales-analyzer`: 영업 실적 분석기
  - `/spec-localizer`: 다국어 스펙 현지화
  - `/price-matrix`: 경쟁사 가격 매트릭스
  - `/exhibition-report`: 전시회 실행 보고서

- **UI/테마**
  - `tailwind.config.ts`: navy 계열 컬러 확장 (navy-50 ~ navy-950)
  - `globals.css`: 프로페셔널 대시보드용 배경·테두리, `.prose-output` 마크다운 스타일

- **기타**
  - `next-env.d.ts`, `postcss.config.mjs`, `tsconfig.json`, `package.json` 설정
  - 참조 데이터 파일(예제 CSV/Excel)은 워크스페이스에 1개 xlsx만 존재하여, 요구사항 및 일반적인 무역·영업 데이터 구조를 바탕으로 인터페이스 및 파서 설계

- **수정**
  - `src/lib/csvParser.ts`: `parseBuyerCsv` 반환 객체에서 `...r` 스프레드 순서 조정 (buyerName/country/productInfo 덮어쓰기 방지로 타입 오류 해결)

---

## 2025-03-18 (OpenAI API 연동)

- **백엔드: Next.js API 라우트**
  - `src/app/api/analyze/route.ts` 추가: POST 전용, 서버에서만 `OPENAI_API_KEY` 사용하여 OpenAI 호출
  - `openai` npm 패키지 사용, `gpt-4o-mini` 모델
  - 요청 본문: `taskType` (5가지) + `data` (작업별 페이로드)
  - `taskType`별 시스템 프롬프트 적용 (바이어 이메일, 영업 실적 분석, 스펙 현지화, 가격 매트릭스, 전시회 보고서)
  - API 키 미설정 시 503, 잘못된 본문 시 400, OpenAI 오류 시 502/503 반환

- **프론트엔드: API 연동**
  - `src/lib/analyzeApi.ts`: `callAnalyzeApi(taskType, data)` 클라이언트 함수, POST `/api/analyze` 호출 후 `content` 반환 또는 throw
  - 5개 페이지에서 Mock 제거 후 `callAnalyzeApi` 사용 (바이어/실적/스펙/가격/전시회)
  - 로딩 상태 유지, 성공 시 결과를 기존 Output Zone의 `<ReactMarkdown>`에 표시
  - 에러 처리: `outputError` 상태 + 결과 영역 상단 빨간 배너, 동시에 `window.alert`로 안내
  - `ToolSection`에 `outputError` optional prop 추가

- **기타**
  - `package.json`: `openai` 의존성 추가
  - `.env.example`: `OPENAI_API_KEY` 안내 추가
  - 스펙 현지화: API에서 `targetLanguage` 코드(en/zh/es)를 English/Chinese/Spanish로 변환해 사용자 메시지에 포함

---

## 2025-03-18 (바이어 이메일 생성기 Output Zone 개편)

- **토큰/UX 개선**
  - 전체 CSV를 한 번에 API로 보내지 않고, **행 단위 온디맨드 생성**으로 변경 (500건도 토큰 한도 영향 최소화)
  - 결과를 긴 텍스트 블록이 아닌 **데이터 테이블 + 페이지네이션**으로 표시

- **타입**
  - `src/types/index.ts`: `BuyerEmailStatus`, `BuyerEmailRow` 추가 (status, generatedContent, 기존 바이어 필드)

- **입력 플로우**
  - `BuyerEmailInput`: 버튼 문구를 "목록 불러오기 (테이블에 적용)"으로 변경, `onLoadList(rows)`로 CSV 파싱 결과만 부모에 전달 (API 호출 없음)

- **테이블**
  - `src/components/tools/BuyerEmailTable.tsx`: 컬럼 (바이어/회사, 이메일, 상태, 작업), 행당 [Generate] [상세보기] [전송], 페이지네이션 (10행/페이지, < 1 2 … >)
  - 상태: Pending / Generated 뱃지 표시

- **상세 모달**
  - `src/components/tools/EmailDetailModal.tsx`: 상세보기 클릭 시 오버레이 모달, AI 생성 마크다운을 `<ReactMarkdown>`으로 표시, "소스 편집"으로 텍스트 편집 후 저장 가능 (전송 시 반영)

- **전송**
  - 행의 [전송] 클릭 시 `mailto:` 링크 생성 (수신 이메일, 제목, 본문)하여 기본 메일 클라이언트 실행 (이메일 주소는 CSV 컬럼에 있을 때만 사용)

- **페이지**
  - `src/app/page.tsx`: 바이어 이메일 전용 레이아웃 (ToolSection 미사용). 입력(왼쪽) + 결과 테이블(오른쪽), 상세 모달 상태·생성 인덱스·에러 상태 관리. Generate/상세보기 시 해당 1행만 `callAnalyzeApi("buyer-email", [row])` 호출

---

## 2025-03-18 (영업 실적 분석기 설명·시스템 프롬프트 개선)

- **프론트엔드**
  - 영업 실적 분석기 페이지 설명 문구를 지정한 한국어 문장으로 통일: "월별 수출 실적 CSV/Excel을 업로드하면 다음 내용을 분석합니다: 1. 전월 대비 증감이 큰 품목 TOP 3 2. 국가별 성장/하락 트렌드 3. 하반기 집중해야 할 시장 (추천 이유 포함)"
  - `ToolSection`: 설명 문자열의 줄바꿈이 보이도록 `whitespace-pre-line` 적용

- **백엔드 (API)**
  - `src/app/api/analyze/route.ts`: sales-analyzer용 OpenAI 시스템 프롬프트 전면 교체. CRO/데이터 분석가 역할, **전체 응답 한국어·개조식 보고서** 강제, 고정 마크다운 구조(월별 수출 실적 분석 보고서, 전월 대비 증감 TOP 3 테이블, 국가별 성장/하락 트렌드, 하반기 집중 타깃 시장 및 추천 이유) 지정, 서두/맺음말 없이 구조화된 보고서만 출력하도록 명시

---

## 2025-03-18 (다국어 스펙 현지화 UI·API 전면 개편)

- **UI/UX (Papago 스타일)**
  - `src/components/tools/SpecLocalizerPanel.tsx` 신규: 좌우(모바일에서는 위아래) 대형 텍스트 영역 – 왼쪽 입력, 오른쪽 결과(ReactMarkdown). 상단 컨트롤 바: 원문 언어 드롭다운(기본값 "언어 감지 (Auto Detect)" + 전체 언어 목록), 스왑 버튼(ArrowLeftRight), 번역 언어 드롭다운, 번역 버튼.
  - 언어 목록: 한국어, 영어, 일본어, 중국어-간체/번체, 스페인어, 프랑스어, 독일어, 러시아어, 포르투갈어, 이탈리아어, 베트남어, 태국어, 인도네시아어, 아랍어. 스왑 시 소스·타깃 맞바꿈(소스가 Auto일 때는 타깃을 ko로 설정).
  - `src/app/spec-localizer/page.tsx`: ToolSection 제거, 단일 컬럼 레이아웃 + SpecLocalizerPanel만 사용. API 호출 시 `text`, `sourceLanguage`, `targetLanguage` 전달.

- **백엔드 (API)**
  - `src/app/api/analyze/route.ts`: spec-localizer 전용 동적 처리. 요청 본문에서 `sourceLanguage`, `targetLanguage`, `text` 수신. 시스템 프롬프트를 `buildSpecLocalizerSystemPrompt(sourceLabel, targetLabel)`로 생성하여 치환. 새 프롬프트: B2B 네이티브 번역·현지화·QA 편집자 역할, 직역 금지·B2B 톤 현지화·문법/어색한 표현/의도 손실 없음·제품 스펙 시 기술 용어 정확성 유지, 출력은 번역문만(서두 문구 없음). 사용자 메시지는 원문 텍스트만 전달.
  - `SPEC_LANGUAGE_LABELS`: 프론트엔드 언어 코드와 동기화된 표시명 맵 추가(Auto Detect, Korean, English, Japanese, Chinese-Simplified/Traditional 등).

---

## 2025-03-18 (영업 실적 분석기 보고서 시각 계층 강화)

- **백엔드 (API)**
  - `src/app/api/analyze/route.ts`: sales-analyzer 시스템 프롬프트를 시각·구조 중심으로 전면 수정. 시각 규칙(### 메인 헤더+이모지, 섹션 간 ---, #### 서브헤더에 📈📉🎯, 수치 **굵게**, Top 3 마크다운 테이블) 및 고정 마크다운 템플릿 적용. 보고서 제목·품목별 실적 변동(테이블+전문가 한줄평)·국가별 트렌드(성장/하락 구분)·하반기 전략 시장 추천 구조 유지. C-level 톤, 성장/하락 대비 명확화 지시.

---

## 2025-03-18 (대시보드 탭 상태 유지 및 Home 버튼)

- **상태 상향 + Keep-Alive**
  - `src/context/DashboardContext.tsx`: DashboardProvider 추가. activeTab 및 5개 기능별 상태(바이어 이메일, 영업 실적, 스펙 현지화, 가격 매트릭스, 전시회 보고서)를 한 곳에서 관리. setActiveTab, setBuyerEmail, setSalesAnalyzer 등 개별 setter 제공.
  - `src/components/dashboard/TradeAXDashboard.tsx`: 5개 기능 패널을 모두 렌더링하고 `activeTab === id ? 'block' : 'hidden'`으로 표시만 전환(Keep-Alive). 탭 전환 시 언마운트되지 않아 입력/결과 유지.
  - `src/app/layout.tsx`: DashboardProvider로 전체 앱 래핑.

- **사이드바·Home**
  - `src/components/layout/Sidebar.tsx`: Next.js Link 제거, `useDashboard()`로 activeTab/setActiveTab 사용. 로고+TradeAX 영역을 버튼으로 만들어 클릭 시 `setActiveTab('buyer-email')` 호출(Home). 메뉴 항목은 버튼으로 `setActiveTab(id)` 호출. 활성 탭 하이라이트는 `activeTab === item.id` 기준.

- **단일 라우트·리다이렉트**
  - `src/app/page.tsx`: TradeAXDashboard만 렌더. `useSearchParams()`로 `?tab=...` 읽어 초기 탭 설정 후 Suspense 경계로 감쌈.
  - `src/app/sales-analyzer/page.tsx`, `spec-localizer`, `price-matrix`, `exhibition-report`: 각각 `router.replace('/?tab=...')` 리다이렉트 페이지로 변경.

- **입력 컴포넌트 controlled 모드**
  - SalesAnalyzerInput: optional `rows`, `onRowsLoad` 추가(파일 로드 시 context 반영).
  - SpecLocalizerPanel: optional `inputText`, `sourceLang`, `targetLang` 및 각 onChange 추가.
  - PriceMatrixInput: optional `initialRows`, `initialRawText`, `onRowsChange`, `onRawTextChange` 추가.
  - ExhibitionReportInput: optional `initialForm`, `onFormChange` 추가.

- **브라우저 저장**
  - DashboardContext 초기값을 `localStorage.getItem('tradeax-dashboard-state')`로 복원. `useEffect`로 state 변경 시 `localStorage.setItem` 호출(loading은 저장 제외). 새로고침 후에도 작업 내용 유지.
