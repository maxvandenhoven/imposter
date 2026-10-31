import { cn } from "cn";
import { Check, Megaphone } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { type CSSProperties, forwardRef } from "react";

import type { CatalogModel } from "@/api/types";
import { ModelThinking } from "@/components/board/ModelThinking";
import { RoleBadge } from "@/components/board/RoleBadge";
import { SeatAvatar } from "@/components/board/SeatAvatar";
import { SpeechBubble } from "@/components/board/SpeechBubble";
import { ThoughtBubble } from "@/components/board/ThoughtBubble";
import { TypingDots } from "@/components/board/TypingDots";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { SeatView } from "@/lib/boardView";

/** The clues of a seat, one chip per round, sliding in as they are given. */
function ClueChips({ seat }: { seat: SeatView }) {
  if (seat.clues.length === 0) {
    return null;
  }

  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Clues">
      <AnimatePresence initial={false}>
        {seat.clues.map(({ round, clue }) => (
          <motion.li
            key={round}
            layout
            initial={{ opacity: 0, x: -16, scale: 0.8 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 380, damping: 24 }}
          >
            <Badge
              variant={clue === null ? "outline" : "secondary"}
              className="h-7 gap-1.5 px-2.5 text-sm"
            >
              <span className="text-[0.65rem] font-semibold text-muted-foreground tabular-nums">
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
      className="absolute -top-3 -right-3 z-10 flex size-9 items-center justify-center rounded-full bg-primary font-heading text-lg font-bold text-primary-foreground shadow-md ring-4 ring-background data-[caught=true]:bg-imposter"
    >
      {count}
    </motion.span>
  );
}

/**
 * A seat at the table: who plays it, its clues, what it says and, in god mode, what it
 * thinks. The seat whose turn it is glows and shows its answer as it is written.
 */
export const SeatCard = forwardRef<
  HTMLDivElement,
  {
    seat: SeatView;
    model: CatalogModel | undefined;
    className?: string;
    style?: CSSProperties;
  }
>(function SeatCard({ seat, model, className, style }, ref) {
  const live = seat.live;
  const text = live?.text ?? seat.said?.text ?? null;
  const reasoning = live?.reasoning ?? seat.said?.reasoning ?? null;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("relative", className)}
      style={style}
    >
      {seat.votesReceived !== null && seat.votesReceived > 0 && (
        <VoteCount count={seat.votesReceived} caught={seat.caught} />
      )}
      <Card
        data-speaking={seat.speaking}
        data-role={seat.role ?? "unknown"}
        className={cn(
          "h-full gap-3 border-t-4 border-t-transparent px-4 transition-colors data-[role=civilian]:border-t-civilian data-[role=imposter]:border-t-imposter",
          seat.speaking && "speaking-glow",
          seat.caught && "bg-imposter/4",
        )}
      >
        <div className="flex items-center gap-3">
          <SeatAvatar model={model} role={seat.role} size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate font-heading text-lg leading-tight font-semibold">
                {seat.name}
              </h3>
              {seat.speaking && <TypingDots />}
            </div>
            <p className="truncate text-xs text-muted-foreground">
              {model?.display_name ?? seat.modelId ?? "Unknown model"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            {seat.role !== null && <RoleBadge role={seat.role} />}
            {seat.hasVoted && seat.votesReceived === null && (
              <Badge variant="outline" className="text-muted-foreground">
                <Check data-icon="inline-start" />
                Voted
              </Badge>
            )}
          </div>
        </div>
        <ClueChips seat={seat} />
        <AnimatePresence mode="popLayout">
          {text !== null && text !== "" && (
            <motion.div
              key={`said-${seat.said?.phase ?? live?.phase}-${seat.said?.round ?? ""}`}
              initial={{ opacity: 0, scale: 0.92, originX: 0, originY: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.92 }}
            >
              <SpeechBubble live={live?.text != null}>
                {/* Finished text is cut to five lines, live text shows its growing end. */}
                <span className={cn(live?.text == null && "line-clamp-5")}>{text}</span>
              </SpeechBubble>
            </motion.div>
          )}
        </AnimatePresence>
        {live?.voteFor != null && live.voteFor !== "" && (
          <p className="text-sm text-muted-foreground">
            Voting for{" "}
            <span className="font-semibold text-foreground">{live.voteFor}</span>
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
        {seat.caught && (
          <motion.span
            initial={{ opacity: 0, scale: 1.8, rotate: -24 }}
            animate={{ opacity: 1, scale: 1, rotate: -12 }}
            transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.8 }}
            className="pointer-events-none absolute top-14 right-4 rounded-md border-2 border-imposter bg-card/80 px-2 py-0.5 font-heading text-sm font-extrabold tracking-widest text-imposter uppercase"
          >
            Caught
          </motion.span>
        )}
        {seat.saidWord && (
          <Badge className="bg-destructive text-white">
            <Megaphone data-icon="inline-start" />
            Said the word
          </Badge>
        )}
      </Card>
    </motion.div>
  );
});
