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
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState(""); // To prevent overcall
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
          console.error(error);
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
  return (
    <div className="w-full min-w-0">
      <input
        type="text"
        className="search w-full py-3 px-5 dark:outline-white outline outline-1 outline-zinc-950 rounded-full z-40"
        value={searchQuery}
        placeholder="Search for a ticker..."
        spellCheck="false"
        autoCorrect="off"
        onChange={(event) => setSearchQuery(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {isLoading ? (
        <div className="py-8 justify-center flex">
          <Loading />
        </div>
      ) : items.length > 0 && searchQuery.length > 0 ? (
        <ul className="results-list py-2 w-full min-w-0 max-h-64 overflow-auto scrollbar scrollbar-track-transparent dark:scrollbar-thumb-white scrollbar-thumb-black bg-transparent">
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
          <div className="text-center text-sm py-5">No results found</div>
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
    <li className="pt-1 text-sm hover:dark:bg-zinc-700 hover:py-1 hover:rounded px-5 hover:bg-zinc-300 w-full min-w-0 z-0">
      <Link href={url} className="inline-block w-full truncate">{text}</Link>
    </li>
  );
}
