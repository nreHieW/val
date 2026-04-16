import React from "react";

export default function DisclaimerPage() {
  return (
    <main className="pb-12 sm:pb-16">
      <section className="mx-auto mt-16 sm:mt-20 max-w-[72ch] text-center">
        <h1 className="text-base font-medium tracking-tight text-foreground">
          Disclaimer
        </h1>
        <p className="mt-6 text-xs leading-6 text-muted-foreground text-balance">
          Nothing on this site is, or should be taken as, financial advice. Val is
          built for educational purposes. While Val aims to keep information accurate
          and current, completeness and timeliness cannot be guaranteed. Always do your
          own research and consult a qualified professional before making financial
          decisions.
        </p>
      </section>
    </main>
  );
}
