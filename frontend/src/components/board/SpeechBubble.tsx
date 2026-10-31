import { cn } from "cn";
import type { ReactNode } from "react";

/** A public statement, guess or reflection, as a speech bubble. */
export function SpeechBubble({
  children,
  live = false,
  muted = false,
  className,
}: {
  children: ReactNode;
  live?: boolean;
  muted?: boolean;
  className?: string;
}) {
  return (
    <div
      data-live={live}
      data-muted={muted}
      className={cn(
        "relative rounded-2xl rounded-tl-sm border bg-card px-3 py-2 text-[0.95rem] leading-snug shadow-xs data-[live=true]:border-speaking/60 data-[live=true]:bg-speaking/6 data-[muted=true]:bg-muted/60",
        className,
      )}
    >
      {children}
      {live && (
        <span className="ml-0.5 inline-block w-1.5 animate-pulse text-speaking">▍</span>
      )}
    </div>
  );
}
