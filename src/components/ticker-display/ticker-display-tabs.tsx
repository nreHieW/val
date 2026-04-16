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
      <nav className="mb-8 flex gap-6 border-b border-border/60" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "dcf"}
          className={`relative pb-2.5 text-sm transition-colors ${
            activeTab === "dcf"
              ? "font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground/80"
          }`}
          onClick={() => setTab("dcf")}
        >
          DCF Model
          {activeTab === "dcf" && (
            <span className="absolute inset-x-0 -bottom-px h-[1.5px] rounded-full bg-foreground" />
          )}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "comparison"}
          className={`relative pb-2.5 text-sm transition-colors ${
            activeTab === "comparison"
              ? "font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground/80"
          }`}
          onClick={() => setTab("comparison")}
        >
          Company Comparison
          {activeTab === "comparison" && (
            <span className="absolute inset-x-0 -bottom-px h-[1.5px] rounded-full bg-foreground" />
          )}
        </button>
      </nav>

      <div role="tabpanel" className={activeTab === "dcf" ? "block" : "hidden"}>{children}</div>
      <div role="tabpanel" className={activeTab === "comparison" ? "block" : "hidden"}>
        <PeerComparisonTab ticker={ticker} />
      </div>
    </div>
  );
}
