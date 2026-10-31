import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent, GameEventType } from "@/api/types";

/** Whether the game is still streaming, and how it ended. */
export type BoardStatus = "running" | "finished" | "aborted" | "failed" | "stopped";

/** What the board shows: the events so far, the answers being written and errors. */
export interface BoardState {
  status: BoardStatus;
  /** The id of the game, its ADK session, once it is created. */
  gameId: string | null;
  /** The engine events, in `seq` order. */
  events: GameEvent[];
  /** The answer each seat is writing, cleared when the engine event of the turn arrives. */
  answers: Partial<Record<number, PartialAnswer>>;
  /** The errors of the run. */
  errors: string[];
}

/** A change to the board, from the stream or the user. */
export type BoardAction =
  | { type: "session"; gameId: string }
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

/** Whether an engine event is a seat's answer, which ends its turn. */
function endsTurn(event: GameEvent): event is Extract<GameEvent, { seat: number }> {
  return ANSWER_EVENT_TYPES.has(event.type) && "seat" in event;
}

/** The board of a game that just started. */
export const INITIAL_BOARD: BoardState = {
  status: "running",
  gameId: null,
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
    case "session":
      return { ...state, gameId: action.gameId };
    case "game_event": {
      const { event } = action;
      // A new turn or the answer of the turn ends what the seat was writing.
      const ended = event.type === "turn_started" || endsTurn(event) ? event.seat : null;
      const answers = Object.fromEntries(
        Object.entries(state.answers).filter(([seat]) => Number(seat) !== ended),
      );

      return { ...state, events: [...state.events, event], answers };
    }
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
    } else if (endsTurn(event)) {
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
