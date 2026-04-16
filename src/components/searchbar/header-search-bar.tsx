"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Loading } from "../ui/loading";
import { Search, X } from "lucide-react";
import { getTickers } from "./search-bar";
import Logo from "../logo";
import { useRouter } from "next/navigation";

type TickerResult = {
  Ticker: string;
  name: string;
};

export default function HeaderSearchBar() {
  const [openMobileSearch, setOpenMobileSearch] = useState(false);
  return (
    <>
      <button
        type="button"
        className="sm:hidden mr-4 text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setOpenMobileSearch(true)}
      >
        <Search className="h-4 w-4" />
      </button>
      {openMobileSearch && (
        <div className="fixed inset-0 z-50 flex flex-col items-center bg-background/98 backdrop-blur-sm">
          <div className="pt-8">
            <Logo />
          </div>
          <div className="w-3/4 max-w-sm mt-[20vh]">
            <BaseSearchBar />
          </div>
          <button
            type="button"
            onClick={() => setOpenMobileSearch(false)}
            className="mt-auto mb-8 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
      <div className="hidden sm:block w-48 lg:w-56">
        <BaseSearchBar />
      </div>
    </>
  );
}

function SearchItem({ text, url }: { text: string; url: string }) {
  return (
    <li className="text-xxs px-3 py-1.5 hover:bg-accent transition-colors w-full min-w-0">
      <Link href={url} className="inline-block w-full truncate">
        {text}
      </Link>
    </li>
  );
}

function BaseSearchBar() {
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
    if (event.key === "Enter" && items.length > 0) {
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
    <div className="w-full min-w-0 relative">
      <input
        type="text"
        className={`w-full py-1.5 px-3 border border-border bg-background text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring transition-shadow ${
          hasResults ? "rounded-t-md rounded-b-sm" : "rounded"
        }`}
        placeholder="Search ticker..."
        value={searchQuery}
        spellCheck="false"
        autoCorrect="off"
        onChange={(event) => setSearchQuery(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {isLoading ? (
        <div className="py-4 justify-center flex">
          <Loading className="h-4 w-4" />
        </div>
      ) : hasResults ? (
        <ul className="absolute top-full mt-0.5 left-0 right-0 z-50 py-1 w-full min-w-0 max-h-64 overflow-auto rounded-b-md border border-border bg-background shadow-md scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border">
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
          <div className="absolute top-full mt-1 left-0 right-0 text-center text-xxs text-muted-foreground py-3 bg-background border border-border rounded">
            No results found
          </div>
        )
      )}
    </div>
  );
}
