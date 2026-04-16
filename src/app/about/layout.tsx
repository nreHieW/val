import type { Metadata } from "next";
import "../globals.css";
import MainHeader from "@/components/main-header";
import HeaderSearchBar from "@/components/searchbar/header-search-bar";

export const metadata: Metadata = {
  title: "val: value any company",
  description: "Create any company valuation",
};

export default function Layout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex flex-col">
      <MainHeader>
        <HeaderSearchBar />
      </MainHeader>
      {children}
    </div>
  );
}
