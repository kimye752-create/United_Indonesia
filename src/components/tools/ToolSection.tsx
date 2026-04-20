"use client";

import { OutputZone } from "@/components/output/OutputZone";

interface ToolSectionProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  outputContent: string;
  outputLoading: boolean;
  /** API 오류 시 표시할 메시지 */
  outputError?: string | null;
  exportPrefix?: string;
}

/** 각 도구 페이지의 공통 구조: 제목 + 입력 영역 + 출력 영역 */
export function ToolSection({
  title,
  description,
  children,
  outputContent,
  outputLoading,
  outputError,
  exportPrefix = "tradeax",
}: ToolSectionProps) {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-navy-900">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-gray-600 whitespace-pre-line">{description}</p>
        )}
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="flex flex-col">
          <h2 className="text-sm font-semibold text-navy-800 mb-2">입력</h2>
          {children}
        </section>
        <section className="flex flex-col min-h-[360px]">
          <h2 className="text-sm font-semibold text-navy-800 mb-2">결과</h2>
          {outputError && (
            <div className="mb-3 p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm">
              {outputError}
            </div>
          )}
          <OutputZone
            content={outputContent}
            isLoading={outputLoading}
            exportPrefix={exportPrefix}
          />
        </section>
      </div>
    </div>
  );
}
