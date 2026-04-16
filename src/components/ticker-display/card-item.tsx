import { ReactNode } from "react";
import InfoHover from "../info-hover";

const CardItem = async ({
  children,
  footerChildren,
  title,
  tooltip,
}: {
  children: ReactNode;
  footerChildren?: ReactNode;
  title: string;
  tooltip?: string;
}) => {
  return (
    <div className="h-full flex flex-col rounded-lg border border-border/50 px-4 py-4 sm:px-5 sm:py-5">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="text-xs font-medium tracking-tight">{title}</h3>
        <InfoHover text={tooltip || ""} />
      </div>
      <div className="text-sm">{children}</div>
      {footerChildren && (
        <div className="mt-auto pt-4 text-xxs text-muted-foreground/60">
          {footerChildren}
        </div>
      )}
    </div>
  );
};

export default CardItem;
