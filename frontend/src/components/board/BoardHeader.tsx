import { Activity, Coins, Eye, RotateCcw, Square, Users } from "lucide-react";

import { PhaseStepper } from "@/components/board/PhaseStepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { BoardStatus } from "@/lib/board";
import type { BoardMode, BoardView } from "@/lib/boardView";
import { formatCost, formatTokens, phaseSteps } from "@/lib/table";

const STATUS_LABELS: Record<BoardStatus, string> = {
  running: "Live",
  finished: "Finished",
  aborted: "Aborted",
  failed: "Failed",
  stopped: "Stopped",
};

/**
 * The bar above the board: the status and phases, the tokens and cost so far, the trace
 * link, the audience or god mode toggle and the game controls.
 */
export function BoardHeader({
  view,
  status,
  mode,
  traceUrl,
  onModeChange,
  onStop,
  onNewGame,
}: {
  view: BoardView;
  status: BoardStatus;
  mode: BoardMode;
  traceUrl: string | null;
  onModeChange: (mode: BoardMode) => void;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const running = status === "running";

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border bg-card/80 px-4 py-2.5 shadow-xs backdrop-blur">
      <Badge
        variant={running ? "default" : "secondary"}
        className="h-6 gap-1.5 px-2.5"
        data-status={status}
      >
        {running && (
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full rounded-full bg-primary-foreground opacity-75 motion-safe:animate-ping" />
            <span className="relative inline-flex size-2 rounded-full bg-primary-foreground" />
          </span>
        )}
        {STATUS_LABELS[status]}
      </Badge>
      <PhaseStepper steps={phaseSteps(view.phase, view.finished)} />
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex items-center gap-3 rounded-full bg-muted px-3 py-1 text-sm tabular-nums">
              <span className="flex items-center gap-1">
                <Coins className="size-3.5 text-speaking" />
                {formatCost(view.usage.costUsd)}
              </span>
              <span className="text-muted-foreground">
                {formatTokens(view.usage.tokens)} tokens
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            Estimated from the catalog prices of the models.
          </TooltipContent>
        </Tooltip>
        {traceUrl !== null && (
          <Button variant="outline" size="sm" asChild>
            <a href={traceUrl} target="_blank" rel="noreferrer">
              <Activity data-icon="inline-start" />
              Trace
            </a>
          </Button>
        )}
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          aria-label="Mode"
          value={mode}
          onValueChange={(value) => {
            // A click on the pressed item clears the value, which keeps the mode.
            if (value !== "") {
              onModeChange(value as BoardMode);
            }
          }}
        >
          <ToggleGroupItem value="audience">
            <Users />
            Audience
          </ToggleGroupItem>
          <ToggleGroupItem value="god">
            <Eye />
            God mode
          </ToggleGroupItem>
        </ToggleGroup>
        {running ? (
          <Button variant="destructive" size="sm" onClick={onStop}>
            <Square data-icon="inline-start" />
            Stop
          </Button>
        ) : (
          <Button size="sm" onClick={onNewGame}>
            <RotateCcw data-icon="inline-start" />
            New game
          </Button>
        )}
      </div>
    </div>
  );
}
