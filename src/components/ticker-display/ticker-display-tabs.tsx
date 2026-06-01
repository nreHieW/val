"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import PeerComparisonTab from "./peer-comparison-tab";

type TickerTab = "overview" | "dcf" | "comparison";

export default function TickerDisplayTabs({
  ticker,
  overview,
  children,
}: {
  ticker: string;
  overview: React.ReactNode;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<TickerTab>(() => {
    const tab = searchParams.get("tab");
    if (tab === "dcf" || tab === "comparison") return tab;
    return "overview";
  });

  function setTab(nextTab: TickerTab) {
    setActiveTab(nextTab);
    const params = new URLSearchParams(searchParams.toString());
    if (nextTab === "overview") {
      params.delete("tab");
    } else {
      params.set("tab", nextTab);
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
          aria-selected={activeTab === "overview"}
          className={`relative pb-2.5 text-sm transition-colors ${
            activeTab === "overview"
              ? "font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground/80"
          }`}
          onClick={() => setTab("overview")}
        >
          Overview
          {activeTab === "overview" && (
            <span className="absolute inset-x-0 -bottom-px h-[1.5px] rounded-full bg-foreground" />
          )}
        </button>
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
          DCF
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
          Compare
          {activeTab === "comparison" && (
            <span className="absolute inset-x-0 -bottom-px h-[1.5px] rounded-full bg-foreground" />
          )}
        </button>
      </nav>

      <div role="tabpanel" className={activeTab === "overview" ? "block" : "hidden"}>
        {overview}
      </div>
      <div role="tabpanel" className={activeTab === "dcf" ? "block" : "hidden"}>{children}</div>
      <div role="tabpanel" className={activeTab === "comparison" ? "block" : "hidden"}>
        <PeerComparisonTab key={ticker} ticker={ticker} />
      </div>
    </div>
  );
}
