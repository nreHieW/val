"use client";

import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getTickers } from "../searchbar/search-bar";
import { Button } from "../ui/button";
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
  const [visibleMetrics, setVisibleMetrics] = useState<MetricKey[]>(() =>
    parseVisibleMetrics(searchParams.get("metrics")),
  );

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

  return (
    <div className="space-y-4 pt-3">
      <div className="rounded border p-3">
        <p className="text-xs text-muted-foreground pb-2">
          Add peer companies to compare against {normalizedMainTicker}.
        </p>
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && normalizedResults.length > 0) {
              addPeer(normalizedResults[0].Ticker);
            }
          }}
          placeholder="Search ticker..."
          className="w-full rounded border px-3 py-2 text-sm outline-none focus:ring-1"
          spellCheck="false"
          autoCorrect="off"
        />
        {searchQuery.length > 0 && normalizedResults.length === 0 ? (
          <p className="pt-2 text-xs text-muted-foreground">No matching tickers.</p>
        ) : null}
        {normalizedResults.length > 0 ? (
          <ul className="mt-2 max-h-48 overflow-auto rounded border bg-background">
            {normalizedResults.slice(0, 10).map((result) => (
              <li key={result.Ticker}>
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left text-xs hover:bg-muted/60"
                  onClick={() => addPeer(result.Ticker)}
                >
                  {result.Ticker} - {result.name}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="rounded border p-3">
        <p className="pb-2 text-xs font-medium">Companies</p>
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center rounded border bg-muted/60 px-2 py-1 text-xs font-semibold">
            {normalizedMainTicker} (Main)
          </span>
          {peers.map((peerTicker) => (
            <span
              key={peerTicker}
              className="inline-flex items-center rounded border px-2 py-1 text-xs"
            >
              {peerTicker}
              <button
                type="button"
                className="ml-1 inline-flex items-center"
                onClick={() => removePeer(peerTicker)}
                aria-label={`Remove ${peerTicker}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {peers.length > 0 ? (
            <Button
              type="button"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={() => setPeers([])}
            >
              Clear Peers
            </Button>
          ) : null}
        </div>
      </div>

      <div className="rounded border p-3">
        <p className="pb-2 text-xs font-medium">Visible Metrics</p>
        <div className="flex flex-wrap gap-2">
          {METRICS.map((metric) => {
            const isActive = visibleMetrics.includes(metric.key);
            return (
              <button
                key={metric.key}
                type="button"
                onClick={() => toggleMetric(metric.key)}
                className={`rounded border px-2 py-1 text-xs ${
                  isActive ? "bg-muted/80 font-medium" : "opacity-70"
                }`}
              >
                {metric.label}
              </button>
            );
          })}
        </div>
      </div>

      <PeerMetricsTable
        rows={rows}
        mainTicker={normalizedMainTicker}
        visibleMetrics={visibleMetrics}
      />
    </div>
  );
}
