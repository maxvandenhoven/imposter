import { cn } from "cn";
import type { ReactNode } from "react";

/**
 * A public answer as a speech bubble. With `tail` set, a small tail points up to the
 * speaker above it or left to the speaker beside it.
 */
export function SpeechBubble({
  children,
  live = false,
  muted = false,
  tail = null,
  className,
}: {
  children: ReactNode;
  live?: boolean;
  muted?: boolean;
  tail?: "top" | "left" | null;
  className?: string;
}) {
  return (
    <div
      data-live={live}
      data-muted={muted}
      data-tail={tail}
      className={cn(
        "group/bubble relative rounded-2xl border bg-card px-3 py-2 text-[0.95rem] leading-snug shadow-xs data-[live=true]:border-speaking/60 data-[live=true]:bg-[color-mix(in_srgb,var(--speaking)_6%,var(--card))] data-[muted=true]:bg-muted/60",
        className,
      )}
    >
      {tail !== null && (
        <span
          aria-hidden
          className="absolute size-3 rotate-45 border-t border-l bg-inherit group-data-[live=true]/bubble:border-speaking/60 group-data-[tail=left]/bubble:top-3 group-data-[tail=left]/bubble:-left-1.5 group-data-[tail=left]/bubble:-rotate-45 group-data-[tail=top]/bubble:-top-1.5 group-data-[tail=top]/bubble:left-1/2 group-data-[tail=top]/bubble:-translate-x-1/2"
        />
      )}
      <span className="relative">
        {children}
        {live && (
          <span className="ml-0.5 inline-block w-1.5 animate-pulse text-speaking">▍</span>
        )}
      </span>
    </div>
  );
}
