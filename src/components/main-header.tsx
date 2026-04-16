import Logo from "./logo";
import { ModeToggle } from "./mode-toggle";

export default function MainHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="flex items-center justify-between py-6 sm:py-8">
      <Logo />
      <div className="flex items-center gap-3">
        {children}
        <ModeToggle />
      </div>
    </header>
  );
}
