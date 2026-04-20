"use client";

import {
  Mail,
  BarChart3,
  Languages,
  DollarSign,
  FileText,
  Bot,
  Home,
} from "lucide-react";
import { useDashboard } from "@/context/DashboardContext";
import type { NavItem, ToolId } from "@/types";

const NAV_ITEMS: NavItem[] = [
  { id: "buyer-email", label: "바이어 이메일 생성기", shortLabel: "이메일" },
  { id: "sales-analyzer", label: "영업 실적 분석기", shortLabel: "실적분석" },
  { id: "spec-localizer", label: "다국어 스펙 현지화", shortLabel: "스펙현지화" },
  { id: "price-matrix", label: "경쟁사 가격 매트릭스", shortLabel: "가격매트릭스" },
  { id: "exhibition-report", label: "전시회 실행 보고서", shortLabel: "전시회보고서" },
];

const ICON_MAP: Record<ToolId, React.ComponentType<{ className?: string }>> = {
  "buyer-email": Mail,
  "sales-analyzer": BarChart3,
  "spec-localizer": Languages,
  "price-matrix": DollarSign,
  "exhibition-report": FileText,
};

/** Feature 1 = 바이어 이메일 생성기 (Home 버튼 클릭 시 이동) */
const HOME_TAB: ToolId = "buyer-email";

export function Sidebar() {
  const { state, setActiveTab } = useDashboard();
  const activeTab = state.activeTab;

  const handleHome = () => setActiveTab(HOME_TAB);
  const handleNav = (id: ToolId) => () => setActiveTab(id);

  return (
    <aside className="w-56 min-h-screen bg-navy-900 text-white flex flex-col shrink-0">
      <button
        type="button"
        onClick={handleHome}
        className="w-full p-4 border-b border-navy-700 flex items-center gap-2 hover:bg-navy-800 transition-colors text-left"
        aria-label="홈 (바이어 이메일 생성기)"
      >
        <Bot className="w-8 h-8 text-navy-200 shrink-0" />
        <span className="font-semibold text-lg">TradeAX Copilot</span>
        <Home className="w-4 h-4 ml-auto text-navy-400 shrink-0" />
      </button>
      <nav className="p-2 flex-1">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = ICON_MAP[item.id];
            const isActive = activeTab === item.id;

            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={handleNav(item.id)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                    ${isActive ? "bg-navy-700 text-white" : "text-navy-200 hover:bg-navy-800 hover:text-white"}
                  `}
                >
                  {Icon && <Icon className="w-5 h-5 shrink-0" />}
                  <span className="truncate">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="p-3 border-t border-navy-700 text-navy-400 text-xs">
        AI 기반 무역·수출 영업 도우미
      </div>
    </aside>
  );
}
