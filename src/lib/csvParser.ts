/**
 * CSV/Excel 파싱 유틸 - 한글·영어 컬럼명 모두 지원
 * papaparse + xlsx 사용
 */
import Papa from "papaparse";
import * as XLSX from "xlsx";
import type { BuyerRow, SalesRow, PriceRow } from "@/types";

/** CSV 문자열을 2차원 배열로 파싱 후 첫 행을 헤더로 사용해 객체 배열로 변환 */
function parseCsvToObjects<T extends Record<string, string | number | undefined>>(
  csvString: string,
  headerMap?: Record<string, string>
): T[] {
  const result = Papa.parse<Record<string, string>>(csvString, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.trim(),
  });
  if (result.errors.length > 0) {
    throw new Error(result.errors.map((e) => e.message).join(", "));
  }
  const rows = result.data as Record<string, string>[];
  if (!headerMap) return rows as unknown as T[];
  return rows.map((row) => {
    const mapped: Record<string, string | number | undefined> = {};
    for (const [rawKey, value] of Object.entries(row)) {
      const key = headerMap[rawKey] ?? rawKey;
      const num = Number(value);
      mapped[key] = Number.isNaN(num) ? value : num;
    }
    return mapped as T;
  });
}

/** 바이어 목록 CSV 컬럼 매핑 (예제1_바이어목록.csv 등) */
const BUYER_HEADER_MAP: Record<string, string> = {
  "바이어명": "buyerName",
  "Buyer Name": "buyerName",
  "국가": "country",
  "Country": "country",
  "제품정보": "productInfo",
  "Product": "productInfo",
  "제품": "productInfo",
  "이메일": "email",
  "Email": "email",
  "회사명": "company",
  "Company": "company",
};

export function parseBuyerCsv(csvString: string): BuyerRow[] {
  const rows = parseCsvToObjects<BuyerRow>(csvString, BUYER_HEADER_MAP);
  return rows.map((r) => ({
    ...r,
    buyerName: r.buyerName ?? "",
    country: r.country ?? "",
    productInfo: r.productInfo ?? "",
  }));
}

/** 영업 실적 CSV 컬럼 매핑 (예제2_수출실적.csv 등) */
const SALES_HEADER_MAP: Record<string, string> = {
  "월": "month",
  "Month": "month",
  "기준월": "month",
  "국가": "country",
  "Country": "country",
  "제품": "product",
  "Product": "product",
  "금액": "amount",
  "Amount": "amount",
  "매출": "revenue",
  "Revenue": "revenue",
  "수출액": "revenue",
  "건수": "count",
  "Count": "count",
};

export function parseSalesCsv(csvString: string): SalesRow[] {
  return parseCsvToObjects<SalesRow>(csvString, SALES_HEADER_MAP);
}

/** 경쟁사 가격 CSV 컬럼 매핑 */
const PRICE_HEADER_MAP: Record<string, string> = {
  "제품명": "productName",
  "Product": "productName",
  "우리가격": "ourPrice",
  "Our Price": "ourPrice",
  "경쟁사A": "competitorA",
  "Competitor A": "competitorA",
  "경쟁사B": "competitorB",
  "Competitor B": "competitorB",
  "경쟁사C": "competitorC",
  "Competitor C": "competitorC",
};

export function parsePriceCsv(csvString: string): PriceRow[] {
  return parseCsvToObjects<PriceRow>(csvString, PRICE_HEADER_MAP);
}

/** Excel 파일 (ArrayBuffer) → 첫 시트 CSV 문자열 */
export function xlsxToCsvString(buffer: ArrayBuffer): string {
  const wb = XLSX.read(buffer, { type: "array" });
  const firstSheetName = wb.SheetNames[0];
  const ws = wb.Sheets[firstSheetName];
  return XLSX.utils.sheet_to_csv(ws);
}

/** 바이어 Excel 업로드 */
export function parseBuyerExcel(buffer: ArrayBuffer): BuyerRow[] {
  return parseBuyerCsv(xlsxToCsvString(buffer));
}

/** 영업 실적 Excel 업로드 */
export function parseSalesExcel(buffer: ArrayBuffer): SalesRow[] {
  return parseSalesCsv(xlsxToCsvString(buffer));
}

/** 경쟁사 가격 Excel 업로드 */
export function parsePriceExcel(buffer: ArrayBuffer): PriceRow[] {
  return parsePriceCsv(xlsxToCsvString(buffer));
}
