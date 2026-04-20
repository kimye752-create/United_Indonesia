"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { ArrowLeftRight, Languages, Loader2 } from "lucide-react";

/** 글로벌 무역용 언어 목록 (소스/타깃 공용) */
export const SPEC_LOCALIZER_LANGUAGES = [
  { value: "ko", label: "한국어 (Korean)" },
  { value: "en", label: "영어 (English)" },
  { value: "ja", label: "일본어 (Japanese)" },
  { value: "zh-CN", label: "중국어-간체 (Chinese-Simplified)" },
  { value: "zh-TW", label: "중국어-번체 (Chinese-Traditional)" },
  { value: "es", label: "스페인어 (Spanish)" },
  { value: "fr", label: "프랑스어 (French)" },
  { value: "de", label: "독일어 (German)" },
  { value: "ru", label: "러시아어 (Russian)" },
  { value: "pt", label: "포르투갈어 (Portuguese)" },
  { value: "it", label: "이탈리아어 (Italian)" },
  { value: "vi", label: "베트남어 (Vietnamese)" },
  { value: "th", label: "태국어 (Thai)" },
  { value: "id", label: "인도네시아어 (Indonesian)" },
  { value: "ar", label: "아랍어 (Arabic)" },
] as const;

export type SpecLocalizerLangCode = (typeof SPEC_LOCALIZER_LANGUAGES)[number]["value"];

/** 소스 언어 옵션: 언어 감지 + 위 목록 */
const SOURCE_OPTIONS = [
  { value: "auto", label: "언어 감지 (Auto Detect)" },
  ...SPEC_LOCALIZER_LANGUAGES,
];

interface SpecLocalizerPanelProps {
  onTranslate: (text: string, sourceLanguage: string, targetLanguage: string) => Promise<void>;
  output: string;
  isLoading: boolean;
  error: string | null;
  /** 컨텍스트 연동(controlled): 탭 전환 시 입력 유지 */
  inputText?: string;
  onInputTextChange?: (value: string) => void;
  sourceLang?: string;
  onSourceLangChange?: (value: string) => void;
  targetLang?: string;
  onTargetLangChange?: (value: string) => void;
}

export function SpecLocalizerPanel({
  onTranslate,
  output,
  isLoading,
  error,
  inputText: controlledInputText,
  onInputTextChange,
  sourceLang: controlledSourceLang,
  onSourceLangChange,
  targetLang: controlledTargetLang,
  onTargetLangChange,
}: SpecLocalizerPanelProps) {
  const [internalInput, setInternalInput] = useState("");
  const [internalSource, setInternalSource] = useState<string>("auto");
  const [internalTarget, setInternalTarget] = useState<string>("en");

  const isControlled =
    controlledInputText !== undefined && onInputTextChange !== undefined &&
    controlledSourceLang !== undefined && onSourceLangChange !== undefined &&
    controlledTargetLang !== undefined && onTargetLangChange !== undefined;

  const inputText = isControlled ? controlledInputText : internalInput;
  const sourceLang = isControlled ? controlledSourceLang : internalSource;
  const targetLang = isControlled ? controlledTargetLang : internalTarget;

  const setInputText = useCallback(
    (v: string | ((prev: string) => string)) => {
      const next = typeof v === "function" ? v(inputText) : v;
      if (isControlled) onInputTextChange?.(next);
      else setInternalInput(next);
    },
    [isControlled, inputText, onInputTextChange]
  );
  const setSourceLang = useCallback(
    (v: string) => {
      if (isControlled) onSourceLangChange?.(v);
      else setInternalSource(v);
    },
    [isControlled, onSourceLangChange]
  );
  const setTargetLang = useCallback(
    (v: string) => {
      if (isControlled) onTargetLangChange?.(v);
      else setInternalTarget(v);
    },
    [isControlled, onTargetLangChange]
  );

  const handleSwap = useCallback(() => {
    const newSource = targetLang;
    const newTarget = sourceLang === "auto" ? "ko" : sourceLang;
    setSourceLang(newSource);
    setTargetLang(newTarget);
  }, [sourceLang, targetLang, setSourceLang, setTargetLang]);

  const handleTranslate = useCallback(() => {
    if (!inputText.trim()) return;
    onTranslate(inputText.trim(), sourceLang, targetLang);
  }, [inputText, sourceLang, targetLang, onTranslate]);

  return (
    <div className="flex flex-col gap-4">
      {/* 컨트롤 바: 소스 / 스왑 / 타깃 */}
      <div className="flex flex-wrap items-center gap-3 p-3 rounded-lg bg-gray-50 border border-gray-200">
        <div className="flex-1 min-w-[140px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">원문 언어</label>
          <select
            value={sourceLang}
            onChange={(e) => setSourceLang(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-navy-500"
          >
            {SOURCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end pb-2">
          <button
            type="button"
            onClick={handleSwap}
            className="p-2 rounded-lg border border-gray-300 bg-white text-gray-600 hover:bg-gray-100"
            aria-label="소스·타깃 언어 맞바꾸기"
          >
            <ArrowLeftRight className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 min-w-[140px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">번역 언어</label>
          <select
            value={targetLang}
            onChange={(e) => setTargetLang(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-navy-500"
          >
            {SPEC_LOCALIZER_LANGUAGES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end pb-2 w-full sm:w-auto">
          <button
            type="button"
            onClick={handleTranslate}
            disabled={!inputText.trim() || isLoading}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 bg-navy-700 text-white text-sm font-medium rounded-lg hover:bg-navy-800 disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Languages className="w-4 h-4" />
            )}
            번역
          </button>
        </div>
      </div>

      {/* 좌우(또는 모바일에서 위아래) 텍스트 영역 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="flex flex-col min-h-[280px] rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 text-sm font-medium text-navy-800">
            입력
          </div>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="제품 스펙, 비즈니스 문구 등을 입력하세요."
            className="flex-1 min-h-[240px] p-4 text-sm resize-none focus:ring-2 focus:ring-navy-500 focus:border-navy-500 border-0"
          />
        </div>
        <div className="flex flex-col min-h-[280px] rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 text-sm font-medium text-navy-800">
            결과
          </div>
          <div className="flex-1 min-h-[240px] overflow-auto p-4">
            {error ? (
              <p className="text-sm text-red-600">{error}</p>
            ) : isLoading ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <Loader2 className="w-10 h-10 animate-spin mb-2" />
                <span className="text-sm">번역 중...</span>
              </div>
            ) : output ? (
              <div className="prose-output prose prose-sm max-w-none text-sm">
                <ReactMarkdown>{output}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-gray-400">번역 결과가 여기에 표시됩니다.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
