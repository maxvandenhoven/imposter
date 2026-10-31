import { useState } from "react";

import { useCatalog } from "@/api/catalog";
import { useGameTrace } from "@/api/trace";
import type { CatalogModel } from "@/api/types";
import { BoardHeader, type BoardStatusLabel } from "@/components/board/BoardHeader";
import { DebriefPanel } from "@/components/board/DebriefPanel";
import { GameTable } from "@/components/board/GameTable";
import { OutcomeBanner } from "@/components/board/OutcomeBanner";
import { PlaybackBar } from "@/components/board/PlaybackBar";
import { Transcript } from "@/components/board/Transcript";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useLeaveWarning } from "@/hooks/useLeaveWarning";
import { usePlaybackClock } from "@/hooks/usePlaybackClock";
import { usePlaybackKeys } from "@/hooks/usePlaybackKeys";
import type { BoardState, BoardStatus } from "@/lib/board";
import { type BoardMode, buildBoardView, type ModelPrices } from "@/lib/boardView";
import { buildDebrief } from "@/lib/debrief";
import type { GamePlayback } from "@/lib/playback";
import { PHASE_STEPS, phaseEnd, phaseSteps } from "@/lib/table";

const ENDED_LABELS: Record<Exclude<BoardStatus, "running">, BoardStatusLabel> = {
  finished: "Finished",
  aborted: "Aborted",
  failed: "Failed",
  stopped: "Stopped",
};

/**
 * The board of a game: the table with the seats, the transcript, the header, the debrief
 * once the game is over and the playback controls.
 *
 * The live board holds the stream's status and errors, and the playback decides how
 * much of the game is shown, at a pace the audience can follow.
 */
export function BoardPage({
  board,
  playback,
  onExport,
  onStop,
  onNewGame,
}: {
  board: BoardState;
  playback: GamePlayback;
  onExport: () => void;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const [mode, setMode] = useState<BoardMode>("god");
  const changePlayback = usePlaybackClock(playback);
  usePlaybackKeys(playback, changePlayback);
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
  // A phase that has ended in the game can be jumped to, also while replaying before it.
  const phaseEnds = Object.fromEntries(
    PHASE_STEPS.map(({ phase }) => [phase, phaseEnd(playback.timeline.events, phase)]),
  );
  let status: BoardStatusLabel = playback.atLive ? "Live" : "Catching up";

  if (!streaming) {
    status = playback.atLive
      ? ENDED_LABELS[board.status as Exclude<BoardStatus, "running">]
      : "Replay";
  }

  // Leaving the page closes the stream, which aborts the game.
  useLeaveWarning(streaming);

  return (
    <div className="flex flex-col gap-5 pb-24">
      <BoardHeader
        view={view}
        steps={phaseSteps(view.phase, view.finished)}
        phaseEnds={phaseEnds}
        status={status}
        running={streaming}
        mode={mode}
        traceUrl={trace.data ?? null}
        onModeChange={setMode}
        onSeek={(events) => {
          changePlayback((current) => {
            current.seek(events);
          });
        }}
        onExport={onExport}
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
      {view.finished && (
        <DebriefPanel
          seats={buildDebrief({ events: played.events, prices })}
          models={models}
        />
      )}
      <PlaybackBar playback={playback} onChange={changePlayback} />
    </div>
  );
}
