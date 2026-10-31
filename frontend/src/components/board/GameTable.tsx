import { type CSSProperties, useLayoutEffect } from "react";

import type { CatalogModel } from "@/api/types";
import { SeatCard } from "@/components/board/SeatCard";
import { TableCenter } from "@/components/board/TableCenter";
import { VoteArrows } from "@/components/board/VoteArrows";
import { useElementRects } from "@/hooks/useElementRects";
import type { BoardView } from "@/lib/boardView";
import { seatCells } from "@/lib/table";

/** The phases in which the votes are drawn as arrows across the table. */
const ARROW_PHASES = new Set(["vote", "resolution", "guess", "outcome"]);

/** The phases in which the arrows stay, faded behind the reflections. */
const FADED_ARROW_PHASES = new Set(["debrief", "done"]);

/**
 * The seats around the table card, on a 3 by 3 grid with the table in the middle.
 *
 * On narrow screens the table comes first and the seats follow in a list. From the
 * vote to the outcome the votes are drawn as arrows between the seats, and they stay
 * faded during the debrief.
 */
export function GameTable({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  const cells = seatCells(view.seats.length);
  const { containerRef, elementRef, measured, measure } = useElementRects();
  const fadedArrows = FADED_ARROW_PHASES.has(view.phase ?? "");
  const showArrows =
    view.votes !== null && (ARROW_PHASES.has(view.phase ?? "") || fadedArrows);

  // Measure again when the arrows appear, since the cards may have moved since.
  useLayoutEffect(() => {
    if (showArrows) {
      measure();
    }
  }, [showArrows, measure, view.votes?.votes.length]);

  return (
    <div
      ref={containerRef}
      className="relative grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:grid-rows-[auto_minmax(16rem,auto)_auto] lg:gap-5"
    >
      <div className="sm:col-span-2 lg:col-span-1 lg:col-start-2 lg:row-start-2">
        <TableCenter view={view} models={models} />
      </div>
      {view.seats.map((seat, index) => {
        const cell = cells[index];

        return (
          <SeatCard
            key={seat.seat}
            ref={elementRef(seat.seat)}
            seat={seat}
            model={models.get(seat.modelId ?? "")}
            className="lg:[grid-column:var(--column)] lg:[grid-row:var(--row)]"
            style={{ "--row": cell?.row, "--column": cell?.column } as CSSProperties}
          />
        );
      })}
      {showArrows && view.votes !== null && (
        <div
          data-faded={fadedArrows}
          className="pointer-events-none hidden transition-opacity duration-700 data-[faded=true]:opacity-25 lg:block"
        >
          <VoteArrows
            votes={view.votes.votes}
            rects={measured.rects}
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
