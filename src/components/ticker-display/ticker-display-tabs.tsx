"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import PeerComparisonTab from "./peer-comparison-tab";

export default function TickerDisplayTabs({
  ticker,
  children,
}: {
  ticker: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<"dcf" | "comparison">(() => {
    const tab = searchParams.get("tab");
    return tab === "comparison" ? "comparison" : "dcf";
  });

  function setTab(nextTab: "dcf" | "comparison") {
    setActiveTab(nextTab);
    const params = new URLSearchParams(searchParams.toString());
    if (nextTab === "dcf") {
      params.delete("tab");
    } else {
      params.set("tab", "comparison");
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div>
      <div className="mb-4 flex gap-2 border-b">
        <button
          type="button"
          className={`rounded-t px-3 py-2 text-sm ${
            activeTab === "dcf" ? "border border-b-0 font-semibold" : "opacity-70"
          }`}
          onClick={() => setTab("dcf")}
        >
          DCF Model
        </button>
        <button
          type="button"
          className={`rounded-t px-3 py-2 text-sm ${
            activeTab === "comparison"
              ? "border border-b-0 font-semibold"
              : "opacity-70"
          }`}
          onClick={() => setTab("comparison")}
        >
          Company Comparison
        </button>
      </div>

      <div className={activeTab === "dcf" ? "block" : "hidden"}>{children}</div>
      <div className={activeTab === "comparison" ? "block" : "hidden"}>
        <PeerComparisonTab ticker={ticker} />
      </div>
    </div>
  );
}
