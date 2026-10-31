import { LayoutGroup } from "motion/react";
import type { CSSProperties } from "react";

import type { CatalogModel } from "@/api/types";
import { BallotFlights } from "@/components/board/BallotFlights";
import { SeatColumn } from "@/components/board/SeatColumn";
import { TableCenter } from "@/components/board/TableCenter";
import { useElementRects } from "@/hooks/useElementRects";
import type { BoardView } from "@/lib/boardView";
import { boardBallots } from "@/lib/table";

/**
 * The table card across the top and the players in one row below it, in seat order.
 *
 * Each player has a column with its card, its answer and its reasoning. From the vote
 * to the outcome every vote is a ballot that flies from the voter's card to the card of
 * the seat it votes for and stays there as a chip with the voter's name.
 */
export function GameTable({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  const ballots = boardBallots(view);
  // Measuring renders again on every resize, so it only runs while ballots show.
  const { containerRef, elementRef, measured } = useElementRects(ballots.length > 0);

  return (
    <div ref={containerRef} className="relative flex flex-col gap-6">
      {/* One group, so a bubble can move from the table to its seat's column. */}
      <LayoutGroup>
        <TableCenter view={view} models={models} />
        <div
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:[grid-template-columns:repeat(var(--seats),minmax(0,1fr))]"
          style={{ "--seats": view.seats.length } as CSSProperties}
        >
          {view.seats.map((seat) => (
            <SeatColumn
              key={seat.seat}
              cardRef={elementRef(seat.seat)}
              seat={seat}
              model={models.get(seat.modelId ?? "")}
              onStage={view.stage?.seat === seat.seat}
              ballots={ballots.filter((ballot) => ballot.target === seat.seat)}
            />
          ))}
        </div>
      </LayoutGroup>
      {ballots.length > 0 && (
        <BallotFlights
          ballots={ballots}
          rects={measured.rects}
          width={measured.width}
          height={measured.height}
        />
      )}
    </div>
  );
}
