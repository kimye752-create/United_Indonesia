"use client";

import { useCallback, useState } from "react";
import { Upload, FileSpreadsheet, AlertCircle } from "lucide-react";
import type { BuyerRow } from "@/types";
import { parseBuyerCsv, parseBuyerExcel } from "@/lib/csvParser";

interface BuyerEmailInputProps {
  /** CSV 파싱된 바이어 목록을 테이블에 반영 (온디맨드 생성용) */
  onLoadList: (rows: BuyerRow[]) => void;
}

export function BuyerEmailInput({ onLoadList }: BuyerEmailInputProps) {
  const [rows, setRows] = useState<BuyerRow[]>([]);
  const [error, setError] = useState<string | null>(null);

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
          const parsed = isCsv ? parseBuyerCsv(text) : parseBuyerExcel(reader.result as ArrayBuffer);
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
    []
  );

  const handleSubmit = useCallback(() => {
    onLoadList(rows);
  }, [onLoadList, rows]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        바이어 목록 (CSV 또는 Excel)
      </label>
      <p className="text-xs text-gray-500 mb-2">
        컬럼: 바이어명/Buyer Name, 국가/Country, 제품정보/Product 등
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
                <th className="px-2 py-1.5 text-left">바이어</th>
                <th className="px-2 py-1.5 text-left">국가</th>
                <th className="px-2 py-1.5 text-left">제품</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((r, i) => (
                <tr key={i} className="border-t border-gray-100">
                  <td className="px-2 py-1.5">{r.buyerName}</td>
                  <td className="px-2 py-1.5">{r.country}</td>
                  <td className="px-2 py-1.5 truncate max-w-[120px]">{r.productInfo}</td>
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
        onClick={handleSubmit}
        disabled={rows.length === 0}
        className="w-full inline-flex items-center justify-center gap-2 py-2.5 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
      >
        <FileSpreadsheet className="w-4 h-4" />
        목록 불러오기 (테이블에 적용)
      </button>
    </div>
  );
}
