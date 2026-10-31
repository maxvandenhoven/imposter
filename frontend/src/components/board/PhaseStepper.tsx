import { Check } from "lucide-react";
import { motion } from "motion/react";

import type { PhaseStep } from "@/lib/table";

/** The phases of the game as steps, with the current one highlighted. */
export function PhaseStepper({ steps }: { steps: PhaseStep[] }) {
  return (
    <ol className="flex items-center gap-1" aria-label="Phases">
      {steps.map((step, index) => (
        <li key={step.phase} className="flex items-center gap-1">
          {index > 0 && (
            <span
              data-state={step.state}
              className="h-px w-3 bg-border data-[state=current]:bg-primary data-[state=done]:bg-primary xl:w-5"
            />
          )}
          <span
            data-state={step.state}
            aria-current={step.state === "current" ? "step" : undefined}
            className="relative flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium text-muted-foreground data-[state=current]:text-primary-foreground data-[state=done]:text-primary"
          >
            {step.state === "current" && (
              <motion.span
                layoutId="phase-pill"
                className="absolute inset-0 rounded-full bg-primary shadow-sm"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span className="relative flex items-center gap-1">
              {step.state === "done" && <Check className="size-3" />}
              {step.label}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}
