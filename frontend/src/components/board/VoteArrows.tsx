import { motion } from "motion/react";

import type { VoteView } from "@/lib/boardView";
import { type BoardRect, voteArrow } from "@/lib/table";

/** How long one arrow takes to draw, and the pause before the next one starts. */
const DRAW_SECONDS = 0.55;
const STAGGER_SECONDS = 0.45;

/**
 * The votes as curved arrows between the seat cards, drawn one after another.
 *
 * Secret votes in god mode are dashed, revealed votes solid. Arrows to a caught seat
 * take the imposter colour.
 */
export function VoteArrows({
  votes,
  rects,
  revealed,
  caught,
  width,
  height,
}: {
  votes: VoteView[];
  rects: Map<number, BoardRect>;
  revealed: boolean;
  caught: number[];
  width: number;
  height: number;
}) {
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 z-20 overflow-visible"
      width={width}
      height={height}
    >
      {votes.map((vote, index) => {
        const from = rects.get(vote.voter);
        const to = vote.target === null ? undefined : rects.get(vote.target);

        if (from === undefined || to === undefined) {
          return null;
        }

        const arrow = voteArrow({ from, to });
        const delay = index * STAGGER_SECONDS;
        const isCaught = vote.target !== null && caught.includes(vote.target);
        const colour = isCaught ? "var(--imposter)" : "var(--primary)";

        return (
          <g key={`${vote.voter}-${vote.target}`}>
            <motion.path
              d={arrow.path}
              fill="none"
              stroke={colour}
              strokeWidth={3}
              strokeLinecap="round"
              strokeDasharray={revealed ? undefined : "6 7"}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: revealed ? 0.85 : 0.55 }}
              transition={{ duration: DRAW_SECONDS, delay, ease: "easeInOut" }}
            />
            <motion.polygon
              points="-11,-7 3,0 -11,7"
              fill={colour}
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: revealed ? 0.95 : 0.6, scale: 1 }}
              transition={{ delay: delay + DRAW_SECONDS * 0.9, duration: 0.15 }}
              style={{
                x: arrow.tip.x,
                y: arrow.tip.y,
                rotate: arrow.tip.angle,
              }}
            />
          </g>
        );
      })}
    </svg>
  );
}
