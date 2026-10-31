import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent, GameEventType } from "@/api/types";

/** Whether the game is still streaming, and how it ended. */
export type BoardStatus = "running" | "finished" | "aborted" | "failed" | "stopped";

/** What the board shows: the events so far, the answers being written and errors. */
export interface BoardState {
  status: BoardStatus;
  /** The engine events, in `seq` order. */
  events: GameEvent[];
  /** The answer each seat is writing or wrote last. */
  answers: Partial<Record<number, PartialAnswer>>;
  /** The errors of the run. */
  errors: string[];
}

/** A change to the board, from the stream or the user. */
export type BoardAction =
  | { type: "game_event"; event: GameEvent }
  | { type: "answer"; answer: PartialAnswer }
  | { type: "error"; message: string }
  | { type: "ended"; stopped: boolean };

/** The engine events that hold a seat's answer and so end its turn. */
const ANSWER_EVENT_TYPES = new Set<GameEventType>([
  "clue_given",
  "statement_made",
  "vote_cast",
  "guess_made",
  "secret_word_said",
  "reflection",
]);

/** The board of a game that just started. */
export const INITIAL_BOARD: BoardState = {
  status: "running",
  events: [],
  answers: {},
  errors: [],
};

/** How a stream that ended left the game, judged by its last engine event. */
function endStatus(state: BoardState, stopped: boolean): BoardStatus {
  const last = state.events.at(-1)?.type;

  if (last === "game_finished") {
    return "finished";
  }

  if (last === "game_aborted") {
    return "aborted";
  }

  if (stopped) {
    return "stopped";
  }

  return "failed";
}

/** Apply one change to the board, returning the new board. */
export function boardReducer(state: BoardState, action: BoardAction): BoardState {
  switch (action.type) {
    case "game_event":
      return { ...state, events: [...state.events, action.event] };
    case "answer":
      return {
        ...state,
        answers: { ...state.answers, [action.answer.seat]: action.answer },
      };
    case "error":
      return { ...state, errors: [...state.errors, action.message] };
    case "ended":
      return { ...state, status: endStatus(state, action.stopped) };
  }
}

/**
 * The seats whose turn has started and not yet ended with their answer.
 *
 * Clue and discussion turns are one at a time, votes and reflections are asked of every
 * seat at once, so several seats can think together.
 */
export function thinkingSeats(events: GameEvent[]): number[] {
  const thinking = new Set<number>();

  for (const event of events) {
    if (event.type === "turn_started") {
      thinking.add(event.seat);
    } else if (ANSWER_EVENT_TYPES.has(event.type) && "seat" in event) {
      thinking.delete(event.seat);
    } else if (event.type === "game_aborted" || event.type === "game_finished") {
      thinking.clear();
    }
  }

  return [...thinking].sort((a, b) => a - b);
}

/** The name of each seat, known from the `game_started` event. */
export function seatNames(events: GameEvent[]): Map<number, string> {
  const started = events.find((event) => event.type === "game_started");

  return new Map(started?.seats.map((seat) => [seat.seat, seat.name]) ?? []);
}

function nameOf(names: Map<number, string>, seat: number | null): string {
  return seat === null ? "nobody" : (names.get(seat) ?? `Seat ${seat}`);
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Describe an engine event in one line, as the audience may see it.
 *
 * Votes stay secret until they are revealed, and private reasoning is left out.
 */
export function describeEvent(event: GameEvent, names: Map<number, string>): string {
  switch (event.type) {
    case "game_started":
      return `The game starts with ${event.seats.map((seat) => seat.name).join(", ")}.`;
    case "phase_started":
      return event.round === null
        ? `${capitalise(event.phase)} phase`
        : `${capitalise(event.phase)} round ${event.round}`;
    case "turn_started":
      return `${nameOf(names, event.seat)} is thinking.`;
    case "clue_given":
      return event.clue === null
        ? `${nameOf(names, event.seat)} passes.`
        : `${nameOf(names, event.seat)} gives the clue "${event.clue}".`;
    case "statement_made":
      return `${nameOf(names, event.seat)}: ${event.statement}`;
    case "vote_cast":
      return `${nameOf(names, event.seat)} has voted.`;
    case "votes_revealed": {
      const votes = event.votes
        .map((vote) => `${nameOf(names, vote.voter)} → ${nameOf(names, vote.target)}`)
        .join(", ");
      const caught = event.caught.map((seat) => nameOf(names, seat)).join(", ");

      return `Votes: ${votes}. Caught: ${caught || "nobody"}.`;
    }
    case "guess_made":
      return `${nameOf(names, event.seat)} guesses "${event.guess}", which is ${event.correct ? "right" : "wrong"}.`;
    case "secret_word_said":
      return `${nameOf(names, event.seat)} said the secret word!`;
    case "outcome": {
      const imposters = event.imposters.map((seat) => nameOf(names, seat)).join(", ");

      return `${capitalise(event.outcome.replaceAll("_", " "))}. The word was "${event.word}" and the imposter was ${imposters}.`;
    }
    case "reflection":
      return `${nameOf(names, event.seat)} reflects: ${event.reflection}`;
    case "player_error":
      return `${nameOf(names, event.seat)} ran into a problem: ${event.message}`;
    case "usage":
      return `${nameOf(names, event.seat)} used ${event.input_tokens + event.output_tokens + event.thinking_tokens} tokens (${event.total_tokens} in total).`;
    case "game_aborted":
      return `The game was aborted: ${event.reason}`;
    case "game_finished":
      return "The game is over.";
  }
}
