"use client";

import { useCallback, useState } from "react";
import { Upload, BarChart3, AlertCircle } from "lucide-react";
import type { SalesRow } from "@/types";
import { parseSalesCsv, parseSalesExcel } from "@/lib/csvParser";

interface SalesAnalyzerInputProps {
  onAnalyze: (rows: SalesRow[]) => void;
  isAnalyzing: boolean;
  /** 컨텍스트 연동: 외부에서 관리하는 rows (탭 전환 시 유지) */
  rows?: SalesRow[];
  /** 파일 로드 시 호출 (controlled 모드일 때 context 업데이트) */
  onRowsLoad?: (rows: SalesRow[]) => void;
}

export function SalesAnalyzerInput({
  onAnalyze,
  isAnalyzing,
  rows: controlledRows,
  onRowsLoad,
}: SalesAnalyzerInputProps) {
  const [internalRows, setInternalRows] = useState<SalesRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const isControlled = controlledRows !== undefined && onRowsLoad !== undefined;
  const rows = isControlled ? controlledRows : internalRows;

  const setRows = useCallback(
    (next: SalesRow[] | ((prev: SalesRow[]) => SalesRow[])) => {
      if (isControlled) {
        const value = typeof next === "function" ? next(controlledRows) : next;
        onRowsLoad?.(value);
      } else {
        setInternalRows(typeof next === "function" ? next(internalRows) : next);
      }
    },
    [isControlled, controlledRows, internalRows, onRowsLoad]
  );

  const handleFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setError(null);
      const isCsv = file.name.toLowerCase().endsWith(".csv");
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const text = reader.result as string;
          const parsed = isCsv ? parseSalesCsv(text) : parseSalesExcel(reader.result as ArrayBuffer);
          setRows(parsed);
        } catch (err) {
          setError(err instanceof Error ? err.message : "파일 파싱 실패");
          setRows([]);
        }
      };
      if (isCsv) reader.readAsText(file, "UTF-8");
      else reader.readAsArrayBuffer(file);
      e.target.value = "";
    },
    [setRows]
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        월별 수출 실적 데이터 (CSV 또는 Excel)
      </label>
      <p className="text-xs text-gray-500 mb-2">
        MoM 성장 Top 3, 국가별 트렌드, H2 권장 타깃 시장 분석용
      </p>
      <div className="flex items-center gap-2 mb-4">
        <label className="inline-flex items-center gap-2 px-3 py-2 bg-navy-50 border border-navy-200 rounded-lg cursor-pointer hover:bg-navy-100 text-sm font-medium text-navy-800">
          <Upload className="w-4 h-4" />
          파일 선택
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFile}
            className="hidden"
          />
        </label>
        <span className="text-xs text-gray-500">
          {rows.length > 0 ? `${rows.length}건 로드됨` : ""}
        </span>
      </div>
      {error && (
        <div className="flex items-center gap-2 text-amber-700 text-sm mb-3 bg-amber-50 p-2 rounded">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}
      {rows.length > 0 && (
        <div className="overflow-auto max-h-48 border border-gray-200 rounded mb-4">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="px-2 py-1.5 text-left">월</th>
                <th className="px-2 py-1.5 text-left">국가</th>
                <th className="px-2 py-1.5 text-left">금액/매출</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((r, i) => (
                <tr key={i} className="border-t border-gray-100">
                  <td className="px-2 py-1.5">{String(r.month)}</td>
                  <td className="px-2 py-1.5">{String(r.country ?? "-")}</td>
                  <td className="px-2 py-1.5">{String(r.amount ?? r.revenue ?? "-")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 10 && (
            <p className="text-xs text-gray-500 px-2 py-1">외 {rows.length - 10}건</p>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={() => onAnalyze(rows.slice())}
        disabled={rows.length === 0 || isAnalyzing}
        className="w-full inline-flex items-center justify-center gap-2 py-2.5 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
      >
        <BarChart3 className="w-4 h-4" />
        실적 분석 실행
      </button>
    </div>
  );
}
