"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import { TradeAXDashboard } from "@/components/dashboard/TradeAXDashboard";
import type { ToolId } from "@/types";

const VALID_TABS: ToolId[] = [
  "buyer-email",
  "sales-analyzer",
  "spec-localizer",
  "price-matrix",
  "exhibition-report",
];

function HomeContent() {
  const searchParams = useSearchParams();
  const { setActiveTab } = useDashboard();

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && VALID_TABS.includes(tab as ToolId)) {
      setActiveTab(tab as ToolId);
    }
  }, [searchParams, setActiveTab]);

  return <TradeAXDashboard />;
}

export default function HomePage() {
  return (
    <Suspense fallback={<div className="p-6 min-h-[200px] flex items-center justify-center text-gray-500">로딩 중...</div>}>
      <HomeContent />
    </Suspense>
  );
}
