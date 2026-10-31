import { Bot } from "lucide-react";

import type { CatalogModel } from "@/api/types";

/** The provider logo of a model, or a robot when the catalog names none. */
export function ModelLogo({ model }: { model: CatalogModel | undefined }) {
  if (model?.logo == null) {
    return <Bot aria-hidden className="size-4 text-muted-foreground" />;
  }

  return <img src={`/${model.logo}`} alt="" className="size-4" />;
}
