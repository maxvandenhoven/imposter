import { CircleCheck, CircleX, Eye, EyeOff, Lightbulb, Tag } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import type { CatalogModel } from "@/api/types";
import { SeatAvatar } from "@/components/board/SeatAvatar";
import { SpeechBubble } from "@/components/board/SpeechBubble";
import { TypingDots } from "@/components/board/TypingDots";
import { Card } from "@/components/ui/card";
import type { BoardView, SeatView } from "@/lib/boardView";
import { phaseTitle } from "@/lib/table";

/** How a guess was judged, as the table says it. */
const JUDGED_BY = { exact: "exact match", judge: "judge's verdict", none: "no match" };

/** The round of a phase out of its total, when the phase has rounds. */
function roundOf(view: BoardView): string | null {
  if (view.round === null) {
    return null;
  }

  const total = view.phase === "clue" ? view.clueRounds : view.discussionRounds;

  return total > 0 ? `of ${total}` : null;
}

/** The seats that are writing, by name with their logo. */
function Speakers({
  seats,
  models,
}: {
  seats: SeatView[];
  models: Map<string, CatalogModel>;
}) {
  const speaking = seats.filter((seat) => seat.speaking);

  if (speaking.length === 0) {
    return null;
  }

  const many = speaking.length > 2;

  return (
    <div className="flex items-center justify-center gap-2 text-table-muted">
      <div className="flex -space-x-2">
        {speaking.map((seat) => (
          <SeatAvatar
            key={seat.seat}
            model={models.get(seat.modelId ?? "")}
            role={null}
            size="sm"
            className="ring-offset-table"
          />
        ))}
      </div>
      <span className="text-sm">
        {many ? "Everyone is" : `${speaking.map((seat) => seat.name).join(" and ")} is`}{" "}
        thinking
      </span>
      <TypingDots />
    </div>
  );
}

/** The revealed tally: each seat that got votes, with a dot per vote. */
function Tally({ view }: { view: BoardView }) {
  const voted = view.seats
    .filter((seat) => (seat.votesReceived ?? 0) > 0)
    .sort((a, b) => (b.votesReceived ?? 0) - (a.votesReceived ?? 0));

  return (
    <ul className="flex flex-col gap-1.5">
      {voted.map((seat, index) => (
        <motion.li
          key={seat.seat}
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 + index * 0.25 }}
          className="flex items-center justify-between gap-4"
        >
          <span className="font-medium">{seat.name}</span>
          <span className="flex items-center gap-1">
            {Array.from({ length: seat.votesReceived ?? 0 }, (_, dot) => (
              <span
                key={dot}
                data-caught={seat.caught}
                className="size-2.5 rounded-full bg-table-muted data-[caught=true]:bg-imposter"
              />
            ))}
          </span>
        </motion.li>
      ))}
      {view.votes?.caught.length === 0 && (
        <li className="text-sm text-table-muted">A tie: nobody is caught.</li>
      )}
    </ul>
  );
}

/** The imposters' guesses at the word, with the verdicts. */
function Guesses({ view }: { view: BoardView }) {
  return (
    <ul className="flex flex-col gap-2">
      {view.guesses.map((guess) => (
        <motion.li
          key={guess.seat}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-1"
        >
          <span className="text-sm text-table-muted">
            {view.seats[guess.seat]?.name} guesses
          </span>
          <span className="flex items-center gap-2 font-heading text-3xl font-bold">
            “{guess.guess || "…"}”
            {guess.correct ? (
              <CircleCheck className="size-7 text-civilian" />
            ) : (
              <CircleX className="size-7 text-imposter" />
            )}
          </span>
          <span className="text-xs text-table-muted">
            {guess.correct ? "Right" : "Wrong"}, by {JUDGED_BY[guess.judgedBy]}
          </span>
        </motion.li>
      ))}
    </ul>
  );
}

/**
 * The answer being written on the table by the one seat whose turn it is, with its
 * avatar and name. The bubble keeps its key when it moves down to the seat's column.
 */
