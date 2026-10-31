import { cn } from "cn";
import { Brain } from "lucide-react";

/**
 * A seat's private reasoning, as a thought bubble that only god mode shows.
 *
 * With `clamp` set it shows the first four lines, for the seat cards.
 */
export function ThoughtBubble({
  text,
  live = false,
  clamp = false,
  className,
}: {
  text: string;
  live?: boolean;
  clamp?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("relative pl-4", className)}>
      <span
        aria-hidden
        className="absolute top-1 left-0.5 size-2 rounded-full border border-dashed border-thought-foreground/40 bg-thought"
      />
      <span
        aria-hidden
        className="absolute top-3.5 left-2 size-1.5 rounded-full border border-dashed border-thought-foreground/40 bg-thought"
      />
      <p
        data-testid="thought-bubble"
        data-clamp={clamp}
        className="rounded-2xl border border-dashed border-thought-foreground/35 bg-thought px-3 py-2 text-sm text-thought-foreground italic data-[clamp=true]:line-clamp-4"
      >
        <Brain
          aria-hidden
          className="mr-1.5 inline size-3.5 -translate-y-px not-italic"
        />
        {text}
        {live && <span className="ml-0.5 inline-block w-1.5 animate-pulse">▍</span>}
      </p>
    </div>
  );
}
