"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ToolId } from "@/types";
import type {
  BuyerEmailRow,
  SalesRow,
  PriceRow,
  ExhibitionFormData,
} from "@/types";

const STORAGE_KEY = "tradeax-dashboard-state";

/** Feature 1: 바이어 이메일 */
export interface BuyerEmailState {
  buyers: BuyerEmailRow[];
  currentPage: number;
  selectedIndex: number | null;
  generatingIndex: number | null;
  error: string | null;
}

/** Feature 2: 영업 실적 분석 */
export interface SalesAnalyzerState {
  rows: SalesRow[];
  output: string;
  loading: boolean;
  error: string | null;
}

/** Feature 3: 다국어 스펙 현지화 */
export interface SpecLocalizerState {
  inputText: string;
  sourceLang: string;
  targetLang: string;
  output: string;
  loading: boolean;
  error: string | null;
}

/** Feature 4: 경쟁사 가격 매트릭스 */
export interface PriceMatrixState {
  rows: PriceRow[] | null;
  rawText: string;
  output: string;
  loading: boolean;
  error: string | null;
}

/** Feature 5: 전시회 보고서 */
export interface ExhibitionReportState {
  form: ExhibitionFormData;
  output: string;
  loading: boolean;
  error: string | null;
}

const defaultExhibitionForm: ExhibitionFormData = {
  exhibitionName: "",
  dates: "",
  consultationsCount: "",
  keyBuyers: "",
  estimatedRevenue: "",
  notes: "",
};

export interface DashboardState {
  activeTab: ToolId;
  buyerEmail: BuyerEmailState;
  salesAnalyzer: SalesAnalyzerState;
  specLocalizer: SpecLocalizerState;
  priceMatrix: PriceMatrixState;
  exhibitionReport: ExhibitionReportState;
}

const defaultState: DashboardState = {
  activeTab: "buyer-email",
  buyerEmail: {
    buyers: [],
    currentPage: 1,
    selectedIndex: null,
    generatingIndex: null,
    error: null,
  },
  salesAnalyzer: {
    rows: [],
    output: "",
    loading: false,
    error: null,
  },
  specLocalizer: {
    inputText: "",
    sourceLang: "auto",
    targetLang: "en",
    output: "",
    loading: false,
    error: null,
  },
  priceMatrix: {
    rows: null,
    rawText: "",
    output: "",
    loading: false,
    error: null,
  },
  exhibitionReport: {
    form: defaultExhibitionForm,
    output: "",
    loading: false,
    error: null,
  },
};

export type DashboardContextValue = {
  state: DashboardState;
  setActiveTab: (tab: ToolId) => void;
  setBuyerEmail: (update: Partial<BuyerEmailState> | ((prev: BuyerEmailState) => Partial<BuyerEmailState>)) => void;
  setSalesAnalyzer: (update: Partial<SalesAnalyzerState> | ((prev: SalesAnalyzerState) => Partial<SalesAnalyzerState>)) => void;
  setSpecLocalizer: (update: Partial<SpecLocalizerState> | ((prev: SpecLocalizerState) => Partial<SpecLocalizerState>)) => void;
  setPriceMatrix: (update: Partial<PriceMatrixState> | ((prev: PriceMatrixState) => Partial<PriceMatrixState>)) => void;
  setExhibitionReport: (update: Partial<ExhibitionReportState> | ((prev: ExhibitionReportState) => Partial<ExhibitionReportState>)) => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

function loadPersistedState(): Partial<DashboardState> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DashboardState>;
    return parsed;
  } catch {
    return null;
  }
}

function persistState(state: DashboardState) {
  if (typeof window === "undefined") return;
  try {
    const toSave: Partial<DashboardState> = {
      activeTab: state.activeTab,
      buyerEmail: state.buyerEmail,
      salesAnalyzer: {
        ...state.salesAnalyzer,
        loading: false,
        rows: state.salesAnalyzer.rows,
        output: state.salesAnalyzer.output,
        error: state.salesAnalyzer.error,
      },
      specLocalizer: {
        ...state.specLocalizer,
        loading: false,
      },
      priceMatrix: {
        ...state.priceMatrix,
        loading: false,
      },
      exhibitionReport: {
        ...state.exhibitionReport,
        loading: false,
      },
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // ignore
  }
}

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<DashboardState>(() => {
    const persisted = loadPersistedState();
    if (!persisted) return defaultState;
    return {
      activeTab: persisted.activeTab ?? defaultState.activeTab,
      buyerEmail: { ...defaultState.buyerEmail, ...persisted.buyerEmail },
      salesAnalyzer: { ...defaultState.salesAnalyzer, ...persisted.salesAnalyzer },
      specLocalizer: { ...defaultState.specLocalizer, ...persisted.specLocalizer },
      priceMatrix: { ...defaultState.priceMatrix, ...persisted.priceMatrix },
      exhibitionReport: { ...defaultState.exhibitionReport, ...persisted.exhibitionReport },
    };
  });

  useEffect(() => {
    persistState(state);
  }, [state]);

  const setActiveTab = useCallback((tab: ToolId) => {
    setState((prev) => ({ ...prev, activeTab: tab }));
  }, []);

  const setBuyerEmail = useCallback(
    (update: Partial<BuyerEmailState> | ((prev: BuyerEmailState) => Partial<BuyerEmailState>)) => {
      setState((prev) => ({
        ...prev,
        buyerEmail: {
          ...prev.buyerEmail,
          ...(typeof update === "function" ? update(prev.buyerEmail) : update),
        },
      }));
    },
    []
  );

  const setSalesAnalyzer = useCallback(
    (update: Partial<SalesAnalyzerState> | ((prev: SalesAnalyzerState) => Partial<SalesAnalyzerState>)) => {
      setState((prev) => ({
        ...prev,
        salesAnalyzer: {
          ...prev.salesAnalyzer,
          ...(typeof update === "function" ? update(prev.salesAnalyzer) : update),
        },
      }));
    },
    []
  );

  const setSpecLocalizer = useCallback(
    (update: Partial<SpecLocalizerState> | ((prev: SpecLocalizerState) => Partial<SpecLocalizerState>)) => {
      setState((prev) => ({
        ...prev,
        specLocalizer: {
          ...prev.specLocalizer,
          ...(typeof update === "function" ? update(prev.specLocalizer) : update),
        },
      }));
    },
    []
  );

  const setPriceMatrix = useCallback(
    (update: Partial<PriceMatrixState> | ((prev: PriceMatrixState) => Partial<PriceMatrixState>)) => {
      setState((prev) => ({
        ...prev,
        priceMatrix: {
          ...prev.priceMatrix,
          ...(typeof update === "function" ? update(prev.priceMatrix) : update),
        },
      }));
    },
    []
  );

  const setExhibitionReport = useCallback(
    (update: Partial<ExhibitionReportState> | ((prev: ExhibitionReportState) => Partial<ExhibitionReportState>)) => {
      setState((prev) => ({
        ...prev,
        exhibitionReport: {
          ...prev.exhibitionReport,
          ...(typeof update === "function" ? update(prev.exhibitionReport) : update),
        },
      }));
    },
    []
  );

  const value = useMemo<DashboardContextValue>(
    () => ({
      state,
      setActiveTab,
      setBuyerEmail,
      setSalesAnalyzer,
      setSpecLocalizer,
      setPriceMatrix,
      setExhibitionReport,
    }),
    [
      state,
      setActiveTab,
      setBuyerEmail,
      setSalesAnalyzer,
      setSpecLocalizer,
      setPriceMatrix,
      setExhibitionReport,
    ]
  );

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used within DashboardProvider");
  return ctx;
}
