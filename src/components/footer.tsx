import Link from "next/link";

export default function Footer() {
  return (
    <footer className="mt-auto border-t border-border pt-4 pb-6 flex items-center justify-between text-xxs text-muted-foreground/60">
      <Link href="/disclaimer" className="hover:text-muted-foreground transition-colors">
        Disclaimer
      </Link>
      <Link href="/about" className="hover:text-muted-foreground transition-colors">
        About val.
      </Link>
      <span>&copy; {new Date().getFullYear()}</span>
    </footer>
  );
}
