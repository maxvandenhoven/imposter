import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent, GameOutcome, GamePhase, IdentityMode } from "@/api/types";
import { thinkingSeats } from "@/lib/board";
import { partialStringFields } from "@/lib/partialJson";

/** Who watches: the audience sees only public fields, god mode sees everything. */
export type BoardMode = "audience" | "god";

/** The role of a seat, once it may be shown. */
export type SeatRole = "imposter" | "civilian";

/** The side that won the game. */
export type GameWinner = "imposters" | "civilians";

/** The catalog price of each model in USD per million tokens, by model id. */
export type ModelPrices = Partial<Record<string, { input: number; output: number }>>;

type EventOf<T extends GameEvent["type"]> = Extract<GameEvent, { type: T }>;

/** The answer a seat is writing, with the private parts only when they may be shown. */
export interface LiveAnswerView {
  /** The phase of the turn. */
  phase: string;
  /** The public field so far: the clue, statement, guess or reflection. */
  text: string | null;
  /** The name the seat votes for so far, a private field. */
  voteFor: string | null;
  /** The private reasoning so far. */
  reasoning: string | null;
  /** The model's native thinking so far. */
  thought: string | null;
}

/** A clue of a seat in one round, `null` when the seat passed. */
export interface SeatClueView {
  round: number;
  clue: string | null;
}

/** What a seat said last in the current phase and round, shown as its bubble. */
export interface SeatSaidView {
  phase: GamePhase;
  round: number | null;
  /** The public text: a clue, statement, guess or reflection, `null` for votes. */
  text: string | null;
  /** The private reasoning, when it may be shown. */
  reasoning: string | null;
}

/** A seat at the table. */
export interface SeatView {
  seat: number;
  name: string;
  /** The catalog id of the model that plays the seat. */
  modelId: string | null;
  /** The role, in god mode or after the reveal. */
  role: SeatRole | null;
  /** Whether the seat's turn is running. */
  speaking: boolean;
  /** The answer the seat is writing, while it speaks. */
  live: LiveAnswerView | null;
  /** The clues of the seat, by round. */
  clues: SeatClueView[];
  /** What the seat said last in the current phase and round. */
  said: SeatSaidView | null;
  /** Whether the seat cast its vote. */
  hasVoted: boolean;
  /** The votes the seat got, once the votes are revealed. */
  votesReceived: number | null;
  /** Whether the vote caught the seat. */
  caught: boolean;
  /** Whether the seat said the secret word and ended the game. */
  saidWord: boolean;
}

/** One vote, from voter to target, `null` for an abstention. */
export interface VoteView {
  voter: number;
  target: number | null;
}

/** The votes: the revealed tally, or in god mode the secret votes so far. */
export interface VotesView {
  /** Whether the votes were revealed to everyone. */
  revealed: boolean;
  votes: VoteView[];
  /** The caught seats, once revealed. */
  caught: number[];
}

/** An imposter's guess at the word, with the verdict. */
export interface GuessView {
  seat: number;
  guess: string;
  correct: boolean;
  judgedBy: EventOf<"guess_made">["judged_by"];
}

/** How the game ended, shown in the outcome banner. */
export interface OutcomeView {
  outcome: GameOutcome;
  winner: GameWinner;
  title: string;
  detail: string;
  word: string;
  imposters: number[];
}

/** The tokens and the estimated cost of the game so far. */
export interface UsageView {
  tokens: number;
  /** The estimated cost in USD of the turns whose model has a known price. */
  costUsd: number;
}

interface BaseTranscriptEntry {
  /** A key that stays the same while the board grows. */
  key: string;
}

interface SeatTranscriptEntry extends BaseTranscriptEntry {
  seat: number;
  /** The private reasoning, when it may be shown. */
  reasoning: string | null;
  /** The player errors of the turn. */
  errors: string[];
}

