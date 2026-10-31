import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";

import { createQueryClient } from "@/api/queryClient";
import type { GameEvent, GameRequest } from "@/api/types";
import { AppLayout } from "@/components/AppLayout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { buildGameExport, downloadJson, exportFileName } from "@/lib/gameExport";
import { useGameRun } from "@/hooks/useGameRun";
import { BoardPage } from "@/pages/BoardPage";
import { SetupPage } from "@/pages/SetupPage";

const queryClient = createQueryClient();

/** The app: the setup view until a game starts, then the board of that game. */
export function App() {
  const [request, setRequest] = useState<GameRequest | null>(null);
  const run = useGameRun();

  const startGame = (gameRequest: GameRequest) => {
    setRequest(gameRequest);
    run.start(gameRequest);
  };

  const importGame = (imported: { config: GameRequest; events: GameEvent[] }) => {
    setRequest(imported.config);
    run.load(imported.events);
  };

  const exportGame = () => {
    if (request !== null) {
      const events = run.board.events;
      const text = JSON.stringify(buildGameExport({ config: request, events }), null, 2);
      downloadJson({ name: exportFileName(events), text });
    }
  };

  const newGame = () => {
    run.stop();
    setRequest(null);
  };

  return (
    <QueryClientProvider client={queryClient}>
      {/* Animations follow the reduced motion setting of the system. */}
      <MotionConfig reducedMotion="user">
        <TooltipProvider delayDuration={200}>
          <AppLayout wide={request !== null}>
            {request === null ? (
              <SetupPage onStart={startGame} onImport={importGame} />
            ) : (
              <BoardPage
                board={run.board}
                playback={run.playback}
                onExport={exportGame}
                onStop={run.stop}
                onNewGame={newGame}
              />
            )}
          </AppLayout>
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
