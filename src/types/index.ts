/**
 * 5개 핵심 기능용 데이터 타입 정의
 * CSV/Excel 컬럼명은 한글·영어 모두 매핑 가능하도록 유연하게 설계
 */

/** 1. 바이어 이메일 생성기 - CSV 행 */
export interface BuyerRow {
  buyerName: string;
  country: string;
  productInfo: string;
  /** 파싱 시 추가 컬럼 매핑용 (이메일, 회사명 등) */
  [key: string]: string;
}

/** 바이어 이메일 테이블용 행: 생성 상태 및 생성된 본문 포함 (인덱스 시그니처 충돌 회피로 별도 정의) */
export type BuyerEmailStatus = "pending" | "generated";

export interface BuyerEmailRow {
  buyerName: string;
  country: string;
  productInfo: string;
  status: BuyerEmailStatus;
  /** AI 생성 이메일 마크다운 (상세보기/전송 시 사용) */
  generatedContent?: string;
  email?: string;
  company?: string;
  [key: string]: string | undefined;
}

/** 2. 영업 실적 분석 - 월별 수출 데이터 행 */
export interface SalesRow {
  month: string;
  country?: string;
  product?: string;
  amount?: number;
  revenue?: number;
  /** 기타 메트릭 */
  [key: string]: string | number | undefined;
}

/** 3. 다국어 제품 스펙 현지화 - 입력은 텍스트만 */
export type ProductSpecText = string;

/** 4. 경쟁사 가격 매트릭스 - 우리 가격 vs 경쟁사 */
export interface PriceRow {
  productName: string;
  ourPrice: number | string;
  competitorA?: number | string;
  competitorB?: number | string;
  competitorC?: number | string;
  [key: string]: string | number | undefined;
}

/** 5. 전시회 실행 보고서 - 폼 필드 */
export interface ExhibitionFormData {
  exhibitionName: string;
  dates: string;
  consultationsCount: string;
  keyBuyers: string;
  estimatedRevenue: string;
  notes: string;
}

/** 네비게이션 탭 ID */
export type ToolId =
  | "buyer-email"
  | "sales-analyzer"
  | "spec-localizer"
  | "price-matrix"
  | "exhibition-report";

export interface NavItem {
  id: ToolId;
  label: string;
  shortLabel?: string;
}
