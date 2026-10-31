import { LayoutGroup } from "motion/react";
import { type CSSProperties, useLayoutEffect } from "react";

import type { CatalogModel } from "@/api/types";
import { SeatColumn } from "@/components/board/SeatColumn";
import { TableCenter } from "@/components/board/TableCenter";
import { VoteArrows } from "@/components/board/VoteArrows";
import { useElementRects } from "@/hooks/useElementRects";
import type { BoardView } from "@/lib/boardView";

/** The phases in which the votes are drawn as arrows across the table. */
const ARROW_PHASES = new Set(["vote", "resolution", "guess", "outcome"]);

/** The phases in which the arrows stay, faded behind the reflections. */
const FADED_ARROW_PHASES = new Set(["debrief", "done"]);

/** The key of the table card among the measured elements, next to the seats. */
const TABLE_KEY = -1;

/**
 * The table card across the top and the players in one row below it, in seat order.
 *
 * Each player has a column with its card, its answer and its reasoning. From the vote
 * to the outcome the votes are drawn as arrows between the players, bending towards the
 * table, and they stay faded during the debrief.
 */
export function GameTable({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  const { containerRef, elementRef, measured, measure } = useElementRects();
  const fadedArrows = FADED_ARROW_PHASES.has(view.phase ?? "");
  const showArrows =
    view.votes !== null && (ARROW_PHASES.has(view.phase ?? "") || fadedArrows);
  const table = measured.rects.get(TABLE_KEY);

  // Measure again when the arrows appear, since the cards may have moved since.
  useLayoutEffect(() => {
    if (showArrows) {
      measure();
    }
  }, [showArrows, measure, view.votes?.votes.length]);

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
      {showArrows && view.votes !== null && (
        <div
          data-faded={fadedArrows}
          className="pointer-events-none hidden transition-opacity duration-700 data-[faded=true]:opacity-25 lg:block"
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
        </div>
      )}
    </div>
  );
}
