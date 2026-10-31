import { useState } from "react";

import { useCatalog } from "@/api/catalog";
import { useGameTrace } from "@/api/trace";
import type { CatalogModel } from "@/api/types";
import { BoardHeader } from "@/components/board/BoardHeader";
import { GameTable } from "@/components/board/GameTable";
import { OutcomeBanner } from "@/components/board/OutcomeBanner";
import { Transcript } from "@/components/board/Transcript";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useLeaveWarning } from "@/hooks/useLeaveWarning";
import type { BoardState } from "@/lib/board";
import { type BoardMode, buildBoardView, type ModelPrices } from "@/lib/boardView";

/** The board of a game: the seats around the table, the transcript and the header. */
export function BoardPage({
  board,
  onStop,
  onNewGame,
}: {
  board: BoardState;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const [mode, setMode] = useState<BoardMode>("audience");
  const running = board.status === "running";
  const catalog = useCatalog();
  const trace = useGameTrace(board.gameId, running);
  const models = new Map<string, CatalogModel>(
    catalog.data?.models.map((model) => [model.id, model]) ?? [],
  );
  const prices: ModelPrices = Object.fromEntries(
    [...models].map(([id, model]) => [id, model.price_per_mtok]),
  );
  const view = buildBoardView({
    events: board.events,
    answers: board.answers,
    mode,
    running,
    prices,
  });
  // Leaving the page closes the stream, which aborts the game.
  useLeaveWarning(running);

  return (
    <div className="flex flex-col gap-5">
      <BoardHeader
        view={view}
        status={board.status}
        mode={mode}
        traceUrl={trace.data ?? null}
        onModeChange={setMode}
        onStop={onStop}
        onNewGame={onNewGame}
      />
      {board.errors.map((message, index) => (
        <Alert key={index} variant="destructive">
          <AlertTitle>The game failed</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">{message}</AlertDescription>
        </Alert>
      ))}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]">
        <div className="flex flex-col gap-5">
          {view.outcome !== null && <OutcomeBanner outcome={view.outcome} />}
          <GameTable view={view} models={models} />
        </div>
        <Transcript
          entries={view.transcript}
          seats={view.seats}
          models={models}
          className="h-[36rem] gap-0 pb-0 xl:sticky xl:top-5 xl:h-[calc(100vh-8.5rem)]"
        />
      </div>
    </div>
  );
}
