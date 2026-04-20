"use client";

import { useState, useCallback } from "react";
import { Languages } from "lucide-react";

const TARGET_LANGUAGES = [
  { value: "en", label: "English" },
  { value: "zh", label: "中文 (Chinese)" },
  { value: "es", label: "Español (Spanish)" },
] as const;

export type SpecLocalizerLanguage = (typeof TARGET_LANGUAGES)[number]["value"];

interface SpecLocalizerInputProps {
  onLocalize: (text: string, lang: SpecLocalizerLanguage) => void;
  isLocalizing: boolean;
}

export function SpecLocalizerInput({ onLocalize, isLocalizing }: SpecLocalizerInputProps) {
  const [text, setText] = useState("");
  const [lang, setLang] = useState<SpecLocalizerLanguage>("en");

  const handleSubmit = useCallback(() => {
    onLocalize(text, lang);
  }, [onLocalize, text, lang]);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        한국어 제품 스펙 (원문)
      </label>
      <p className="text-xs text-gray-500 mb-2">
        직역이 아닌, 해당 지역 바이어에 맞는 B2B 비즈니스 톤으로 현지화합니다.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="제품명, 규격, 인증, 용도 등을 입력하세요."
        rows={8}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-navy-500 focus:border-navy-500"
      />
      <div className="mt-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">대상 언어</label>
        <select
          value={lang}
          onChange={(e) => setLang(e.target.value as SpecLocalizerLanguage)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-navy-500"
        >
          {TARGET_LANGUAGES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!text.trim() || isLocalizing}
        className="mt-4 w-full inline-flex items-center justify-center gap-2 py-2.5 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
      >
        <Languages className="w-4 h-4" />
        현지화 생성
      </button>
    </div>
  );
}
