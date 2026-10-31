import { cn } from "cn";
import { Check, Megaphone } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { forwardRef } from "react";

import type { CatalogModel } from "@/api/types";
import { ModelThinking } from "@/components/board/ModelThinking";
import { RoleBadge } from "@/components/board/RoleBadge";
import { SeatAvatar } from "@/components/board/SeatAvatar";
import { SpeechBubble } from "@/components/board/SpeechBubble";
import { ThoughtBubble } from "@/components/board/ThoughtBubble";
import { TypingDots } from "@/components/board/TypingDots";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { bubbleKey, type SeatView } from "@/lib/boardView";

/** The clues of a seat, one chip per round, sliding in as they are given. */
function ClueChips({ seat }: { seat: SeatView }) {
  if (seat.clues.length === 0) {
    return null;
  }

  return (
    <ul className="flex flex-wrap justify-center gap-1" aria-label="Clues">
      <AnimatePresence initial={false}>
        {seat.clues.map(({ round, clue }) => (
          <motion.li
            key={round}
            initial={{ opacity: 0, y: -8, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 380, damping: 24 }}
          >
            <Badge variant={clue === null ? "outline" : "secondary"} className="gap-1">
              <span className="text-[0.6rem] font-semibold text-muted-foreground tabular-nums">
                R{round}
              </span>
              {clue ?? <span className="text-muted-foreground italic">pass</span>}
            </Badge>
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

/** The vote count of a seat after the reveal, popping in. */
function VoteCount({ count, caught }: { count: number; caught: boolean }) {
  return (
    <motion.span
      initial={{ scale: 0, rotate: -30 }}
      animate={{ scale: 1, rotate: 0 }}
      transition={{ type: "spring", stiffness: 420, damping: 16, delay: 0.4 }}
      data-caught={caught}
      aria-label={`${count} votes`}
      className="absolute -top-3 -right-2 z-10 flex size-9 items-center justify-center rounded-full bg-primary font-heading text-lg font-bold text-primary-foreground shadow-md ring-4 ring-background data-[caught=true]:bg-imposter"
    >
      {count}
    </motion.span>
  );
}

/**
 * A player's column in the row under the table: its card, its answer as a speech bubble
 * and, below it, its private reasoning as a thought bubble.
 *
 * The bubble shares its key with the one on the table, so an answer written on the
 * table moves down into the column when the turn ends. Answers that every seat writes
 * at once, votes and reflections, are written in the column itself.
 */
export const SeatColumn = forwardRef<
  HTMLDivElement,
  { seat: SeatView; model: CatalogModel | undefined; onStage: boolean }
>(function SeatColumn({ seat, model, onStage }, ref) {
  const live = seat.live;
  const said = seat.said;
  const liveText = onStage ? null : (live?.text ?? null);
  const text = liveText ?? (live === null ? (said?.text ?? null) : null);
  const reasoning = live?.reasoning ?? said?.reasoning ?? null;
  const key =
    said !== null && live === null
      ? bubbleKey(seat.seat, said.phase, said.round)
      : `live-${seat.seat}-${live?.phase ?? ""}`;

  return (
    <div ref={ref} className="flex min-w-0 flex-col items-stretch gap-2">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative"
      >
        {seat.votesReceived !== null && seat.votesReceived > 0 && (
          <VoteCount count={seat.votesReceived} caught={seat.caught} />
        )}
        <Card
          data-role={seat.role ?? "unknown"}
          className={cn(
            "items-center gap-2 border-t-4 border-t-transparent px-3 text-center transition-colors data-[role=civilian]:border-t-civilian data-[role=imposter]:border-t-imposter",
            seat.speaking && "speaking-glow",
            seat.caught && "bg-imposter/5",
          )}
        >
          <SeatAvatar model={model} role={seat.role} size="lg" />
          <div className="flex min-w-0 flex-col items-center">
            <h3 className="flex items-center gap-1.5 font-heading text-lg leading-tight font-semibold">
              <span className="truncate">{seat.name}</span>
              {seat.speaking && <TypingDots />}
            </h3>
            <p className="truncate text-xs text-muted-foreground">
              {model?.display_name ?? seat.modelId ?? "Unknown model"}
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-1">
            {seat.role !== null && <RoleBadge role={seat.role} />}
            {seat.hasVoted && seat.votesReceived === null && (
              <Badge variant="outline" className="text-muted-foreground">
                <Check data-icon="inline-start" />
                Voted
              </Badge>
            )}
            {seat.saidWord && (
              <Badge className="bg-destructive text-white">
                <Megaphone data-icon="inline-start" />
                Said the word
              </Badge>
            )}
          </div>
          <ClueChips seat={seat} />
          {seat.caught && (
            <motion.span
              initial={{ opacity: 0, scale: 1.8, rotate: -24 }}
              animate={{ opacity: 1, scale: 1, rotate: -12 }}
              transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.8 }}
              className="pointer-events-none absolute top-4 left-2 rounded-md border-2 border-imposter bg-card/80 px-1.5 py-0.5 font-heading text-xs font-extrabold tracking-widest text-imposter uppercase"
            >
              Caught
            </motion.span>
          )}
        </Card>
      </motion.div>
      <AnimatePresence mode="popLayout">
        {text !== null && text !== "" && (
          <motion.div
            key={key}
            layoutId={key}
            // Only the move from the table animates, not every shift of the column.
            layoutDependency={key}
            initial={{ opacity: 0, y: -16, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
          >
            <SpeechBubble live={liveText !== null} tail="top">
              {/* Finished text is cut to six lines, live text shows its growing end. */}
              <span className={cn(liveText === null && "line-clamp-6")}>{text}</span>
            </SpeechBubble>
          </motion.div>
        )}
      </AnimatePresence>
      {live?.voteFor != null && live.voteFor !== "" && (
        <p className="text-center text-sm text-muted-foreground">
          Voting for <span className="font-semibold text-foreground">{live.voteFor}</span>
        </p>
      )}
      {reasoning !== null && reasoning !== "" && (
        <ThoughtBubble
          text={reasoning}
          live={live?.reasoning != null}
          clamp={live?.reasoning == null}
        />
      )}
      {live?.thought != null && <ModelThinking text={live.thought} />}
    </div>
  );
});
