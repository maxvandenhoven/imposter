import { cn } from "cn";
import { Check, Eye, HelpCircle, VenetianMask, X } from "lucide-react";
import type { ReactNode } from "react";

import { BallotChip } from "@/components/board/BallotChip";
import { SpeechBubble } from "@/components/board/SpeechBubble";
import type { SeatRole } from "@/lib/boardView";

/** A player in a rule diagram, with what the diagram shows about it. */
export interface DiagramPlayer {
  name: string;
  role: SeatRole;
  /** The logo in `public/logos` that stands for the player's model. */
  logo: string;
  /** What the player says, as a speech bubble pointing down at it. */
  says?: string;
  /** Whether what it says is allowed (`good`) or breaks a rule (`bad`). */
  mark?: "good" | "bad";
  /** The secret word as the player knows it, shown on a card above it. */
  knows?: string;
  /** The names of the players who voted for it. */
  votedBy?: string[];
  /** Whether the vote caught the player. */
  caught?: boolean;
  /** Whether the others suspect the player. */
  suspected?: boolean;
  /** Whether the player is out of focus in this diagram. */
  quiet?: boolean;
}

/** The check or cross on a speech bubble, for an allowed or a rule breaking answer. */
function AnswerMark({ mark }: { mark: "good" | "bad" }) {
  const Icon = mark === "good" ? Check : X;

  return (
    <span
      data-mark={mark}
      aria-label={mark === "good" ? "Allowed" : "Breaks a rule"}
      className="absolute -top-5 -right-5 flex size-6 items-center justify-center rounded-full text-white shadow-md ring-2 ring-card data-[mark=bad]:bg-destructive data-[mark=good]:bg-civilian"
    >
      <Icon className="size-3.5" strokeWidth={3} />
    </span>
  );
}

/** What sits above a player: its speech bubble or the word card it holds. */
function AbovePlayer({ player }: { player: DiagramPlayer }) {
  if (player.says !== undefined) {
    return (
      <SpeechBubble
        tail="bottom"
        className={cn(
          "w-max max-w-44 text-center text-sm",
          player.mark === "good" && "border-civilian/60",
          player.mark === "bad" && "border-destructive/60",
        )}
      >
        {player.says}
        {player.mark !== undefined && (
          <>
            {/* Room for the mark, which sits on the corner of the bubble. */}
            <span aria-hidden className="inline-block w-2" />
            <AnswerMark mark={player.mark} />
          </>
        )}
      </SpeechBubble>
    );
  }

  if (player.knows !== undefined) {
    const imposter = player.role === "imposter";
    const Icon = imposter ? VenetianMask : Eye;

    return (
      <span className="flex max-w-full flex-col items-center rounded-md bg-table px-1.5 py-1 text-[0.7rem] leading-tight font-semibold text-table-foreground shadow-sm">
        <Icon className={cn("size-3", imposter ? "text-imposter" : "text-speaking")} />
        {player.knows}
      </span>
    );
  }

  return null;
}

/**
 * A small scene of the game built from the pieces of the board: four players in a row,
 * with speech bubbles, word cards, ballots and stamps on them, and a caption below.
 *
 * Teal rings mark civilians and red rings imposters, as on the board in god mode.
 */
export function RuleDiagram({
  title,
  players,
  caption,
}: {
  title: string;
  players: DiagramPlayer[];
  caption: ReactNode;
}) {
  // The row above the players is only there when someone speaks or holds a word.
  const above = players.some(
    (player) => player.says !== undefined || player.knows !== undefined,
  );

  return (
    <figure className="flex flex-col gap-2" aria-label={title}>
      <span className="text-sm font-medium">{title}</span>
      <div className="board-surface grid grid-cols-4 gap-1 rounded-xl px-2 pt-4 pb-3 ring-1 ring-border">
        {players.map((player) => (
          <div
            key={player.name}
            data-quiet={player.quiet ?? false}
            className="flex min-w-0 flex-col items-center gap-1.5 transition-opacity data-[quiet=true]:opacity-45"
          >
            {above && (
              <div className="flex h-16 items-end justify-center">
                <AbovePlayer player={player} />
              </div>
            )}
            <div className="relative">
              <span
                data-role={player.role}
                className="flex size-11 items-center justify-center rounded-full bg-card shadow-sm ring-2 ring-offset-2 ring-offset-card data-[role=civilian]:ring-civilian data-[role=imposter]:ring-imposter"
              >
                <img src={`/logos/${player.logo}.svg`} alt="" className="size-6" />
              </span>
              {player.caught === true && (
                <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 -rotate-12 rounded-sm border-2 border-imposter bg-card/90 px-1 font-heading text-[0.6rem] font-extrabold tracking-widest text-imposter uppercase">
                  Caught
                </span>
              )}
              {player.suspected === true && (
                <span
                  aria-label="Suspected"
                  className="absolute -top-2 -right-2 flex size-5 items-center justify-center rounded-full bg-speaking text-white shadow-sm ring-2 ring-card"
                >
                  <HelpCircle className="size-3.5" />
                </span>
              )}
              {(player.votedBy?.length ?? 0) > 0 && (
                <span
                  data-caught={player.caught ?? false}
                  aria-label={`${player.votedBy?.length ?? 0} votes`}
                  className="absolute -top-2 -right-2 flex size-6 items-center justify-center rounded-full bg-primary font-heading text-sm font-bold text-primary-foreground shadow-sm ring-2 ring-card data-[caught=true]:bg-imposter"
                >
                  {player.votedBy?.length}
                </span>
              )}
            </div>
            <span className="relative max-w-full truncate font-heading text-sm font-semibold">
              {player.name}
            </span>
            {player.votedBy !== undefined && (
              <div className="flex min-h-5 flex-col items-center gap-0.5">
                {player.votedBy.map((voter) => (
                  <BallotChip
                    key={voter}
                    name={voter}
                    revealed
                    caught={player.caught ?? false}
                    className="px-1.5 text-[0.65rem]"
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <figcaption className="text-sm text-muted-foreground">{caption}</figcaption>
    </figure>
  );
}