function Stage({ view, models }: { view: BoardView; models: Map<string, CatalogModel> }) {
  const stage = view.stage;
  const seat = stage === null ? undefined : view.seats[stage.seat];

  if (stage === null || seat === undefined) {
    return null;
  }

  return (
    <div className="flex items-start justify-center gap-3">
      <div className="flex shrink-0 flex-col items-center gap-1 pt-1">
        <SeatAvatar
          model={models.get(seat.modelId ?? "")}
          role={seat.role}
          className="ring-offset-table"
        />
        <span className="text-xs font-medium text-table-muted">{seat.name}</span>
      </div>
      {stage.text === null || stage.text === "" ? (
        <div className="flex h-12 items-center gap-2 text-table-muted">
          <span className="text-sm">{seat.name} is thinking</span>
          <TypingDots />
        </div>
      ) : (
        <motion.div
          key={stage.bubbleKey}
          layoutId={stage.bubbleKey}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="max-w-3xl min-w-0 text-foreground"
        >
          <SpeechBubble live tail="left" className="text-base">
            {stage.text}
          </SpeechBubble>
        </motion.div>
      )}
    </div>
  );
}

/** The secret word: hidden, in god mode on a card, or revealed after the outcome. */
function SecretWord({ view }: { view: BoardView }) {
  if (view.revealed && view.outcome !== null) {
    return (
      <div className="flex flex-col items-center gap-1">
        <span className="text-sm text-table-muted">The word was</span>
        <motion.span
          initial={{ opacity: 0, scale: 0.6, rotateX: 90 }}
          animate={{ opacity: 1, scale: 1, rotateX: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 16 }}
          className="font-heading text-4xl font-extrabold tracking-tight text-speaking uppercase xl:text-5xl"
        >
          {view.outcome.word}
        </motion.span>
      </div>
    );
  }

  if (view.word !== null) {
    return (
      <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed border-table-muted/40 bg-white/6 px-6 py-2">
        <span className="flex items-center gap-1.5 text-xs tracking-wider text-table-muted uppercase">
          <Eye className="size-3.5" />
          Secret word
        </span>
        <span className="font-heading text-3xl font-bold text-speaking">{view.word}</span>
        {view.hint !== null && (
          <span className="flex items-center gap-1 text-xs text-table-muted">
            <Lightbulb className="size-3" />
            Imposter hint: {view.hint}
          </span>
        )}
      </div>
    );
  }

  return (
    <p className="flex items-center gap-1.5 text-sm text-table-muted">
      <EyeOff className="size-4" />
      The word stays hidden until the reveal
    </p>
  );
}

/** What the table shows about the current phase. */
function PhaseBody({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  if (view.guesses.length > 0) {
    return <Guesses view={view} />;
  }

  if (view.votes?.revealed === true) {
    return <Tally view={view} />;
  }

  if (view.phase === "vote") {
    const cast = view.seats.filter((seat) => seat.hasVoted).length;

    return (
      <div className="flex flex-col items-center gap-2">
        <span className="font-heading text-3xl font-bold tabular-nums">
          {cast} / {view.seats.length}
        </span>
        <span className="text-sm text-table-muted">secret votes cast</span>
        <Speakers seats={view.seats} models={models} />
      </div>
    );
  }

  return <Speakers seats={view.seats} models={models} />;
}

/**
 * The table across the top of the board: the phase, round and category on the left, the
 * secret word in the middle (in god mode, or once revealed) and what the current phase
 * is about on the right.
 */
export function TableCenter({
  view,
  models,
}: {
  view: BoardView;
  models: Map<string, CatalogModel>;
}) {
  const round = roundOf(view);

  return (
    <Card className="relative grid min-h-40 items-center gap-5 overflow-hidden bg-table px-6 text-table-foreground shadow-xl ring-0 lg:grid-cols-[1fr_auto_1fr] lg:gap-8 lg:px-8">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,color-mix(in_srgb,var(--primary)_55%,transparent),transparent_70%)] opacity-60"
      />
      <div className="relative flex flex-col items-center gap-1 lg:items-start">
        <AnimatePresence mode="wait">
          <motion.h2
            key={`${view.phase}-${view.round}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="font-heading text-2xl font-bold tracking-tight xl:text-3xl"
          >
            {phaseTitle(view.phase, view.round)}
            {round !== null && (
              <span className="ml-2 font-medium text-table-muted">{round}</span>
            )}
          </motion.h2>
        </AnimatePresence>
        <p className="flex items-center gap-1.5 text-sm text-table-muted">
          <Tag className="size-3.5" />
          {view.category === null ? "Secret category" : `Category: ${view.category}`}
        </p>
      </div>
      <div className="relative flex justify-center">
        <SecretWord view={view} />
      </div>
      <div className="relative flex justify-center lg:justify-end">
        {view.stage === null && <PhaseBody view={view} models={models} />}
      </div>
      {view.stage !== null && (
        <div className="relative lg:col-span-3">
          <Stage view={view} models={models} />
        </div>
      )}
    </Card>
  );
}
