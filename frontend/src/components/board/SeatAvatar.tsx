import { cn } from "cn";

import type { CatalogModel } from "@/api/types";
import { ModelLogo } from "@/components/ModelLogo";
import { Avatar } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SeatRole } from "@/lib/boardView";

/** A seat's avatar: the logo of its model on a disc, ringed in its role's colour. */
export function SeatAvatar({
  model,
  role,
  size = "default",
  className,
}: {
  model: CatalogModel | undefined;
  role: SeatRole | null;
  size?: "sm" | "default" | "lg";
  className?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Avatar
          size={size}
          data-role={role ?? "unknown"}
          className={cn(
            "items-center justify-center bg-card shadow-sm ring-2 ring-border ring-offset-2 ring-offset-card data-[role=civilian]:ring-civilian data-[role=imposter]:ring-imposter",
            size === "lg" && "size-12",
            className,
          )}
        >
          <ModelLogo
            model={model}
            className={cn(
              size === "sm" ? "size-3.5" : size === "lg" ? "size-7" : "size-5",
            )}
          />
        </Avatar>
      </TooltipTrigger>
      <TooltipContent>{model?.display_name ?? "Unknown model"}</TooltipContent>
    </Tooltip>
  );
}
