import {
  ArrowRight,
  CircleCheck,
  CircleX,
  Gavel,
  HelpCircle,
  Lightbulb,
  Megaphone,
  MessagesSquare,
  NotebookPen,
  OctagonX,
  ScrollText,
  TriangleAlert,
  Vote,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useEffect, useRef } from "react";

import type { CatalogModel, GamePhase } from "@/api/types";
import { SeatAvatar } from "@/components/board/SeatAvatar";
import { SpeechBubble } from "@/components/board/SpeechBubble";
import { ThoughtBubble } from "@/components/board/ThoughtBubble";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { SeatView, TranscriptEntry } from "@/lib/boardView";
import { phaseTitle } from "@/lib/table";

/** How close to the bottom, in pixels, the transcript still follows new entries. */
const FOLLOW_DISTANCE = 120;

/** The input with which a reader scrolls, and how long a scroll after it counts. */
const INPUT_EVENTS = ["wheel", "touchmove", "pointerdown", "keydown"] as const;
const USER_SCROLL_MILLISECONDS = 1000;

const PHASE_ICONS: Partial<Record<GamePhase, typeof Lightbulb>> = {
  clue: Lightbulb,
  discussion: MessagesSquare,
  vote: Vote,
  guess: HelpCircle,
  debrief: NotebookPen,
};

interface EntryContext {
  seats: SeatView[];
  models: Map<string, CatalogModel>;
}

/** The warnings of a turn, shown under its entry. */
function Errors({ errors }: { errors: string[] }) {
  return errors.map((message, index) => (
    <p key={index} className="flex items-start gap-1.5 text-xs text-speaking">
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
      <span className="text-muted-foreground">{message}</span>
    </p>
  ));
}

/** A seat's line in the transcript: its avatar and name, then what it did. */
function SeatLine({
  seat,
  context,
  reasoning = null,
  errors = [],
  children,
}: {
  seat: number;
  context: EntryContext;
  reasoning?: string | null;
  errors?: string[];
  children: ReactNode;
}) {
  const view = context.seats[seat];

  return (
    <div className="flex gap-3">
      <SeatAvatar
        model={context.models.get(view?.modelId ?? "")}
        role={view?.role ?? null}
        size="sm"
        className="mt-0.5"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{view?.name ?? `Seat ${seat}`}</span>
          {children}
        </div>
        {reasoning !== null && <ThoughtBubble text={reasoning} />}
        <Errors errors={errors} />
      </div>
    </div>
  );
}

function nameOf(context: EntryContext, seat: number | null): string {
  return seat === null ? "nobody" : (context.seats[seat]?.name ?? `Seat ${seat}`);
}

