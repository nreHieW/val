import type { Metadata } from "next";
import MainHeader from "@/components/main-header";

export const metadata: Metadata = {
  title: "val: value any company",
  description: "Create a discounted cash flow valuation for any company",
};

export default function Layout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex flex-col h-svh">
      <MainHeader />
      {children}
    </div>
  );
}
