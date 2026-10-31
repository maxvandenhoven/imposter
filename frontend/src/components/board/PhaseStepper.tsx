import { cn } from "cn";
import { Check } from "lucide-react";
import { motion } from "motion/react";

import type { GamePhase } from "@/api/types";
import { STEP_ICONS } from "@/components/board/phaseIcons";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { PhaseStep } from "@/lib/table";

/**
 * The phases of the game as a row of steps joined by a line that fills as the game goes.
 *
 * Done steps show a check, the current step is a filled pill with its label, and the
 * steps still to come are quiet icons with their labels. A step whose phase has ended in
 * the game is a button that jumps to the end of that phase, through `onSeek` with the
 * number of events to show, so the phase can be discussed.
 */
export function PhaseStepper({
  steps,
  ends,
  onSeek,
}: {
  steps: PhaseStep[];
  ends: Partial<Record<GamePhase, number | null>>;
  onSeek: (events: number) => void;
}) {
  return (
    <ol className="flex items-center" aria-label="Phases">
      {steps.map((step, index) => {
        const Icon = step.state === "done" ? Check : (STEP_ICONS[step.phase] ?? Check);
        const end = ends[step.phase] ?? null;
        const content = (
          <>
            {step.state === "current" && (
              <motion.span
                layoutId="phase-pill"
                // Measured only when the phase changes, not on every render.
                layoutDependency={step.phase}
                className="absolute inset-0 rounded-full bg-primary shadow-md shadow-primary/30"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span
              className={cn(
                "relative flex size-5 items-center justify-center rounded-full",
                step.state === "done" && "bg-primary/12",
              )}
            >
              <Icon className="size-3.5" />
            </span>
            <span className="relative">{step.label}</span>
          </>
        );
        const className =
          "relative flex h-8 items-center gap-1.5 rounded-full px-2.5 text-sm font-medium whitespace-nowrap text-muted-foreground data-[state=current]:text-primary-foreground data-[state=done]:text-primary";

        return (
          <li key={step.phase} className="flex items-center">
            {index > 0 && (
              <span className="relative mx-1 h-0.5 w-4 overflow-hidden rounded-full bg-border xl:w-6">
                <motion.span
                  className="absolute inset-0 origin-left bg-primary"
                  initial={false}
                  animate={{ scaleX: step.state === "next" ? 0 : 1 }}
                  transition={{ duration: 0.5 }}
                />
              </span>
            )}
            {end === null ? (
              <span
                data-state={step.state}
                aria-current={step.state === "current" ? "step" : undefined}
                className={className}
              >
                {content}
              </span>
            ) : (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    data-state={step.state}
                    aria-current={step.state === "current" ? "step" : undefined}
                    className={cn(
                      className,
                      "cursor-pointer transition-colors outline-none hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-ring data-[state=current]:hover:bg-transparent",
                    )}
                    onClick={() => {
                      onSeek(end);
                    }}
                  >
                    {content}
                  </button>
                </TooltipTrigger>
                <TooltipContent>Go to the end of this phase</TooltipContent>
              </Tooltip>
            )}
          </li>
        );
      })}
    </ol>
  );
}
