"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { X, Loader2 } from "lucide-react";
import type { BuyerEmailRow } from "@/types";

interface EmailDetailModalProps {
  isOpen: boolean;
  buyer: BuyerEmailRow | null;
  /** 표시/편집할 마크다운 본문 */
  content: string;
  /** 이 행에 대해 API 생성 중일 때 */
  isLoading: boolean;
  onClose: () => void;
  /** 사용자가 본문을 편집했을 때 (부모에서 해당 행 generatedContent 업데이트) */
  onContentUpdate: (value: string) => void;
}

export function EmailDetailModal({
  isOpen,
  buyer,
  content,
  isLoading,
  onClose,
  onContentUpdate,
}: EmailDetailModalProps) {
  const [editing, setEditing] = useState(false);
  const [localContent, setLocalContent] = useState(content);

  useEffect(() => {
    setLocalContent(content);
  }, [content]);

  useEffect(() => {
    if (!isOpen) setEditing(false);
  }, [isOpen]);

  const handleSaveEdit = () => {
    onContentUpdate(localContent);
    setEditing(false);
  };

  const title =
    buyer?.buyerName?.trim() ||
    (buyer?.company ?? "").trim() ||
    "이메일 상세";

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="email-modal-title"
    >
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
          <h2 id="email-modal-title" className="text-lg font-semibold text-navy-900">
            {title}
            {buyer?.country && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                · {buyer.country}
              </span>
            )}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            aria-label="닫기"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-500">
              <Loader2 className="w-10 h-10 animate-spin mb-3" />
              <span className="text-sm">이메일 생성 중...</span>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-gray-100 bg-gray-50 shrink-0">
                {editing ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setLocalContent(content);
                        setEditing(false);
                      }}
                      className="px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-200 rounded"
                    >
                      취소
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveEdit}
                      className="px-3 py-1.5 text-sm font-medium text-white bg-navy-600 rounded hover:bg-navy-700"
                    >
                      저장
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="px-3 py-1.5 text-sm font-medium text-navy-700 bg-navy-50 border border-navy-200 rounded hover:bg-navy-100"
                  >
                    소스 편집
                  </button>
                )}
              </div>
              <div className="flex-1 overflow-auto p-4">
                {editing ? (
                  <textarea
                    value={localContent}
                    onChange={(e) => setLocalContent(e.target.value)}
                    className="w-full h-64 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono resize-y focus:ring-2 focus:ring-navy-500 focus:border-navy-500"
                    placeholder="마크다운으로 이메일 본문을 편집하세요."
                    spellCheck={false}
                  />
                ) : (
                  <div className="prose-output prose prose-sm max-w-none text-sm">
                    <ReactMarkdown>{localContent || "*내용 없음*"}</ReactMarkdown>
                  </div>
                )}
                {editing && (
                  <p className="mt-2 text-xs text-gray-500">
                    저장 후 미리보기가 갱신됩니다. 전송 시에도 수정된 내용이 사용됩니다.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
