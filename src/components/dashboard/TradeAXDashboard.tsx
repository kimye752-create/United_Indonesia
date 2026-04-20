"use client";

import { useCallback } from "react";
import { useDashboard } from "@/context/DashboardContext";
import type { ToolId } from "@/types";
import type { BuyerRow, BuyerEmailRow } from "@/types";
import { callAnalyzeApi } from "@/lib/analyzeApi";
import { BuyerEmailInput } from "@/components/tools/BuyerEmailInput";
import { BuyerEmailTable } from "@/components/tools/BuyerEmailTable";
import { EmailDetailModal } from "@/components/tools/EmailDetailModal";
import { ToolSection } from "@/components/tools/ToolSection";
import { SalesAnalyzerInput } from "@/components/tools/SalesAnalyzerInput";
import { SpecLocalizerPanel } from "@/components/tools/SpecLocalizerPanel";
import { PriceMatrixInput } from "@/components/tools/PriceMatrixInput";
import { ExhibitionReportInput } from "@/components/tools/ExhibitionReportInput";
import type { SalesRow } from "@/types";
import type { PriceRow } from "@/types";
import type { ExhibitionFormData } from "@/types";

function toBuyerRow(b: BuyerEmailRow): BuyerRow {
  const { status: _s, generatedContent: _g, ...rest } = b;
  return rest as BuyerRow;
}

async function generateOneEmail(row: BuyerRow): Promise<string> {
  return callAnalyzeApi("buyer-email", [row]);
}

function buildMailtoLink(email: string, subject: string, body: string): string {
  const to = (email || "").trim();
  const s = subject.trim() || "Partnership inquiry";
  const b = body.trim() || "";
  const params = new URLSearchParams();
  if (to) params.set("to", to);
  params.set("subject", s);
  if (b) params.set("body", b);
  const q = params.toString();
  return q ? `mailto:${to || ""}?${q}` : to ? `mailto:${to}` : "mailto:";
}

const PANEL_IDS: ToolId[] = [
  "buyer-email",
  "sales-analyzer",
  "spec-localizer",
  "price-matrix",
  "exhibition-report",
];

export function TradeAXDashboard() {
  const { state, setActiveTab, setBuyerEmail, setSalesAnalyzer, setSpecLocalizer, setPriceMatrix, setExhibitionReport } =
    useDashboard();
  const { activeTab, buyerEmail, salesAnalyzer, specLocalizer, priceMatrix, exhibitionReport } = state;

  const handleBuyerSend = useCallback((index: number) => {
    const row = buyerEmail.buyers[index];
    if (!row?.generatedContent) return;
    const email = (row.email ?? "").trim();
    const subject = row.productInfo?.trim().slice(0, 60) || "Partnership inquiry";
    const body = row.generatedContent;
    window.open(buildMailtoLink(email, subject, body), "_blank", "noopener");
  }, [buyerEmail.buyers]);

  return (
    <>
      {PANEL_IDS.map((id) => (
        <div
          key={id}
          className={activeTab === id ? "block" : "hidden"}
          aria-hidden={activeTab !== id}
        >
          {id === "buyer-email" && (
            <BuyerEmailPanel
              state={buyerEmail}
              setState={setBuyerEmail}
              onSend={handleBuyerSend}
            />
          )}
          {id === "sales-analyzer" && (
            <SalesAnalyzerPanel state={salesAnalyzer} setState={setSalesAnalyzer} />
          )}
          {id === "spec-localizer" && (
            <SpecLocalizerPanelPanel state={specLocalizer} setState={setSpecLocalizer} />
          )}
          {id === "price-matrix" && (
            <PriceMatrixPanel state={priceMatrix} setState={setPriceMatrix} />
          )}
          {id === "exhibition-report" && (
            <ExhibitionReportPanel state={exhibitionReport} setState={setExhibitionReport} />
          )}
        </div>
      ))}
    </>
  );
}

