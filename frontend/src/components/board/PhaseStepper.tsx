import { cn } from "cn";
import {
  Check,
  HelpCircle,
  Lightbulb,
  type LucideIcon,
  MessagesSquare,
  NotebookPen,
  Trophy,
  Vote,
} from "lucide-react";
import { motion } from "motion/react";

import type { GamePhase } from "@/api/types";
import type { PhaseStep } from "@/lib/table";

const STEP_ICONS: Partial<Record<GamePhase, LucideIcon>> = {
  clue: Lightbulb,
  discussion: MessagesSquare,
  vote: Vote,
  guess: HelpCircle,
  outcome: Trophy,
  debrief: NotebookPen,
};

/**
 * The phases of the game as a row of steps joined by a line that fills as the game goes.
 *
 * Done steps show a check, the current step is a filled pill with its label, and the
 * steps still to come are quiet icons with their labels.
 */
export function PhaseStepper({ steps }: { steps: PhaseStep[] }) {
  return (
    <ol className="flex items-center" aria-label="Phases">
      {steps.map((step, index) => {
        const Icon = step.state === "done" ? Check : (STEP_ICONS[step.phase] ?? Check);

        return (
          <li key={step.phase} className="flex items-center">
            {index > 0 && (
              <span className="relative mx-1 h-0.5 w-5 overflow-hidden rounded-full bg-border xl:w-8">
                <motion.span
                  className="absolute inset-0 origin-left bg-primary"
                  initial={false}
                  animate={{ scaleX: step.state === "next" ? 0 : 1 }}
                  transition={{ duration: 0.5 }}
                />
              </span>
            )}
            <span
              data-state={step.state}
              aria-current={step.state === "current" ? "step" : undefined}
              className="relative flex h-8 items-center gap-1.5 rounded-full px-2.5 text-sm font-medium text-muted-foreground data-[state=current]:text-primary-foreground data-[state=done]:text-primary"
            >
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
            </span>
          </li>
        );
      })}
    </ol>
  );
}
