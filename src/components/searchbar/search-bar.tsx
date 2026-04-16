"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Loading } from "../ui/loading";
import { useRouter } from "next/navigation";

type TickerResult = {
  Ticker: string;
  name: string;
};

export const getTickers = async (
  query: string,
  signal?: AbortSignal
): Promise<TickerResult[]> => {
  const response = await fetch(`/api/tickers?query=${encodeURIComponent(query)}`, {
    signal,
  });
  if (!response.ok) {
    throw new Error("Failed to fetch tickers");
  }
  return response.json();
};

export default function SearchBar() {
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [items, setItems] = useState<TickerResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 200);

    return () => {
      clearTimeout(handler);
    };
  }, [searchQuery]);

  useEffect(() => {
    const controller = new AbortController();
    const getResults = async () => {
      if (!debouncedSearchQuery) {
        setItems([]);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        let results: TickerResult[] = await getTickers(
          debouncedSearchQuery,
          controller.signal
        );
        results = results.sort((a, b) => {
          if (a.Ticker.toLowerCase() === debouncedSearchQuery.toLowerCase())
            return -1;
          if (b.Ticker.toLowerCase() === debouncedSearchQuery.toLowerCase())
            return 1;
          return 0;
        });
        setItems(results);
      } catch (error) {
        if ((error as DOMException).name !== "AbortError") {
          setItems([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    getResults();
    return () => {
      controller.abort();
    };
  }, [debouncedSearchQuery]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && items.length > 0) {
      const firstItem = items[0];
      const displayText = firstItem.Ticker + "  -  " + firstItem.name;
      const urlSlug = displayText
        .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g, "")
        .split(/\s+/)
        .join("-");
      router.push(`/ticker/${urlSlug}`);
    }
  };

  const hasResults = items.length > 0 && searchQuery.length > 0 && !isLoading;

  return (
    <div className="w-full min-w-0">
      <input
        type="text"
        className={`w-full py-3 px-5 border border-border bg-background text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring transition-shadow ${
          hasResults ? "rounded-t-3xl rounded-b-xl" : "rounded-full"
        }`}
        value={searchQuery}
        placeholder="Search for a ticker..."
        spellCheck="false"
        autoCorrect="off"
        onChange={(event) => setSearchQuery(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {isLoading ? (
        <div className="py-6 justify-center flex">
          <Loading />
        </div>
      ) : hasResults ? (
        <ul className="py-1.5 mt-0.5 w-full min-w-0 max-h-64 overflow-auto rounded-b-2xl border border-border bg-background scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border">
          {items.map((item: TickerResult, index) => {
            const ticker = item.Ticker;
            const name = item.name;
            const displayText = ticker + "  -  " + name;
            const urlSlug = displayText
              .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g, "")
              .split(/\s+/)
              .join("-");
            return (
              <SearchItem
                key={index}
                text={displayText}
                url={`/ticker/${urlSlug}`}
              />
            );
          })}
        </ul>
      ) : (
        debouncedSearchQuery.length > 0 &&
        items.length === 0 && (
          <div className="text-center text-xs text-muted-foreground py-4">No results found</div>
        )
      )}
    </div>
  );
}

interface SearchItemProps {
  text: string;
  url: string;
}

function SearchItem({ text, url }: SearchItemProps) {
  return (
    <li className="text-xs px-4 py-1.5 hover:bg-accent transition-colors w-full min-w-0">
      <Link href={url} className="inline-block w-full truncate">{text}</Link>
    </li>
  );
}
