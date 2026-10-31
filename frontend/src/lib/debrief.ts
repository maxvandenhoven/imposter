import type { GameEvent, GamePhase } from "@/api/types";
import { type ModelPrices, type SeatRole, TOKENS_PER_PRICE_UNIT } from "@/lib/boardView";

/** What a seat did in one turn, with the reasoning it wrote down at that moment. */
export interface DebriefTurnView {
  key: string;
  kind: "clue" | "statement" | "vote" | "guess" | "word_said";
  phase: GamePhase;
  round: number | null;
  /** The clue, statement, guess or word said, `null` for a pass or a vote. */
  text: string | null;
  /** The seat voted for, for a vote. */
  target: number | null;
  /** The private reasoning of the turn, empty when it wrote none. */
  reasoning: string;
}

/** One player in the debrief. */
export interface DebriefSeatView {
  seat: number;
  name: string;
  modelId: string | null;
  role: SeatRole;
  /** The turns of the seat in order: clues, statements, vote and guess. */
  turns: DebriefTurnView[];
  /** The reflection after the reveal, `null` while it is not in. */
  reflection: string | null;
  tokens: number;
  /** The estimated cost in USD, zero when the model has no known price. */
  costUsd: number;
}

/**
 * The debrief of a finished game, a card per player.
 *
 * It holds everything private, so it is only to be built for a game that is over.
 */
export function buildDebrief({
  events,
  prices,
}: {
  events: GameEvent[];
  prices: ModelPrices;
}): DebriefSeatView[] {
  const started = events.find((event) => event.type === "game_started");

  if (started === undefined) {
    return [];
  }

  const imposters = new Set(started.imposters);
  const seats = new Map<number, DebriefSeatView>(
    started.seats.map(({ seat, name }) => [
      seat,
      {
        seat,
        name,
        modelId: started.seat_models[seat] ?? null,
        role: imposters.has(seat) ? "imposter" : "civilian",
        turns: [],
        reflection: null,
        tokens: 0,
        costUsd: 0,
      },
    ]),
  );

  const addTurn = (
    event: GameEvent & { seat: number },
    turn: Pick<DebriefTurnView, "kind" | "text"> & { target?: number | null },
  ) => {
    seats.get(event.seat)?.turns.push({
      key: `e${event.seq}`,
      kind: turn.kind,
      phase: event.phase,
      round: event.round ?? null,
      text: turn.text,
      target: turn.target ?? null,
      reasoning: "private_reasoning" in event ? event.private_reasoning : "",
    });
  };

  for (const event of events) {
    switch (event.type) {
      case "clue_given":
        addTurn(event, { kind: "clue", text: event.clue });
        break;
      case "statement_made":
        addTurn(event, { kind: "statement", text: event.statement });
        break;
      case "vote_cast":
        addTurn(event, { kind: "vote", text: null, target: event.target });
        break;
      case "guess_made":
        addTurn(event, { kind: "guess", text: event.guess });
        break;
      case "secret_word_said":
        addTurn(event, { kind: "word_said", text: event.text });
        break;
      case "reflection": {
        const seat = seats.get(event.seat);

        if (seat !== undefined) {
          seat.reflection = event.reflection;
        }

        break;
      }
      case "usage": {
        const seat = seats.get(event.seat);
        const price = prices[event.model_id];

        if (seat !== undefined) {
          seat.tokens += event.input_tokens + event.output_tokens + event.thinking_tokens;

          if (price !== undefined) {
            seat.costUsd +=
              (event.input_tokens * price.input +
                (event.output_tokens + event.thinking_tokens) * price.output) /
              TOKENS_PER_PRICE_UNIT;
          }
        }

        break;
      }
      default:
        break;
    }
  }

  return [...seats.values()];
}