/** Feature 1: 바이어 이메일 */
function BuyerEmailPanel({
  state,
  setState,
  onSend,
}: {
  state: import("@/context/DashboardContext").BuyerEmailState;
  setState: import("@/context/DashboardContext").DashboardContextValue["setBuyerEmail"];
  onSend: (index: number) => void;
}) {
  const selectedBuyer = state.selectedIndex !== null ? state.buyers[state.selectedIndex] ?? null : null;
  const modalContent = selectedBuyer?.generatedContent ?? "";
  const handleLoadList = useCallback(
    (rows: BuyerRow[]) => {
      setState({
        buyers: rows.map((r) => ({ ...r, status: "pending" as const })),
        currentPage: 1,
        selectedIndex: null,
        error: null,
      });
    },
    [setState]
  );

  const generateForRow = useCallback(
    async (index: number) => {
      const row = state.buyers[index];
      if (!row || row.status === "generated") return;
      setState({ generatingIndex: index, error: null });
      try {
        const content = await generateOneEmail(toBuyerRow(row));
        setState((prev) => ({
          buyers: prev.buyers.map((b, i) =>
            i === index ? { ...b, status: "generated" as const, generatedContent: content } : b
          ),
          generatingIndex: null,
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : "생성 실패";
        setState({ generatingIndex: null, error: message });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [state.buyers, setState]
  );

  const handleDetail = useCallback(
    async (index: number) => {
      const row = state.buyers[index];
      if (!row) return;
      if (row.status === "generated") {
        setState({ selectedIndex: index });
        return;
      }
      setState({ generatingIndex: index, error: null });
      try {
        const content = await generateOneEmail(toBuyerRow(row));
        setState((prev) => ({
          buyers: prev.buyers.map((b, i) =>
            i === index ? { ...b, status: "generated" as const, generatedContent: content } : b
          ),
          selectedIndex: index,
          generatingIndex: null,
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : "생성 실패";
        setState({ generatingIndex: null, error: message });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [state.buyers, setState]
  );

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-navy-900">바이어 이메일 생성기</h1>
        <p className="mt-1 text-sm text-gray-600">
          CSV/Excel 바이어 목록을 불러온 뒤, 행별로 생성·상세보기·전송할 수 있습니다.
        </p>
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <section className="lg:col-span-4">
          <h2 className="text-sm font-semibold text-navy-800 mb-2">입력</h2>
          <BuyerEmailInput onLoadList={handleLoadList} />
        </section>
        <section className="lg:col-span-8 flex flex-col min-h-[360px]">
          <h2 className="text-sm font-semibold text-navy-800 mb-2">결과</h2>
          {state.error && (
            <div className="mb-3 p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm">
              {state.error}
            </div>
          )}
          <BuyerEmailTable
            buyers={state.buyers}
            currentPage={state.currentPage}
            onPageChange={(p) => setState({ currentPage: p })}
            onDetail={handleDetail}
            onSend={onSend}
            onGenerate={generateForRow}
            generatingIndex={state.generatingIndex}
          />
        </section>
      </div>
      <EmailDetailModal
        isOpen={state.selectedIndex !== null}
        buyer={selectedBuyer}
        content={modalContent}
        isLoading={state.generatingIndex === state.selectedIndex && state.selectedIndex !== null}
        onClose={() => setState({ selectedIndex: null })}
        onContentUpdate={(value) => {
          if (state.selectedIndex !== null) {
            setState((prev) => ({
              buyers: prev.buyers.map((b, i) =>
                i === state.selectedIndex ? { ...b, generatedContent: value } : b
              ),
            }));
          }
        }}
      />
    </div>
  );
}

/** Feature 2: 영업 실적 분석 */
function SalesAnalyzerPanel({
  state,
  setState,
}: {
  state: import("@/context/DashboardContext").SalesAnalyzerState;
  setState: import("@/context/DashboardContext").DashboardContextValue["setSalesAnalyzer"];
}) {
  const handleAnalyze = useCallback(
    async (rows: SalesRow[]) => {
      setState({ loading: true, output: "", error: null, rows });
      try {
        const content = await callAnalyzeApi("sales-analyzer", rows);
        setState({ output: content, loading: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : "요청 실패";
        setState({ error: message, loading: false });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [setState]
  );

  return (
    <ToolSection
      title="영업 실적 분석기"
      description={"월별 수출 실적 CSV/Excel을 업로드하면 다음 내용을 분석합니다:\n1. 전월 대비 증감이 큰 품목 TOP 3\n2. 국가별 성장/하락 트렌드\n3. 하반기 집중해야 할 시장 (추천 이유 포함)"}
      outputContent={state.output}
      outputLoading={state.loading}
      outputError={state.error}
      exportPrefix="sales-analysis"
    >
      <SalesAnalyzerInput
        onAnalyze={handleAnalyze}
        isAnalyzing={state.loading}
        rows={state.rows}
        onRowsLoad={(rows) => setState({ rows })}
      />
    </ToolSection>
  );
}

/** Feature 3: 다국어 스펙 현지화 */
function SpecLocalizerPanelPanel({
  state,
  setState,
}: {
  state: import("@/context/DashboardContext").SpecLocalizerState;
  setState: import("@/context/DashboardContext").DashboardContextValue["setSpecLocalizer"];
}) {
  const handleTranslate = useCallback(
    async (text: string, sourceLanguage: string, targetLanguage: string) => {
      setState({ loading: true, output: "", error: null });
      try {
        const content = await callAnalyzeApi("spec-localizer", {
          text,
          sourceLanguage,
          targetLanguage,
        });
        setState({ output: content, loading: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : "요청 실패";
        setState({ error: message, loading: false });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [setState]
  );

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-navy-900">다국어 제품 스펙 현지화</h1>
        <p className="mt-1 text-sm text-gray-600 whitespace-pre-line">
          원문 언어를 선택하거나 자동 감지 후, 번역할 언어를 선택해 B2B 비즈니스 톤으로 현지화합니다.
        </p>
      </header>
      <SpecLocalizerPanel
        onTranslate={handleTranslate}
        output={state.output}
        isLoading={state.loading}
        error={state.error}
        inputText={state.inputText}
        onInputTextChange={(v) => setState({ inputText: v })}
        sourceLang={state.sourceLang}
        onSourceLangChange={(v) => setState({ sourceLang: v })}
        targetLang={state.targetLang}
        onTargetLangChange={(v) => setState({ targetLang: v })}
      />
    </div>
  );
}

/** Feature 4: 경쟁사 가격 매트릭스 */
function PriceMatrixPanel({
  state,
  setState,
}: {
  state: import("@/context/DashboardContext").PriceMatrixState;
  setState: import("@/context/DashboardContext").DashboardContextValue["setPriceMatrix"];
}) {
  const handleAnalyze = useCallback(
    async (rows: PriceRow[] | null, rawText: string) => {
      const data = rows && rows.length > 0 ? rows : rawText;
      setState({ loading: true, output: "", error: null });
      try {
        const content = await callAnalyzeApi("price-matrix", data);
        setState({ output: content, loading: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : "요청 실패";
        setState({ error: message, loading: false });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [setState]
  );

  return (
    <ToolSection
      title="경쟁사 가격 매트릭스"
      description="우리 가격과 경쟁사 가격을 입력하면 포지셔닝, 차별화 포인트, 협상 논거 3가지를 분석합니다."
      outputContent={state.output}
      outputLoading={state.loading}
      outputError={state.error}
      exportPrefix="price-matrix"
    >
      <PriceMatrixInput
        onAnalyze={handleAnalyze}
        isAnalyzing={state.loading}
        initialRows={state.rows}
        initialRawText={state.rawText}
        onRowsChange={(rows) => setState({ rows })}
        onRawTextChange={(rawText) => setState({ rawText })}
      />
    </ToolSection>
  );
}

/** Feature 5: 전시회 보고서 */
function ExhibitionReportPanel({
  state,
  setState,
}: {
  state: import("@/context/DashboardContext").ExhibitionReportState;
  setState: import("@/context/DashboardContext").DashboardContextValue["setExhibitionReport"];
}) {
  const handleSubmit = useCallback(
    async (data: ExhibitionFormData) => {
      setState({ loading: true, output: "", error: null, form: data });
      try {
        const content = await callAnalyzeApi("exhibition-report", data);
        setState({ output: content, loading: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : "요청 실패";
        setState({ error: message, loading: false });
        if (typeof window !== "undefined") window.alert(message);
      }
    },
    [setState]
  );

  return (
    <ToolSection
      title="전시회 실행 보고서"
      description="전시회명, 기간, 상담 수, 주요 바이어, 예상 매출 등을 입력하면 경영진용 한글 실행 요약 보고서를 생성합니다."
      outputContent={state.output}
      outputLoading={state.loading}
      outputError={state.error}
      exportPrefix="exhibition-report"
    >
      <ExhibitionReportInput
        onSubmit={handleSubmit}
        isSubmitting={state.loading}
        initialForm={state.form}
        onFormChange={(form) => setState({ form })}
      />
    </ToolSection>
  );
}
