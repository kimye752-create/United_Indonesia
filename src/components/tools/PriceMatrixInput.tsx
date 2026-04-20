"use client";

import { useCallback, useState } from "react";
import { Upload, DollarSign, AlertCircle } from "lucide-react";
import type { PriceRow } from "@/types";
import { parsePriceCsv, parsePriceExcel } from "@/lib/csvParser";

interface PriceMatrixInputProps {
  onAnalyze: (rows: PriceRow[] | null, rawText: string) => void;
  isAnalyzing: boolean;
  /** 컨텍스트 연동(controlled) */
  initialRows?: PriceRow[] | null;
  initialRawText?: string;
  onRowsChange?: (rows: PriceRow[] | null) => void;
  onRawTextChange?: (rawText: string) => void;
}

export function PriceMatrixInput({
  onAnalyze,
  isAnalyzing,
  initialRows,
  initialRawText,
  onRowsChange,
  onRawTextChange,
}: PriceMatrixInputProps) {
  const [internalRows, setInternalRows] = useState<PriceRow[] | null>(null);
  const [internalRawText, setInternalRawText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isControlled =
    initialRows !== undefined &&
    initialRawText !== undefined &&
    onRowsChange !== undefined &&
    onRawTextChange !== undefined;
  const rows = isControlled ? initialRows : internalRows;
  const rawText = isControlled ? initialRawText : internalRawText;

  const setRows = useCallback(
    (next: PriceRow[] | null) => {
      if (isControlled) onRowsChange?.(next);
      else setInternalRows(next);
    },
    [isControlled, onRowsChange]
  );
  const setRawText = useCallback(
    (next: string) => {
      if (isControlled) onRawTextChange?.(next);
      else setInternalRawText(next);
    },
    [isControlled, onRawTextChange]
  );

  const handleFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setError(null);
      setRawText("");
      const isCsv = file.name.toLowerCase().endsWith(".csv");
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const text = reader.result as string;
          const parsed = isCsv ? parsePriceCsv(text) : parsePriceExcel(reader.result as ArrayBuffer);
          setRows(parsed);
        } catch (err) {
          setError(err instanceof Error ? err.message : "파일 파싱 실패");
          setRows(null);
        }
      };
      if (isCsv) reader.readAsText(file, "UTF-8");
      else reader.readAsArrayBuffer(file);
      e.target.value = "";
    },
    [setRows, setRawText]
  );

  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setRawText(e.target.value);
      setRows(null);
      setError(null);
    },
    [setRows, setRawText]
  );

  const handleSubmit = useCallback(() => {
    if (rows && rows.length > 0) {
      onAnalyze(rows, "");
    } else if (rawText.trim()) {
      onAnalyze(null, rawText.trim());
    }
  }, [onAnalyze, rows, rawText]);

  const canSubmit = (rows && rows.length > 0) || rawText.trim().length > 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        우리 가격 vs 경쟁사 가격
      </label>
      <p className="text-xs text-gray-500 mb-2">
        CSV/Excel 업로드 또는 텍스트로 입력 (포지셔닝, 차별화, 협상 논거 3가지 분석)
      </p>
      <div className="flex items-center gap-2 mb-3">
        <label className="inline-flex items-center gap-2 px-3 py-2 bg-navy-50 border border-navy-200 rounded-lg cursor-pointer hover:bg-navy-100 text-sm font-medium text-navy-800">
          <Upload className="w-4 h-4" />
          CSV/Excel
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFile}
            className="hidden"
          />
        </label>
        {rows && rows.length > 0 && (
          <span className="text-xs text-gray-500">{rows.length}건 로드됨</span>
        )}
      </div>
      <textarea
        value={rawText}
        onChange={handleTextChange}
        placeholder="제품명, 우리가격, 경쟁사A, 경쟁사B 등 텍스트로 입력 가능"
        rows={6}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-navy-500 focus:border-navy-500"
      />
      {error && (
        <div className="flex items-center gap-2 text-amber-700 text-sm mt-2 bg-amber-50 p-2 rounded">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit || isAnalyzing}
        className="mt-4 w-full inline-flex items-center justify-center gap-2 py-2.5 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
      >
        <DollarSign className="w-4 h-4" />
        가격 매트릭스 분석
      </button>
    </div>
  );
}
