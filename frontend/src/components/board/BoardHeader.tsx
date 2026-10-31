import {
  Activity,
  Coins,
  Download,
  Eye,
  RotateCcw,
  SlidersHorizontal,
  Square,
} from "lucide-react";

import type { GamePhase } from "@/api/types";
import { PhaseStepper } from "@/components/board/PhaseStepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { BoardMode, BoardView } from "@/lib/boardView";
import { formatCost, formatTokens, type PhaseStep } from "@/lib/table";

/** How the game looks from the board: live, replaying a backlog, or how it ended. */
export type BoardStatusLabel =
  "Live" | "Catching up" | "Replay" | "Finished" | "Aborted" | "Failed" | "Stopped";

/** The view settings behind a button: whether the board shows what is hidden. */
function ViewSettings({
  mode,
  onModeChange,
}: {
  mode: BoardMode;
  onModeChange: (mode: BoardMode) => void;
}) {
  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="outline" size="icon-sm" aria-label="View settings">
              <SlidersHorizontal />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>View settings</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-72">
        <div className="flex items-start gap-3">
          <Eye className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div className="flex flex-1 flex-col gap-1">
            <Label htmlFor="show-hidden">Show hidden info</Label>
            <p className="text-xs text-muted-foreground">
              Show the secret word, the roles, the secret votes and the private reasoning
              while the game runs.
            </p>
          </div>
          <Switch
            id="show-hidden"
            checked={mode === "god"}
            onCheckedChange={(checked) => {
              onModeChange(checked ? "god" : "audience");
            }}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * The dark bar across the top of the board: the status and cost on the left, the phases
 * in the middle,
 * and the trace link, the export, the view settings and the game controls on the right.
 */
export function BoardHeader({
  view,
  steps,
  phaseEnds,
  status,
  running,
  mode,
  traceUrl,
  onModeChange,
  onSeek,
  onExport,
  onStop,
  onNewGame,
}: {
  view: BoardView;
  steps: PhaseStep[];
  phaseEnds: Partial<Record<GamePhase, number | null>>;
  status: BoardStatusLabel;
  running: boolean;
  mode: BoardMode;
  traceUrl: string | null;
  onModeChange: (mode: BoardMode) => void;
  onSeek: (events: number) => void;
  onExport: () => void;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const active = status === "Live" || status === "Catching up";

  return (
    <header className="night border-b bg-background text-foreground shadow-md">
      <div className="mx-auto grid max-w-[120rem] items-center gap-x-4 gap-y-3 px-4 py-2.5 sm:px-8 xl:grid-cols-[minmax(max-content,1fr)_auto_minmax(max-content,1fr)]">
        <div className="flex flex-wrap items-center gap-3">
          <img src="/favicon.svg" alt="Imposter" className="size-7" />
          <Badge
            variant={active ? "default" : "secondary"}
            className="h-6 gap-1.5 px-2.5"
          >
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
          <PhaseStepper steps={steps} ends={phaseEnds} onSeek={onSeek} />
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2">
          {traceUrl !== null && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon-sm" asChild>
                  <a href={traceUrl} target="_blank" rel="noreferrer" aria-label="Trace">
                    <Activity />
                  </a>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Open the trace of the game in Cloud Trace.</TooltipContent>
            </Tooltip>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Export"
                onClick={onExport}
              >
                <Download />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Download the game as JSON. It holds the secrets of the game.
            </TooltipContent>
          </Tooltip>
          <ViewSettings mode={mode} onModeChange={onModeChange} />
          {running ? (
            <Button variant="destructive" size="sm" onClick={onStop}>
              <Square data-icon="inline-start" />
              Stop
            </Button>
          ) : (
            <Button size="sm" className="whitespace-nowrap" onClick={onNewGame}>
              <RotateCcw data-icon="inline-start" />
              New game
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
