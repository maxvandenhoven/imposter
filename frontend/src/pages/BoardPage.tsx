import { useState } from "react";

import { useCatalog } from "@/api/catalog";
import { useGameTrace } from "@/api/trace";
import type { CatalogModel } from "@/api/types";
import { BoardHeader, type BoardStatusLabel } from "@/components/board/BoardHeader";
import { GameTable } from "@/components/board/GameTable";
import { OutcomeBanner } from "@/components/board/OutcomeBanner";
import { PlaybackBar } from "@/components/board/PlaybackBar";
import { Transcript } from "@/components/board/Transcript";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useLeaveWarning } from "@/hooks/useLeaveWarning";
import { usePlaybackClock } from "@/hooks/usePlaybackClock";
import type { BoardState, BoardStatus } from "@/lib/board";
import { type BoardMode, buildBoardView, type ModelPrices } from "@/lib/boardView";
import type { GamePlayback } from "@/lib/playback";

const ENDED_LABELS: Record<Exclude<BoardStatus, "running">, BoardStatusLabel> = {
  finished: "Finished",
  aborted: "Aborted",
  failed: "Failed",
  stopped: "Stopped",
};

/**
 * The board of a game: the table with the seats, the transcript, the header and the
 * playback controls.
 *
 * The live board holds the stream's status and errors, and the playback decides how
 * much of the game is shown, at a pace the audience can follow.
 */
export function BoardPage({
  board,
  playback,
  onStop,
  onNewGame,
}: {
  board: BoardState;
  playback: GamePlayback;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const [mode, setMode] = useState<BoardMode>("god");
  const changePlayback = usePlaybackClock(playback);
  const streaming = board.status === "running";
  const catalog = useCatalog();
  const trace = useGameTrace(board.gameId, streaming);
  const models = new Map<string, CatalogModel>(
    catalog.data?.models.map((model) => [model.id, model]) ?? [],
  );
  const prices: ModelPrices = Object.fromEntries(
    [...models].map(([id, model]) => [id, model.price_per_mtok]),
  );
  const played = playback.board();
  const view = buildBoardView({
    events: played.events,
    answers: played.answers,
    mode,
    running: streaming || !playback.atLive,
    prices,
  });
  let status: BoardStatusLabel = playback.atLive ? "Live" : "Catching up";

  if (!streaming && playback.atLive) {
    status = ENDED_LABELS[board.status as Exclude<BoardStatus, "running">];
  }

  // Leaving the page closes the stream, which aborts the game.
  useLeaveWarning(streaming);

  return (
    <div className="flex flex-col gap-5 pb-24">
      <BoardHeader
        view={view}
        status={status}
        running={streaming}
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
          className="h-[36rem] gap-0 pb-0 xl:sticky xl:top-5 xl:h-[calc(100vh-10rem)]"
        />
      </div>
      <PlaybackBar playback={playback} onChange={changePlayback} />
    </div>
  );
}
