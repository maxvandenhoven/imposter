import { useQuery } from "@tanstack/react-query";

import { requestJson } from "@/api/http";
import type { CatalogResponse } from "@/api/types";

/** The models, word categories and default lineup that the setup screen offers. */
export function useCatalog() {
  return useQuery({
    queryKey: ["catalog"],
    queryFn: ({ signal }) => requestJson<CatalogResponse>("/catalog", { signal }),
  });
}
