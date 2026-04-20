"use client";

import { ChevronLeft, ChevronRight, Eye, Send, Loader2 } from "lucide-react";
import type { BuyerEmailRow } from "@/types";

const ITEMS_PER_PAGE = 10;

interface BuyerEmailTableProps {
  buyers: BuyerEmailRow[];
  currentPage: number;
  onPageChange: (page: number) => void;
  onDetail: (index: number) => void;
  onSend: (index: number) => void;
  onGenerate: (index: number) => void;
  /** 현재 생성 중인 행의 인덱스 (로딩 표시) */
  generatingIndex: number | null;
}

export function BuyerEmailTable({
  buyers,
  currentPage,
  onPageChange,
  onDetail,
  onSend,
  onGenerate,
  generatingIndex,
}: BuyerEmailTableProps) {
  const totalPages = Math.max(1, Math.ceil(buyers.length / ITEMS_PER_PAGE));
  const start = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageRows = buyers.slice(start, start + ITEMS_PER_PAGE);

  const displayName = (row: BuyerEmailRow) =>
    row.buyerName?.trim() || (row.company ?? "").trim() || "-";
  const displayEmail = (row: BuyerEmailRow) =>
    (row.email ?? "").trim() || "-";

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-navy-50 border-b border-navy-100">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-navy-800">
                바이어 / 회사
              </th>
              <th className="px-4 py-3 text-left font-semibold text-navy-800">
                이메일
              </th>
              <th className="px-4 py-3 text-left font-semibold text-navy-800 w-28">
                상태
              </th>
              <th className="px-4 py-3 text-right font-semibold text-navy-800 w-48">
                작업
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                  바이어 목록을 불러온 후 표시됩니다.
                </td>
              </tr>
            ) : (
              pageRows.map((row, i) => {
                const globalIndex = start + i;
                const isGenerating = generatingIndex === globalIndex;
                const isGenerated = row.status === "generated";
                const hasEmail = (row.email ?? "").trim().length > 0;

                return (
                  <tr
                    key={globalIndex}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-4 py-3 text-gray-900 font-medium">
                      {displayName(row)}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {displayEmail(row)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          isGenerated
                            ? "text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-xs font-medium"
                            : "text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-xs font-medium"
                        }
                      >
                        {isGenerated ? "Generated" : "Pending"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {!isGenerated && (
                          <button
                            type="button"
                            onClick={() => onGenerate(globalIndex)}
                            disabled={isGenerating}
                            className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-navy-700 bg-navy-50 border border-navy-200 rounded hover:bg-navy-100 disabled:opacity-50"
                          >
                            {isGenerating ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              "Generate"
                            )}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => onDetail(globalIndex)}
                          disabled={isGenerating}
                          className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-navy-700 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          상세보기
                        </button>
                        <button
                          type="button"
                          onClick={() => onSend(globalIndex)}
                          disabled={!isGenerated || !hasEmail}
                          className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-white bg-navy-600 rounded hover:bg-navy-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Send className="w-3.5 h-3.5" />
                          전송
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {buyers.length > ITEMS_PER_PAGE && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
          <span className="text-xs text-gray-600">
            전체 {buyers.length}건 · {start + 1}–{Math.min(start + ITEMS_PER_PAGE, buyers.length)} 표시
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage <= 1}
              className="p-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="이전 페이지"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => {
                if (totalPages <= 7) return true;
                if (p === 1 || p === totalPages) return true;
                if (Math.abs(p - currentPage) <= 1) return true;
                return false;
              })
              .map((p, i, arr) => (
                <span key={p}>
                  {i > 0 && arr[i - 1] !== p - 1 && (
                    <span className="px-1 text-gray-400">…</span>
                  )}
                  <button
                    type="button"
                    onClick={() => onPageChange(p)}
                    className={
                      "min-w-[2rem] py-1.5 px-2 rounded text-sm font-medium " +
                      (p === currentPage
                        ? "bg-navy-600 text-white"
                        : "text-gray-600 hover:bg-gray-200")
                    }
                  >
                    {p}
                  </button>
                </span>
              ))}
            <button
              type="button"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="p-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="다음 페이지"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export { ITEMS_PER_PAGE };
