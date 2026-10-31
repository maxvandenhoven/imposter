import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import type { CSSProperties } from "react";

import type { CatalogModel } from "@/api/types";
import { SeatColumn } from "@/components/board/SeatColumn";
import { TableCenter } from "@/components/board/TableCenter";
import { VoteArrows } from "@/components/board/VoteArrows";
import { useElementRects } from "@/hooks/useElementRects";
import type { BoardView } from "@/lib/boardView";

/** The phases in which the votes are drawn as arrows across the table. */
const ARROW_PHASES = new Set(["vote", "resolution", "guess", "outcome"]);

/** The key of the table card among the measured elements, next to the seats. */
const TABLE_KEY = -1;

/**
 * The table card across the top and the players in one row below it, in seat order.
 *
 * Each player has a column with its card, its answer and its reasoning. From the vote
 * to the outcome the votes are drawn as arrows between the players, bending towards the
 * table, and they fade out when the debrief starts.
 */
export function GameTable({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  const showArrows = view.votes !== null && ARROW_PHASES.has(view.phase ?? "");
  // Measuring renders again on every resize, so it only runs while the arrows show.
  const { containerRef, elementRef, measured } = useElementRects(showArrows);
  const table = measured.rects.get(TABLE_KEY);

  return (
    <div ref={containerRef} className="relative flex flex-col gap-6">
      {/* One group, so a bubble can move from the table to its seat's column. */}
      <LayoutGroup>
        <div ref={elementRef(TABLE_KEY)}>
          <TableCenter view={view} models={models} />
        </div>
        <div
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:[grid-template-columns:repeat(var(--seats),minmax(0,1fr))]"
          style={{ "--seats": view.seats.length } as CSSProperties}
        >
          {view.seats.map((seat) => (
            <SeatColumn
              key={seat.seat}
              ref={elementRef(seat.seat)}
              seat={seat}
              model={models.get(seat.modelId ?? "")}
              onStage={view.stage?.seat === seat.seat}
            />
          ))}
        </div>
      </LayoutGroup>
      <AnimatePresence>
        {showArrows && view.votes !== null && (
          <motion.div
            key="arrows"
            className="pointer-events-none hidden lg:block"
            exit={{ opacity: 0, transition: { duration: 1 } }}
          >
            <VoteArrows
              votes={view.votes.votes}
              rects={measured.rects}
              towards={
                table === undefined
                  ? undefined
                  : { x: table.x + table.width / 2, y: table.y + table.height / 2 }
              }
              revealed={view.votes.revealed}
              caught={view.votes.caught}
              width={measured.width}
              height={measured.height}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
