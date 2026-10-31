import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";

import { createQueryClient } from "@/api/queryClient";
import type { GameRequest } from "@/api/types";
import { AppLayout } from "@/components/AppLayout";
import { TooltipProvider } from "@/components/ui/tooltip";
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
              <SetupPage onStart={startGame} />
            ) : (
              <BoardPage board={run.board} onStop={run.stop} onNewGame={newGame} />
            )}
          </AppLayout>
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
