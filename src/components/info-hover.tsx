import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Info } from "lucide-react";

export default function InfoHover({ text }: { text: string }) {
  return (
    <HoverCard>
      <HoverCardTrigger className="hidden sm:inline-flex text-muted-foreground/30 hover:text-muted-foreground/50 transition-colors">
        <Info className="h-3.5 w-3.5" />
      </HoverCardTrigger>
      <HoverCardContent>
        <p className="text-xxs leading-relaxed text-muted-foreground/60">{text}</p>
      </HoverCardContent>
    </HoverCard>
  );
}