/** One line of the transcript next to the table. */
export type TranscriptEntry =
  | (BaseTranscriptEntry & { kind: "phase"; phase: GamePhase; round: number | null })
  | (SeatTranscriptEntry & { kind: "clue"; round: number; clue: string | null })
  | (SeatTranscriptEntry & { kind: "statement"; statement: string; truncated: boolean })
  | (SeatTranscriptEntry & { kind: "vote"; target: number | null })
  | (BaseTranscriptEntry & { kind: "votes"; votes: VoteView[]; caught: number[] })
  | (SeatTranscriptEntry & { kind: "guess"; guess: GuessView })
  | (SeatTranscriptEntry & { kind: "word_said"; text: string | null })
  | (BaseTranscriptEntry & { kind: "outcome"; outcome: OutcomeView })
  | (SeatTranscriptEntry & { kind: "reflection"; reflection: string })
  | (BaseTranscriptEntry & { kind: "error"; seat: number; message: string })
  | (BaseTranscriptEntry & { kind: "aborted"; reason: string });

/** The seat whose answer is written on the table, in a turn that one seat takes alone. */
export interface StageView {
  seat: number;
  /** The public text so far, `null` until it starts. */
  text: string | null;
  /** The key its bubble keeps when it moves from the table to the seat. */
  bubbleKey: string;
}

/** What the board shows at the cursor, in one mode. */
export interface BoardView {
  /** Whether the `game_started` event arrived. */
  started: boolean;
  phase: GamePhase | null;
  round: number | null;
  identityMode: IdentityMode | null;
  clueRounds: number;
  discussionRounds: number;
  imposterCount: number;
  /** The category, when it is public, in god mode or after the reveal. */
  category: string | null;
  /** The secret word, in god mode or after the reveal. */
  word: string | null;
  /** The imposter hint, in god mode or after the reveal. */
  hint: string | null;
  /** Whether the outcome revealed the word and the roles to everyone. */
  revealed: boolean;
  /** Whether private fields are shown: in god mode or after the reveal. */
  showPrivate: boolean;
  seats: SeatView[];
  /** The answer being written on the table, in clue, discussion and guess turns. */
  stage: StageView | null;
  votes: VotesView | null;
  guesses: GuessView[];
  outcome: OutcomeView | null;
  /** Why the game was aborted, if it was. */
  aborted: string | null;
  /** Whether the game finished, debrief included. */
  finished: boolean;
  usage: UsageView;
  transcript: TranscriptEntry[];
}

/** The phases that start a section of the transcript. */
const TRANSCRIPT_PHASES = new Set<GamePhase>([
  "clue",
  "discussion",
  "vote",
  "guess",
  "debrief",
]);

/** The public field of the answer in each phase. */
const PUBLIC_ANSWER_FIELDS: Partial<Record<string, string>> = {
  clue: "clue",
  discussion: "statement",
  guess: "guess",
  debrief: "reflection",
};

/** The phases in which one seat speaks at a time, with its answer on the table. */
const STAGE_PHASES = new Set<string>(["clue", "discussion", "guess"]);

/** The phases whose public answer could say the secret word before the reveal. */
const MASKED_PHASES = new Set(["clue", "discussion"]);

/** What hides the secret word in live text. */
export const WORD_MASK = "•••";

/** The shortest start of the secret word that is hidden at the end of live text. */
const MASKED_PREFIX_LENGTH = 3;

const OUTCOME_TEXT: Record<GameOutcome, { winner: GameWinner; title: string }> = {
  imposter_wins: { winner: "imposters", title: "The imposter got away" },
  imposter_steals: { winner: "imposters", title: "The imposter steals the win" },
  civilians_win: { winner: "civilians", title: "The civilians win" },
  civilian_said_word: { winner: "imposters", title: "A civilian said the word" },
  imposter_said_word: { winner: "civilians", title: "The imposter said the word" },
};

/** The number of tokens that the catalog prices are given for. */
export const TOKENS_PER_PRICE_UNIT = 1_000_000;

