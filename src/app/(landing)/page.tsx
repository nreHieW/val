import SearchBar from "@/components/searchbar/search-bar";
import Link from "next/link";

export default function Home() {
  return (
    <main className="flex-1 flex items-start justify-center pt-24 sm:pt-28">
      <div className="flex flex-col w-full items-center gap-8">
        <h1 className="text-2xl sm:text-3xl font-light tracking-tight text-foreground/90">
          Value any company.
        </h1>
        <div className="w-full max-w-md min-w-0 px-4">
          <SearchBar />
        </div>
        <Link
          href="/about"
          className="text-xxs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
        >
          Learn more about val. →
        </Link>
      </div>
    </main>
  );
}
