"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ExhibitionReportRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/?tab=exhibition-report");
  }, [router]);
  return (
    <div className="p-6 flex items-center justify-center min-h-[200px] text-gray-500">
      이동 중...
    </div>
  );
}