function escapeRegExp(text: string): string {
  return text.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

/**
 * Hide the secret word in text that is still being written.
 *
 * Every occurrence is hidden, regardless of case, and so is a start of the word at the
 * end of the text, since the next chunk may complete it.
 */
export function maskWord(text: string, word: string): string {
  if (word === "") {
    return text;
  }

  const masked = text.replaceAll(new RegExp(escapeRegExp(word), "gi"), WORD_MASK);
  const lower = masked.toLowerCase();
  const target = word.toLowerCase();

  for (let length = target.length - 1; length >= MASKED_PREFIX_LENGTH; length -= 1) {
    if (lower.endsWith(target.slice(0, length))) {
      return masked.slice(0, masked.length - length) + WORD_MASK;
    }
  }

  return masked;
}

/** The winner, title and one-line explanation of an outcome. */
export function describeOutcome(
  event: EventOf<"outcome">,
  names: Map<number, string>,
): OutcomeView {
  const { winner, title } = OUTCOME_TEXT[event.outcome];
  const imposters = event.imposters.map((seat) => names.get(seat) ?? `Seat ${seat}`);
  const who = imposters.join(" and ");
  const details: Record<GameOutcome, string> = {
    imposter_wins: `Nobody caught ${who}.`,
    imposter_steals: `${who} was caught but guessed the word.`,
    civilians_win: `${who} was caught and guessed wrong.`,
    civilian_said_word: `${names.get(event.word_said_by ?? -1) ?? "A civilian"} gave the word away.`,
    imposter_said_word: `${who} said the word and gave the game away.`,
  };

  return {
    outcome: event.outcome,
    winner,
    title,
    detail: details[event.outcome],
    word: event.word,
    imposters: event.imposters,
  };
}

/** The live answer of a speaking seat, with private parts only when they may be shown. */
function liveAnswer({
  answer,
  showPrivate,
  word,
}: {
  answer: PartialAnswer;
  showPrivate: boolean;
  word: string;
}): LiveAnswerView {
  const fields = partialStringFields(answer.text);
  const publicField = PUBLIC_ANSWER_FIELDS[answer.phase];
  let text = publicField === undefined ? null : (fields[publicField] ?? null);

  if (text !== null && !showPrivate && MASKED_PHASES.has(answer.phase)) {
    text = maskWord(text, word);
  }

  return {
    phase: answer.phase,
    text,
    voteFor: showPrivate ? (fields.vote_for ?? null) : null,
    reasoning: showPrivate ? (fields.private_reasoning ?? null) : null,
    thought: showPrivate && answer.thought !== "" ? answer.thought : null,
  };
}

/** The key of a seat's speech bubble in a phase and round, the same on table and seat. */
export function bubbleKey(seat: number, phase: string, round: number | null): string {
  return `bubble-${seat}-${phase}-${round ?? ""}`;
}

function turnKey(seat: number, phase: string, round: number | null): string {
  return `${seat}|${phase}|${round ?? ""}`;
}

/** The engine events that become a seat's transcript entry, as their turn key. */
function answerKey(event: GameEvent, showPrivate: boolean): string | null {
  switch (event.type) {
    case "clue_given":
    case "statement_made":
    case "guess_made":
    case "secret_word_said":
    case "reflection":
      return turnKey(event.seat, event.phase, event.round);
    case "vote_cast":
      return showPrivate ? turnKey(event.seat, event.phase, event.round) : null;
    default:
      return null;
  }
}

/**
 * Build what the board shows from the engine events up to the cursor.
 *
 * In audience mode nothing private is in the view until the outcome reveals the word:
 * no word, hint, private category, roles, votes before their reveal, private reasoning,
 * live vote or model thinking, and the secret word is hidden in live clues and
 * statements. After the reveal, and in god mode, everything is shown. The answers being
 * written are shown only at the live end of a running game.
 */
export function buildBoardView({
  events: allEvents,
  cursor = allEvents.length,
  answers,
  mode,
  running,
  prices,
}: {
  events: GameEvent[];
  cursor?: number;
  answers: Partial<Record<number, PartialAnswer>>;
  mode: BoardMode;
  running: boolean;
  prices: ModelPrices;
}): BoardView {
  const events = allEvents.slice(0, cursor);
  const atLiveEnd = running && cursor >= allEvents.length;
  const started = events.find((event) => event.type === "game_started");
  const outcomeEvent = events.find((event) => event.type === "outcome");
  const revealed = outcomeEvent !== undefined;
  const showPrivate = mode === "god" || revealed;
  const names = new Map(started?.seats.map((seat) => [seat.seat, seat.name]) ?? []);
  const imposters = new Set(started?.imposters ?? []);
  const speaking = new Set(atLiveEnd ? thinkingSeats(events) : []);
  const seats: SeatView[] = (started?.seats ?? []).map(({ seat, name }) => {
    const answer = answers[seat];
    const isSpeaking = speaking.has(seat);

    return {
      seat,
      name,
      modelId: started?.seat_models[seat] ?? null,
      role: showPrivate ? (imposters.has(seat) ? "imposter" : "civilian") : null,
      speaking: isSpeaking,
      live:
        isSpeaking && answer !== undefined
          ? liveAnswer({ answer, showPrivate, word: started?.word ?? "" })
          : null,
      clues: [],
      said: null,
      hasVoted: false,
      votesReceived: null,
      caught: false,
      saidWord: false,
    };
  });
  const seatAt = (seat: number): SeatView | undefined => seats[seat];
  const answerKeys = new Set(
    events.map((event) => answerKey(event, showPrivate)).filter((key) => key !== null),
  );
  const seatEntries = new Map<string, SeatTranscriptEntry>();
  const pendingErrors = new Map<string, string[]>();
  const transcript: TranscriptEntry[] = [];
  const castVotes: VoteView[] = [];
  const guesses: GuessView[] = [];
  let revealedVotes: VotesView | null = null;
  let phase: GamePhase | null = null;
  let round: number | null = null;
  let tokens = 0;
  let costUsd = 0;
  let aborted: string | null = null;
  let finished = false;
  const reasoningOf = (event: { private_reasoning: string }): string | null =>
    showPrivate && event.private_reasoning !== "" ? event.private_reasoning : null;

  // Notes what a seat said, which its card shows while the phase and round last.
  const noteSaid = (event: GameEvent & { seat: number }, text: string | null) => {
    const seat = seatAt(event.seat);
    const reasoning = "private_reasoning" in event ? reasoningOf(event) : null;

    if (seat !== undefined) {
      seat.said = { phase: event.phase, round: event.round ?? null, text, reasoning };
    }
  };

  // Adds a seat's entry to the transcript with the errors of its turn reported so far.
  const addSeatEntry = (entry: TranscriptEntry & SeatTranscriptEntry, key: string) => {
    entry.errors.push(...(pendingErrors.get(key) ?? []));
    pendingErrors.delete(key);
    seatEntries.set(key, entry);
    transcript.push(entry);
  };

  for (const event of events) {
    const key = `e${event.seq}`;
    const turn = answerKey(event, showPrivate);

    if (event.type !== "usage" && event.type !== "player_error") {
      phase = event.phase;
      round = event.round ?? null;
    }

    switch (event.type) {
      case "phase_started":
        if (TRANSCRIPT_PHASES.has(event.phase)) {
          transcript.push({ key, kind: "phase", phase: event.phase, round: event.round });
        }

        break;
      case "clue_given":
        seatAt(event.seat)?.clues.push({ round: event.round ?? 0, clue: event.clue });
        noteSaid(event, event.clue);
        addSeatEntry(
          {
            key,
            kind: "clue",
            seat: event.seat,
            round: event.round ?? 0,
            clue: event.clue,
            reasoning: reasoningOf(event),
            errors: [],
          },
          turn ?? key,
        );
        break;
      case "statement_made":
        noteSaid(event, event.statement);
        addSeatEntry(
          {
            key,
            kind: "statement",
            seat: event.seat,
            statement: event.statement,
            truncated: event.truncated,
            reasoning: reasoningOf(event),
            errors: [],
          },
          turn ?? key,
        );
        break;
      case "vote_cast": {
        const voter = seatAt(event.seat);

        if (voter !== undefined) {
          voter.hasVoted = true;
        }

        if (showPrivate) {
          noteSaid(event, null);
          castVotes.push({ voter: event.seat, target: event.target });
          addSeatEntry(
            {
              key,
              kind: "vote",
              seat: event.seat,
              target: event.target,
              reasoning: reasoningOf(event),
              errors: [],
            },
            turn ?? key,
          );
        }

        break;
      }
      case "votes_revealed":
        revealedVotes = { revealed: true, votes: event.votes, caught: event.caught };

        for (const seat of seats) {
          seat.votesReceived = event.counts[seat.seat] ?? 0;
          seat.caught = event.caught.includes(seat.seat);
        }

        transcript.push({ key, kind: "votes", votes: event.votes, caught: event.caught });
        break;
      case "guess_made": {
        const guess: GuessView = {
          seat: event.seat,
          guess: event.guess,
          correct: event.correct,
          judgedBy: event.judged_by,
        };
        guesses.push(guess);
        noteSaid(event, event.guess);
        addSeatEntry(
          {
            key,
            kind: "guess",
            seat: event.seat,
            guess,
            reasoning: reasoningOf(event),
            errors: [],
          },
          turn ?? key,
        );
        break;
      }
      case "secret_word_said": {
        const seat = seatAt(event.seat);

        if (seat !== undefined) {
          seat.saidWord = true;
        }

        noteSaid(event, showPrivate ? event.text : null);

        addSeatEntry(
          {
            key,
            kind: "word_said",
            seat: event.seat,
            text: showPrivate ? event.text : null,
            reasoning: reasoningOf(event),
            errors: [],
          },
          turn ?? key,
        );
        break;
      }
      case "outcome":
        transcript.push({ key, kind: "outcome", outcome: describeOutcome(event, names) });
        break;
      case "reflection":
        noteSaid(event, event.reflection);
        addSeatEntry(
          {
            key,
            kind: "reflection",
            seat: event.seat,
            reflection: event.reflection,
            reasoning: null,
            errors: [],
          },
          turn ?? key,
        );
        break;
      case "player_error": {
        const errorKey = turnKey(event.seat, event.phase, event.round);
        const entry = seatEntries.get(errorKey);

        if (entry !== undefined) {
          entry.errors.push(event.message);
        } else if (answerKeys.has(errorKey)) {
          pendingErrors.set(errorKey, [
            ...(pendingErrors.get(errorKey) ?? []),
            event.message,
          ]);
        } else {
          transcript.push({
            key,
            kind: "error",
            seat: event.seat,
            message: event.message,
          });
        }

        break;
      }
      case "usage": {
        const price = prices[event.model_id];
        tokens = Math.max(tokens, event.total_tokens);

        if (price !== undefined) {
          const billed =
            event.input_tokens * price.input +
            (event.output_tokens + event.thinking_tokens) * price.output;
          costUsd += billed / TOKENS_PER_PRICE_UNIT;
        }

        break;
      }
      case "game_aborted":
        aborted = event.reason;
        transcript.push({ key, kind: "aborted", reason: event.reason });
        break;
      case "game_finished":
        finished = true;
        break;
      case "game_started":
      case "turn_started":
        break;
    }
  }

  // A bubble lasts as long as its phase and round, and the reflections stay at the end.
  const bubblePhase = phase === "done" ? "debrief" : phase;

  for (const seat of seats) {
    if (seat.said?.phase !== bubblePhase || seat.said.round !== round) {
      seat.said = null;
    }
  }

  const speakers = seats.filter((seat) => seat.speaking);
  const speaker = speakers.length === 1 ? speakers[0] : undefined;
  const stage: StageView | null =
    speaker !== undefined && STAGE_PHASES.has(phase ?? "")
      ? {
          seat: speaker.seat,
          text: speaker.live?.text ?? null,
          bubbleKey: bubbleKey(speaker.seat, phase ?? "", round),
        }
      : null;

  const votes: VotesView | null =
    revealedVotes ??
    (showPrivate && castVotes.length > 0
      ? { revealed: false, votes: castVotes, caught: [] }
      : null);

  return {
    started: started !== undefined,
    phase,
    round,
    identityMode: started?.identity_mode ?? null,
    clueRounds: started?.clue_rounds ?? 0,
    discussionRounds: started?.discussion_rounds ?? 0,
    imposterCount: started?.imposter_count ?? 0,
    category:
      started?.public_category ?? (showPrivate ? (started?.category ?? null) : null),
    word: showPrivate ? (started?.word ?? null) : null,
    hint: showPrivate ? (started?.hint ?? null) : null,
    revealed,
    showPrivate,
    seats,
    stage,
    votes,
    guesses,
    outcome: outcomeEvent === undefined ? null : describeOutcome(outcomeEvent, names),
    aborted,
    finished,
    usage: { tokens, costUsd },
    transcript,
  };
}
