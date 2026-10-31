import { QueryClient } from "@tanstack/react-query";

/** Create the query client. The catalog does not change while the app runs. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, staleTime: Infinity } },
  });
}
