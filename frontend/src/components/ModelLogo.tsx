import { cn } from "cn";
import { Bot } from "lucide-react";

import type { CatalogModel } from "@/api/types";

/** The provider logo of a model, or a robot when the catalog names none. */
export function ModelLogo({
  model,
  className,
}: {
  model: CatalogModel | undefined;
  className?: string;
}) {
  if (model?.logo == null) {
    return <Bot aria-hidden className={cn("size-4 text-muted-foreground", className)} />;
  }

  return <img src={`/${model.logo}`} alt="" className={cn("size-4", className)} />;
}
