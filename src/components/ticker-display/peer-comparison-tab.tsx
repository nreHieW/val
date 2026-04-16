"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getTickers } from "../searchbar/search-bar";
import PeerMetricsTable from "./peer-metrics-table";
import {
  FinancialComparisonRow,
  METRICS,
  MetricKey,
} from "./peerComparisonHelpers";

type TickerResult = {
  Ticker: string;
  name: string;
};

const METRIC_KEY_SET = new Set(METRICS.map((metric) => metric.key));

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

function parseVisibleMetrics(raw: string | null): MetricKey[] {
  if (!raw) {
    return METRICS.map((metric) => metric.key);
  }
  const parsed = raw
    .split(",")
    .map((value) => value.trim())
    .filter((value): value is MetricKey => METRIC_KEY_SET.has(value as MetricKey));
  if (parsed.length === 0) {
    return METRICS.map((metric) => metric.key);
  }
  return Array.from(new Set(parsed));
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
  const [rows, setRows] = useState<FinancialComparisonRow[]>([]);
  const [isLoadingRows, setIsLoadingRows] = useState(false);
  const [visibleMetrics, setVisibleMetrics] = useState<MetricKey[]>(() =>
    parseVisibleMetrics(searchParams.get("metrics")),
  );
  const searchInputRef = useRef<HTMLInputElement>(null);

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

    const allMetrics = METRICS.map((metric) => metric.key);
    const isAllVisible =
      visibleMetrics.length === allMetrics.length &&
      allMetrics.every((metric) => visibleMetrics.includes(metric));
    if (isAllVisible) {
      params.delete("metrics");
    } else {
      params.set("metrics", visibleMetrics.join(","));
    }

    const nextQuery = params.toString();
    const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
    const currentQuery = searchParams.toString();
    const currentUrl = currentQuery ? `${pathname}?${currentQuery}` : pathname;
    if (nextUrl !== currentUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [pathname, peers, router, searchParams, visibleMetrics]);

  useEffect(() => {
    const tickers = [normalizedMainTicker, ...peers];
    const controller = new AbortController();
    setIsLoadingRows(true);
    fetch(`/api/financials?tickers=${encodeURIComponent(tickers.join(","))}`, {
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
        setRows(ordered);
      })
      .catch((error) => {
        if ((error as DOMException).name !== "AbortError") {
          setRows([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingRows(false);
        }
      });

    return () => controller.abort();
  }, [normalizedMainTicker, peers]);

  const normalizedResults = useMemo(
    () =>
      searchResults.filter(
        (result) =>
          !peers.includes(result.Ticker.toUpperCase()) &&
          result.Ticker.toUpperCase() !== normalizedMainTicker,
      ),
    [peers, searchResults, normalizedMainTicker],
  );

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

  function toggleMetric(metric: MetricKey) {
    setVisibleMetrics((prev) => {
      const next = prev.includes(metric)
        ? prev.filter((item) => item !== metric)
        : [...prev, metric];
      return next.length === 0 ? prev : next;
    });
  }

  const showDropdown = searchQuery.length > 0 && normalizedResults.length > 0;
  const showNoResults =
    searchQuery.length > 0 &&
    debouncedSearchQuery.length > 0 &&
    normalizedResults.length === 0;

  return (
    <div className="space-y-6 pt-2">
      {/* Search & peer chips */}
      <div>
        <div className="relative">
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
            placeholder="Add a peer company..."
            className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 outline-none transition-shadow focus:ring-1 focus:ring-ring"
            spellCheck="false"
            autoCorrect="off"
          />
          {showNoResults && (
            <p className="absolute left-0 top-full mt-1 text-xs text-muted-foreground">
              No matching tickers.
            </p>
          )}
          {showDropdown && (
            <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-48 overflow-auto rounded-md border bg-background shadow-md scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border">
              {normalizedResults.slice(0, 10).map((result) => (
                <li key={result.Ticker}>
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left text-xs transition-colors hover:bg-muted/60"
                    onClick={() => addPeer(result.Ticker)}
                  >
                    <span className="font-medium">{result.Ticker}</span>
                    <span className="text-muted-foreground"> — {result.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={`flex flex-wrap items-center gap-2 ${showNoResults ? "mt-8" : "mt-3"}`}>
          <span className="inline-flex items-center rounded-md bg-foreground/[0.06] px-2.5 py-1 text-xs font-semibold">
            {normalizedMainTicker}
          </span>
          {peers.map((peerTicker) => (
            <span
              key={peerTicker}
              className="group inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors"
            >
              {peerTicker}
              <button
                type="button"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setPeers([])}
            >
              Clear all
            </button>
          )}
        </div>
      </div>

      {/* Metric toggles */}
      <div>
        <p className="pb-2 text-xs font-medium text-muted-foreground">Metrics</p>
        <div className="flex flex-wrap gap-1.5">
          {METRICS.map((metric) => {
            const isActive = visibleMetrics.includes(metric.key);
            return (
              <button
                key={metric.key}
                type="button"
                onClick={() => toggleMetric(metric.key)}
                className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                  isActive
                    ? "border-foreground/20 bg-foreground/[0.06] font-medium text-foreground"
                    : "border-transparent text-muted-foreground/60 hover:text-muted-foreground"
                }`}
              >
                {metric.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Table */}
      <div className={isLoadingRows ? "opacity-60 transition-opacity" : "transition-opacity"}>
        <PeerMetricsTable
          rows={rows}
          mainTicker={normalizedMainTicker}
          visibleMetrics={visibleMetrics}
        />
      </div>
    </div>
  );
}
