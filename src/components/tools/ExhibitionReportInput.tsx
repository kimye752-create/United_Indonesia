"use client";

import { useState, useCallback } from "react";
import { FileText } from "lucide-react";
import type { ExhibitionFormData } from "@/types";

const INITIAL: ExhibitionFormData = {
  exhibitionName: "",
  dates: "",
  consultationsCount: "",
  keyBuyers: "",
  estimatedRevenue: "",
  notes: "",
};

interface ExhibitionReportInputProps {
  onSubmit: (data: ExhibitionFormData) => void;
  isSubmitting: boolean;
  /** 컨텍스트 연동(controlled): 탭 전환 시 폼 유지 */
  initialForm?: ExhibitionFormData;
  onFormChange?: (form: ExhibitionFormData) => void;
}

export function ExhibitionReportInput({
  onSubmit,
  isSubmitting,
  initialForm,
  onFormChange,
}: ExhibitionReportInputProps) {
  const isControlled = initialForm !== undefined && onFormChange !== undefined;
  const [internalForm, setInternalForm] = useState<ExhibitionFormData>(INITIAL);
  const form = isControlled ? initialForm : internalForm;

  const setForm = useCallback(
    (next: ExhibitionFormData | ((prev: ExhibitionFormData) => ExhibitionFormData)) => {
      const value = typeof next === "function" ? next(form) : next;
      if (isControlled) onFormChange?.(value);
      else setInternalForm(value);
    },
    [isControlled, form, onFormChange]
  );

  const update = useCallback((field: keyof ExhibitionFormData, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  }, [setForm]);

  const handleSubmit = useCallback(() => {
    onSubmit(form);
  }, [onSubmit, form]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        전시회 실행 보고서 (경영진용 2페이지 요약)
      </label>
      <p className="text-xs text-gray-500 mb-4">
        입력 후 AI가 한글 경영진 요약 보고서(마크다운 테이블 포함)를 생성합니다.
      </p>
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">전시회명</label>
          <input
            type="text"
            value={form.exhibitionName}
            onChange={(e) => update("exhibitionName", e.target.value)}
            placeholder="예: Canton Fair 2024"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">기간</label>
          <input
            type="text"
            value={form.dates}
            onChange={(e) => update("dates", e.target.value)}
            placeholder="예: 2024-10-15 ~ 2024-10-19"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">상담 건수</label>
          <input
            type="text"
            value={form.consultationsCount}
            onChange={(e) => update("consultationsCount", e.target.value)}
            placeholder="예: 120"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">주요 바이어</label>
          <input
            type="text"
            value={form.keyBuyers}
            onChange={(e) => update("keyBuyers", e.target.value)}
            placeholder="예: ABC Corp (USA), XYZ GmbH (Germany)"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">예상 매출 (USD)</label>
          <input
            type="text"
            value={form.estimatedRevenue}
            onChange={(e) => update("estimatedRevenue", e.target.value)}
            placeholder="예: 500,000"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">비고</label>
          <textarea
            value={form.notes}
            onChange={(e) => update("notes", e.target.value)}
            placeholder="추가 메모"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-navy-500"
          />
        </div>
      </div>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={isSubmitting}
        className="mt-4 w-full inline-flex items-center justify-center gap-2 py-2.5 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
      >
        <FileText className="w-4 h-4" />
        실행 보고서 생성
      </button>
    </div>
  );
}
