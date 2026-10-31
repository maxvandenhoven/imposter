import { Vote } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import {
  type Ballot,
  BALLOT_FLIGHT_SECONDS,
  ballotFlight,
  type BallotFlight,
  type BoardRect,
} from "@/lib/table";

/** One ballot, flying along the arc it had when it was thrown. */
function FlyingBallot({
  name,
  delay,
  flight,
}: {
  name: string;
  delay: number;
  flight: BallotFlight;
}) {
  // The arc is kept from the throw, so a resize while it flies does not throw it again.
  const [path] = useState(flight);

  return (
    <motion.div
      className="absolute top-0 left-0"
      initial={{ x: path.x[0], y: path.y[0], opacity: 0, scale: 0.6 }}
      animate={{
        x: path.x,
        y: path.y,
        opacity: [0, 1, 1, 0],
        scale: [0.6, 1.15, 1, 0.7],
        rotate: [-8, 6, 0],
      }}
      transition={{ duration: BALLOT_FLIGHT_SECONDS, delay, ease: "easeInOut" }}
    >
      <span className="flex -translate-x-1/2 -translate-y-1/2 items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-primary-foreground shadow-lg shadow-primary/30">
        <Vote className="size-3.5" />
        {name}
      </span>
    </motion.div>
  );
}

/**
 * The ballots flying across the board, each from the voter's card in an arc to the
 * card of the seat it votes for, where it lands as a chip. A secret vote in god mode
 * flies as it is cast, and the reveal throws every ballot again, one after another.
 */
export function BallotFlights({
  ballots,
  rects,
  width,
  height,
}: {
  ballots: Ballot[];
  rects: Map<number, BoardRect>;
  width: number;
  height: number;
}) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 z-20 overflow-visible"
      style={{ width, height }}
    >
      {ballots.map((ballot) => {
        const from = rects.get(ballot.voter);
        const to = rects.get(ballot.target);

        if (from === undefined || to === undefined) {
          return null;
        }

        return (
          <FlyingBallot
            key={`${ballot.revealed}-${ballot.voter}-${ballot.target}`}
            name={ballot.name}
            delay={ballot.delay}
            flight={ballotFlight({ from, to })}
          />
        );
      })}
    </div>
  );
}