/** One entry of the transcript. */
function Entry({ entry, context }: { entry: TranscriptEntry; context: EntryContext }) {
  switch (entry.kind) {
    case "phase": {
      const Icon = PHASE_ICONS[entry.phase] ?? ScrollText;

      return (
        <div className="flex items-center gap-2 pt-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
          <span className="flex size-6 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
            <Icon className="size-3.5" />
          </span>
          {phaseTitle(entry.phase, entry.round)}
          <span className="h-px flex-1 bg-border" />
        </div>
      );
    }
    case "clue":
      return (
        <SeatLine
          seat={entry.seat}
          context={context}
          reasoning={entry.reasoning}
          errors={entry.errors}
        >
          {entry.clue === null ? (
            <Badge variant="outline" className="text-muted-foreground italic">
              passed
            </Badge>
          ) : (
            <Badge variant="secondary" className="h-6 px-2.5 text-sm">
              {entry.clue}
            </Badge>
          )}
        </SeatLine>
      );
    case "statement":
      return (
        <SeatLine
          seat={entry.seat}
          context={context}
          reasoning={entry.reasoning}
          errors={entry.errors}
        >
          <SpeechBubble className="w-full text-sm">
            {entry.statement}
            {entry.truncated && <span className="text-muted-foreground"> (cut)</span>}
          </SpeechBubble>
        </SeatLine>
      );
    case "vote":
      return (
        <SeatLine
          seat={entry.seat}
          context={context}
          reasoning={entry.reasoning}
          errors={entry.errors}
        >
          <span className="flex items-center gap-1 text-sm text-muted-foreground">
            <ArrowRight className="size-3.5" />
            votes for
            <span className="font-medium text-foreground">
              {nameOf(context, entry.target)}
            </span>
          </span>
        </SeatLine>
      );
    case "votes":
      return (
        <div className="flex flex-col gap-2 rounded-xl border bg-secondary/50 p-3">
          <p className="flex items-center gap-1.5 text-sm font-semibold">
            <Gavel className="size-4 text-primary" />
            The votes are in
          </p>
          <ul className="grid grid-cols-[auto_auto_1fr] items-center gap-x-2 gap-y-1 text-sm">
            {entry.votes.map((vote) => (
              <li key={vote.voter} className="contents">
                <span>{nameOf(context, vote.voter)}</span>
                <ArrowRight className="size-3.5 text-muted-foreground" />
                <span className="font-medium">{nameOf(context, vote.target)}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm">
            {entry.caught.length === 0 ? (
              "A tie: nobody is caught."
            ) : (
              <>
                Caught:{" "}
                <span className="font-semibold text-imposter">
                  {entry.caught.map((seat) => nameOf(context, seat)).join(", ")}
                </span>
              </>
            )}
          </p>
        </div>
      );
    case "guess":
      return (
        <SeatLine
          seat={entry.seat}
          context={context}
          reasoning={entry.reasoning}
          errors={entry.errors}
        >
          <span className="text-sm text-muted-foreground">guesses</span>
          <Badge
            variant="outline"
            data-correct={entry.guess.correct}
            className="h-6 gap-1 text-sm data-[correct=false]:border-imposter/50 data-[correct=true]:border-civilian/50"
          >
            {entry.guess.correct ? (
              <CircleCheck className="text-civilian" />
            ) : (
              <CircleX className="text-imposter" />
            )}
            {entry.guess.guess || "no guess"}
          </Badge>
        </SeatLine>
      );
    case "word_said":
      return (
        <SeatLine
          seat={entry.seat}
          context={context}
          reasoning={entry.reasoning}
          errors={entry.errors}
        >
          <Badge className="bg-destructive text-white">
            <Megaphone data-icon="inline-start" />
            said the secret word
          </Badge>
          {entry.text !== null && (
            <span className="text-sm text-muted-foreground">“{entry.text}”</span>
          )}
        </SeatLine>
      );
    case "outcome":
      return (
        <div
          data-winner={entry.outcome.winner}
          className="rounded-xl px-3 py-2 text-white data-[winner=civilians]:bg-civilian data-[winner=imposters]:bg-imposter"
        >
          <p className="font-heading font-semibold">{entry.outcome.title}</p>
          <p className="text-sm opacity-90">
            {entry.outcome.detail} The word was “{entry.outcome.word}”.
          </p>
        </div>
      );
    case "reflection":
      return (
        <SeatLine seat={entry.seat} context={context} errors={entry.errors}>
          <SpeechBubble muted className="w-full text-sm">
            {entry.reflection}
          </SpeechBubble>
        </SeatLine>
      );
    case "error":
      return (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-speaking" />
          <span>
            <span className="font-medium text-foreground">
              {nameOf(context, entry.seat)}
            </span>
            : {entry.message}
          </span>
        </p>
      );
    case "aborted":
      return (
        <p className="flex items-center gap-2 rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <OctagonX className="size-4" />
          The game was aborted: {entry.reason}
        </p>
      );
  }
}

/**
 * The transcript of the game next to the table, newest last.
 *
 * It follows new entries, and the growing ones, while it is scrolled to the bottom, and
 * stays put while the reader scrolls back.
 */
export function Transcript({
  entries,
  seats,
  models,
  className,
}: {
  entries: TranscriptEntry[];
  seats: SeatView[];
  models: Map<string, CatalogModel>;
  className?: string;
}) {
  const viewport = useRef<HTMLDivElement | null>(null);
  // Whether the reader is at the bottom, which the reader changes by scrolling.
  const pinned = useRef(true);
  const context = { seats, models };

  useEffect(() => {
    const element = viewport.current;

    if (element === null) {
      return;
    }

    // Only scrolling by the reader changes whether it follows, not layout changes.
    let lastInput = 0;
    const onInput = () => {
      lastInput = Date.now();
    };
    const onScroll = () => {
      if (Date.now() - lastInput > USER_SCROLL_MILLISECONDS) {
        return;
      }

      const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
      pinned.current = distance < FOLLOW_DISTANCE;
    };

    for (const type of INPUT_EVENTS) {
      element.addEventListener(type, onInput, { passive: true });
    }

    element.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      for (const type of INPUT_EVENTS) {
        element.removeEventListener(type, onInput);
      }

      element.removeEventListener("scroll", onScroll);
    };
  }, []);

  useEffect(() => {
    const element = viewport.current;

    if (element !== null && pinned.current) {
      element.scrollTop = element.scrollHeight;
    }
  });

  return (
    <Card className={className}>
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <ScrollText className="size-4 text-primary" />
          Transcript
        </CardTitle>
      </CardHeader>
      <ScrollArea viewportRef={viewport} className="min-h-0 flex-1">
        {entries.length === 0 ? (
          <p className="px-4 text-sm text-muted-foreground">
            The table is being set. The first clue is coming up.
          </p>
        ) : (
          <ol className="flex flex-col gap-3 px-4 pb-4">
            <AnimatePresence initial={false}>
              {entries.map((entry) => (
                <motion.li
                  key={entry.key}
                  layout="position"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  <Entry entry={entry} context={context} />
                </motion.li>
              ))}
            </AnimatePresence>
          </ol>
        )}
      </ScrollArea>
    </Card>
  );
}
