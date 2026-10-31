import { useQuery } from "@tanstack/react-query";

import { requestJson } from "@/api/http";

/** The trace link of a game, as `/traces/{game_id}` returns it. */
interface GameTraceResponse {
  url: string | null;
}

/** How often to ask again while the run has not noted its trace yet. */
const RETRY_MILLISECONDS = 3000;

/**
 * The link to a game's trace in Cloud Trace, once its run started.
 *
 * Asks again until a link arrives while `running` is set, since the trace is only known
 * once the run starts. The link is `null` when traces stay local.
 */
export function useGameTrace(gameId: string | null, running: boolean) {
  return useQuery({
    queryKey: ["trace", gameId],
    enabled: gameId !== null,
    queryFn: ({ signal }) =>
      requestJson<GameTraceResponse>(`/traces/${gameId ?? ""}`, { signal }),
    select: (response) => response.url,
    refetchInterval: (query) =>
      running && query.state.data?.url == null ? RETRY_MILLISECONDS : false,
    staleTime: Infinity,
  });
}
