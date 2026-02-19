import SearchBar from "@/components/searchbar/search-bar";
import { Poppins } from "next/font/google";
import Link from "next/link";

const poppins = Poppins({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-poppins",
  weight: ["100", "200", "300", "400", "500", "600", "700", "800", "900"],
});

export default function Home() {
  return (
    <main className="h-2/3 grid">
      <div className="flex flex-col w-full items-center">
        <div className={`${poppins.className} align-text-bottom pt-12 text-xl`}>
          Value any company.
        </div>
        <div className="w-3/5 min-w-0 pt-6">
          <SearchBar />
        </div>
        <div className="text-xs underline mt-12" style={{ opacity: "50%" }}>
          <Link href="/about">Learn more about val. →</Link>
        </div>
      </div>
    </main>
  );
}
