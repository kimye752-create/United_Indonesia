"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Copy, Download, Loader2 } from "lucide-react";

interface OutputZoneProps {
  content: string;
  isLoading?: boolean;
  /** 내보내기 파일명 접두사 */
  exportPrefix?: string;
}

/** 클립보드 복사 */
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** 마크다운을 Blob으로 다운로드 (.md) */
function downloadMarkdown(text: string, filename: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** 간단한 마크다운 → HTML 스타일 (Word 호환용 .html로 저장 시 Word에서 열 수 있음) */
function markdownToSimpleHtml(md: string): string {
  const lines = md.split("\n");
  let inTable = false;
  let html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"/><title>Report</title></head><body style="font-family: Malgun Gothic, sans-serif;">';
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("|") && line.includes("|")) {
      if (!inTable) {
        inTable = true;
        html += "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>";
      }
      const cells = line.split("|").filter((c) => c.trim() !== "").map((c) => c.trim());
      const isHeader = i > 0 && lines[i - 1].startsWith("|") && lines[i - 1].includes("---");
      const tag = isHeader ? "th" : "td";
      html += "<tr>";
      for (const cell of cells) {
        html += `<${tag}>${cell}</${tag}>`;
      }
      html += "</tr>";
    } else {
      if (inTable) {
        html += "</table>";
        inTable = false;
      }
      if (line.startsWith("### ")) {
        html += `<h3>${line.slice(4)}</h3>`;
      } else if (line.startsWith("## ")) {
        html += `<h2>${line.slice(3)}</h2>`;
      } else if (line.startsWith("# ")) {
        html += `<h1>${line.slice(2)}</h1>`;
      } else if (line.trim()) {
        html += `<p>${line}</p>`;
      }
    }
  }
  if (inTable) html += "</table>";
  html += "</body></html>";
  return html;
}

export function OutputZone({
  content,
  isLoading = false,
  exportPrefix = "tradeax-output",
}: OutputZoneProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [content]);

  const handleExportMd = useCallback(() => {
    const name = `${exportPrefix}-${new Date().toISOString().slice(0, 10)}.md`;
    downloadMarkdown(content, name);
  }, [content, exportPrefix]);

  const handleExportWord = useCallback(() => {
    const html = markdownToSimpleHtml(content);
    const blob = new Blob(
      ["\ufeff" + html],
      { type: "application/msword;charset=utf-8" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${exportPrefix}-${new Date().toISOString().slice(0, 10)}.doc`;
    a.click();
    URL.revokeObjectURL(url);
  }, [content, exportPrefix]);

  return (
    <div className="flex flex-col h-full min-h-[320px] rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <span className="text-sm font-medium text-navy-800">AI 결과</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopy}
            disabled={!content || isLoading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-navy-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            <Copy className="w-3.5 h-3.5" />
            {copied ? "복사됨" : "클립보드 복사"}
          </button>
          <button
            type="button"
            onClick={handleExportMd}
            disabled={!content || isLoading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-navy-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            Markdown
          </button>
          <button
            type="button"
            onClick={handleExportWord}
            disabled={!content || isLoading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-navy-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            Word
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Loader2 className="w-10 h-10 animate-spin mb-3" />
            <span className="text-sm">AI 분석 중...</span>
          </div>
        ) : content ? (
          <div className="prose-output prose max-w-none text-sm">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-gray-400 text-sm">결과가 여기에 표시됩니다.</p>
        )}
      </div>
    </div>
  );
}
