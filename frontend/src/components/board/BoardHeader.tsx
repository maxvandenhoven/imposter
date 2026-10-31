import { Activity, Coins, Eye, RotateCcw, Square } from "lucide-react";

import { PhaseStepper } from "@/components/board/PhaseStepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { BoardMode, BoardView } from "@/lib/boardView";
import { formatCost, formatTokens, phaseSteps } from "@/lib/table";

/** How the game looks from the board: live, replaying a backlog, or how it ended. */
export type BoardStatusLabel =
  "Live" | "Catching up" | "Finished" | "Aborted" | "Failed" | "Stopped";

/**
 * The bar above the board: the status and cost on the left, the phases in the middle,
 * and the trace link, the god mode switch and the game controls on the right.
 */
export function BoardHeader({
  view,
  status,
  running,
  mode,
  traceUrl,
  onModeChange,
  onStop,
  onNewGame,
}: {
  view: BoardView;
  status: BoardStatusLabel;
  running: boolean;
  mode: BoardMode;
  traceUrl: string | null;
  onModeChange: (mode: BoardMode) => void;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const active = status === "Live" || status === "Catching up";

  return (
    <div className="grid items-center gap-x-4 gap-y-3 rounded-2xl border bg-card/80 px-4 py-2.5 shadow-xs backdrop-blur xl:grid-cols-[1fr_auto_1fr]">
      <div className="flex flex-wrap items-center gap-3">
        <img src="/favicon.svg" alt="Imposter" className="size-7" />
        <Badge variant={active ? "default" : "secondary"} className="h-6 gap-1.5 px-2.5">
          {active && (
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full rounded-full bg-primary-foreground opacity-75 motion-safe:animate-ping" />
              <span className="relative inline-flex size-2 rounded-full bg-primary-foreground" />
            </span>
          )}
          {status}
        </Badge>
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
      </div>
      <div className="flex justify-center overflow-x-auto">
        <PhaseStepper steps={phaseSteps(view.phase, view.finished)} />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-3">
        {traceUrl !== null && (
          <Button variant="outline" size="sm" asChild>
            <a href={traceUrl} target="_blank" rel="noreferrer">
              <Activity data-icon="inline-start" />
              Trace
            </a>
          </Button>
        )}
        <div className="flex items-center gap-2 rounded-full bg-muted px-3 py-1">
          <Eye className="size-4 text-muted-foreground" />
          <Label htmlFor="god-mode" className="text-sm">
            God mode
          </Label>
          <Switch
            id="god-mode"
            checked={mode === "god"}
            onCheckedChange={(checked) => {
              onModeChange(checked ? "god" : "audience");
            }}
          />
        </div>
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
