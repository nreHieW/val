"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Plus, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getTickers } from "../searchbar/search-bar";
import PeerComparisonPanels from "./peer-comparison-panels";
import { FinancialComparisonRow } from "@/lib/financialComparison";

const SUGGESTIONS_PREVIEW_COUNT = 6;

type TickerResult = {
  Ticker: string;
  name: string;
};

function parsePeers(raw: string | null, mainTicker: string): string[] {
  if (!raw) return [];
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((ticker) => ticker.trim().toUpperCase())
        .filter((ticker) => ticker.length > 0 && ticker !== mainTicker),
    ),
  );
}

export default function PeerComparisonTab({ ticker }: { ticker: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const normalizedMainTicker = ticker.toUpperCase();
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<TickerResult[]>([]);
  const [peers, setPeers] = useState<string[]>(() =>
    parsePeers(searchParams.get("peers"), normalizedMainTicker),
  );
  const [suggestedPeers, setSuggestedPeers] = useState<string[]>([]);
  const [rowsState, setRowsState] = useState<{
    key: string;
    rows: FinancialComparisonRow[];
  }>({ key: "", rows: [] });
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/similar-companies?ticker=${encodeURIComponent(normalizedMainTicker)}`, {
      signal: controller.signal,
      cache: "no-store",
    })
      .then((response) => (response.ok ? response.json() : { tickers: [] }))
      .then((data: { tickers?: string[] }) => {
        const similarPeers = parsePeers(
          Array.isArray(data.tickers) ? data.tickers.join(",") : "",
          normalizedMainTicker,
        );
        setSuggestedPeers(similarPeers);
      })
      .catch((error) => {
        if ((error as DOMException).name !== "AbortError") {
          setSuggestedPeers([]);
        }
      });

    return () => controller.abort();
  }, [normalizedMainTicker]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
    }, 200);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    if (!debouncedSearchQuery) {
      return;
    }

    const controller = new AbortController();
    getTickers(debouncedSearchQuery, controller.signal)
      .then((results) => {
        const filtered = results.filter(
          (result) => result.Ticker.toUpperCase() !== normalizedMainTicker,
        );
        setSearchResults(filtered);
      })
      .catch((error) => {
        if ((error as DOMException).name !== "AbortError") {
          setSearchResults([]);
        }
      });

    return () => controller.abort();
  }, [debouncedSearchQuery, normalizedMainTicker]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (peers.length === 0) {
      params.delete("peers");
    } else {
      params.set("peers", peers.join(","));
    }

    params.delete("metrics");

    const nextQuery = params.toString();
    const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
    const currentQuery = searchParams.toString();
    const currentUrl = currentQuery ? `${pathname}?${currentQuery}` : pathname;
    if (nextUrl !== currentUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [pathname, peers, router, searchParams]);

  useEffect(() => {
    const tickers = [normalizedMainTicker, ...peers];
    const key = tickers.join(",");
    const controller = new AbortController();
    fetch(`/api/financials?tickers=${encodeURIComponent(key)}`, {
      signal: controller.signal,
      cache: "no-store",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch comparison data");
        }
        return response.json();
      })
      .then((data: FinancialComparisonRow[]) => {
        const byTicker = new Map(
          data.map((item) => [item.Ticker.toUpperCase(), item] as const),
        );
        const ordered = tickers
          .map((itemTicker) => byTicker.get(itemTicker))
          .filter((item): item is FinancialComparisonRow => Boolean(item));
        setRowsState({ key, rows: ordered });
      })
      .catch((error) => {
        if ((error as DOMException).name !== "AbortError") {
          setRowsState({ key, rows: [] });
        }
      });

    return () => controller.abort();
  }, [normalizedMainTicker, peers]);

  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  const normalizedResults = searchResults.filter(
    (result) =>
      !peers.includes(result.Ticker.toUpperCase()) &&
      result.Ticker.toUpperCase() !== normalizedMainTicker,
  );
  const allAvailableSuggestions = suggestedPeers.filter((peer) => !peers.includes(peer)).slice(0, 40);
  const availableSuggestions = showAllSuggestions
    ? allAvailableSuggestions
    : allAvailableSuggestions.slice(0, SUGGESTIONS_PREVIEW_COUNT);
  const hasMoreSuggestions = allAvailableSuggestions.length > SUGGESTIONS_PREVIEW_COUNT;
  const SuggestionToggleIcon = showAllSuggestions ? ChevronUp : ChevronDown;
  const suggestionToggleLabel = showAllSuggestions ? "Show less" : `${allAvailableSuggestions.length - SUGGESTIONS_PREVIEW_COUNT} more`;

  function addPeer(tickerToAdd: string) {
    const normalized = tickerToAdd.toUpperCase();
    if (normalized === normalizedMainTicker || peers.includes(normalized)) {
      return;
    }
    setPeers((prev) => [...prev, normalized]);
    setSearchQuery("");
    setDebouncedSearchQuery("");
    setSearchResults([]);
    searchInputRef.current?.focus();
  }

  function removePeer(tickerToRemove: string) {
    setPeers((prev) => prev.filter((item) => item !== tickerToRemove));
  }

  const showDropdown = searchQuery.length > 0 && normalizedResults.length > 0;
  const showNoResults =
    searchQuery.length > 0 &&
    debouncedSearchQuery.length > 0 &&
    normalizedResults.length === 0;
  const rowsKey = [normalizedMainTicker, ...peers].join(",");
  const rows = rowsState.key === rowsKey ? rowsState.rows : [];
  const isLoadingRows = rowsState.key !== rowsKey;

  return (
    <div className="space-y-8 pt-2">
      <div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/40" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && normalizedResults.length > 0) {
                addPeer(normalizedResults[0].Ticker);
              }
            }}
            placeholder="Search by ticker or company name"
            className="w-full rounded-lg border bg-background py-2.5 pl-9 pr-3 text-sm placeholder:text-muted-foreground/40 outline-none transition-all focus:border-foreground/20 focus:ring-1 focus:ring-ring/50"
            spellCheck="false"
            autoCorrect="off"
          />
          {showNoResults && (
            <p className="absolute left-0 top-full mt-1.5 text-xs text-muted-foreground">
              No matching tickers
            </p>
          )}
          {showDropdown && (
            <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-52 overflow-auto rounded-lg border bg-background shadow-lg scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border">
              {normalizedResults.slice(0, 10).map((result) => (
                <li key={result.Ticker}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-xs transition-colors hover:bg-muted/50"
                    onClick={() => addPeer(result.Ticker)}
                  >
                    <span className="min-w-[3.5rem] font-medium tabular-nums">{result.Ticker}</span>
                    <span className="truncate text-muted-foreground">{result.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={`flex flex-wrap items-center gap-1.5 ${showNoResults ? "mt-8" : "mt-3"}`}>
          <span className="inline-flex items-center rounded-md bg-foreground px-2.5 py-1 text-xs font-medium text-background">
            {normalizedMainTicker}
          </span>
          {peers.map((peerTicker) => (
            <span
              key={peerTicker}
              className="group inline-flex items-center gap-1 rounded-md border border-border/60 bg-background px-2.5 py-1 text-xs tabular-nums transition-colors hover:border-foreground/20"
            >
              {peerTicker}
              <button
                type="button"
                className="-mr-0.5 rounded p-0.5 text-muted-foreground/50 transition-colors hover:text-foreground"
                onClick={() => removePeer(peerTicker)}
                aria-label={`Remove ${peerTicker}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {peers.length > 0 && (
            <button
              type="button"
              className="ml-1 text-xs text-muted-foreground/50 transition-colors hover:text-foreground"
              onClick={() => setPeers([])}
            >
              Clear
            </button>
          )}
        </div>

        {allAvailableSuggestions.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xxs font-medium uppercase tracking-wider text-muted-foreground/50">Suggested peers</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {availableSuggestions.map((peerTicker) => (
                <button
                  key={peerTicker}
                  type="button"
                  className="inline-flex items-center gap-1 rounded-md border border-dashed border-border/60 px-2.5 py-1 text-xs tabular-nums text-muted-foreground transition-all hover:border-foreground/25 hover:text-foreground"
                  onClick={() => addPeer(peerTicker)}
                >
                  <Plus className="h-2.5 w-2.5" />
                  {peerTicker}
                </button>
              ))}
              {hasMoreSuggestions && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground/50 transition-colors hover:text-foreground"
                  onClick={() => setShowAllSuggestions((prev) => !prev)}
                >
                  <SuggestionToggleIcon className="h-3 w-3" /> {suggestionToggleLabel}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className={isLoadingRows ? "opacity-60 transition-opacity" : "transition-opacity"}>
        <PeerComparisonPanels rows={rows} mainTicker={normalizedMainTicker} />
      </div>
    </div>
  );
}
