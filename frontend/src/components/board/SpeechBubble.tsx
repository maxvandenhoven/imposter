import { cn } from "cn";
import type { ReactNode } from "react";

/** Where the tail of a speech bubble points: at the speaker above, beside or below it. */
export type BubbleTail = "top" | "left" | "bottom";

/**
 * The tails as SVG paths: the fill in the bubble's colour, which covers the bubble's
 * border where the tail joins it, and the outline along the two sides of the tail.
 */
const TAILS: Record<
  BubbleTail,
  { className: string; width: number; height: number; fill: string; stroke: string }
> = {
  top: {
    className: "-top-[9px] left-1/2 -translate-x-1/2",
    width: 16,
    height: 9,
    fill: "M0 9.5 L8 1 L16 9.5 Z",
    stroke: "M0 8.5 L8 1 L16 8.5",
  },
  bottom: {
    className: "-bottom-[9px] left-1/2 -translate-x-1/2",
    width: 16,
    height: 9,
    fill: "M0 -0.5 L8 8 L16 -0.5 Z",
    stroke: "M0 0.5 L8 8 L16 0.5",
  },
  left: {
    className: "top-3 -left-[9px]",
    width: 9,
    height: 16,
    fill: "M9.5 0 L1 8 L9.5 16 Z",
    stroke: "M8.5 0 L1 8 L8.5 16",
  },
};

/** The tail of a speech bubble, in the colours of the bubble it is part of. */
function BubbleTailMark({ tail }: { tail: BubbleTail }) {
  const { className, width, height, fill, stroke } = TAILS[tail];

  return (
    <svg
      aria-hidden
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("pointer-events-none absolute overflow-visible", className)}
    >
      <path d={fill} fill="var(--bubble-bg)" />
      <path
        d={stroke}
        fill="none"
        stroke="var(--bubble-border)"
        strokeWidth={1}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * A public answer as a speech bubble. With `tail` set, a small tail points up to the
 * speaker above it, left to the speaker beside it or down to the speaker below it. The
 * tail is drawn in the bubble's own colours, so it joins the outline without a seam.
 * `tone` colours the outline of an answer that follows (`good`) or breaks (`bad`) the
 * rules.
 */
export function SpeechBubble({
  children,
  live = false,
  muted = false,
  tail = null,
  tone = null,
  className,
}: {
  children: ReactNode;
  live?: boolean;
  muted?: boolean;
  tail?: BubbleTail | null;
  tone?: "good" | "bad" | null;
  className?: string;
}) {
  return (
    <div
      data-live={live}
      data-muted={muted}
      data-tone={tone}
      className={cn(
        "relative rounded-2xl border border-(--bubble-border) bg-(--bubble-bg) px-3 py-2 text-[0.95rem] leading-snug shadow-xs [--bubble-bg:var(--card)] [--bubble-border:var(--border)]",
        "data-[live=true]:[--bubble-bg:color-mix(in_srgb,var(--speaking)_6%,var(--card))] data-[live=true]:[--bubble-border:color-mix(in_srgb,var(--speaking)_60%,transparent)]",
        "data-[muted=true]:[--bubble-bg:color-mix(in_srgb,var(--muted)_60%,transparent)]",
        "data-[tone=bad]:[--bubble-border:color-mix(in_srgb,var(--destructive)_60%,transparent)] data-[tone=good]:[--bubble-border:color-mix(in_srgb,var(--civilian)_60%,transparent)]",
        className,
      )}
    >
      {tail !== null && <BubbleTailMark tail={tail} />}
      <span className="relative">
        {children}
        {live && (
          <span className="ml-0.5 inline-block w-1.5 animate-pulse text-speaking">▍</span>
        )}
      </span>
    </div>
  );
}
