import type { CatalogResponse, GameEvent } from "@/api/types";

/** A catalog shaped like the one the API returns, with three models. */
export const CATALOG: CatalogResponse = {
  models: [
    {
      id: "gemini-flash",
      display_name: "Gemini Flash",
      provider: "google",
      logo: "logos/gemini.svg",
      price_per_mtok: { input: 0.75, output: 3.75 },
    },
    {
      id: "claude-haiku",
      display_name: "Claude Haiku",
      provider: "anthropic",
      logo: "logos/claude.svg",
      price_per_mtok: { input: 0.1, output: 0.5 },
    },
    {
      id: "gpt-oss",
      display_name: "GPT-OSS 120B",
      provider: "openai",
      logo: null,
      price_per_mtok: { input: 0.09, output: 0.36 },
    },
  ],
  categories: [
    { name: "animals", description: "Creatures of land, sea and air." },
    { name: "food", description: "Things to eat and drink." },
  ],
  default_lineup: ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash"],
};

const BASE = {
  game_id: "game-1",
  phase: "clue",
  round: 1,
  timestamp: "2026-10-31T09:00:00Z",
  visibility: "public",
} as const;

/** The `game_started` event of a game with Alice, Bob and Charlie. */
export function gameStarted(seq = 0): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "setup",
    round: null,
    type: "game_started",
    identity_mode: "names",
    seats: [
      { seat: 0, name: "Alice" },
      { seat: 1, name: "Bob" },
      { seat: 2, name: "Charlie" },
    ],
    imposter_count: 1,
    clue_rounds: 2,
    discussion_rounds: 2,
    public_category: null,
    word: "lighthouse",
    category: "objects",
    hint: null,
    seat_models: ["gemini-flash", "claude-haiku", "gpt-oss"],
    imposters: [1],
  };
}

/** A `turn_started` event of a seat. */
export function turnStarted(seq: number, seat: number): GameEvent {
  return { ...BASE, seq, type: "turn_started", seat };
}

/** A `clue_given` event of a seat. */
export function clueGiven(seq: number, seat: number, clue: string | null): GameEvent {
  return {
    ...BASE,
    seq,
    type: "clue_given",
    seat,
    clue,
    rejection_reason: null,
    private_reasoning: "Secret thoughts.",
    reasoning_truncated: false,
  };
}

/** A `vote_cast` event of a seat. */
export function voteCast(seq: number, seat: number, target: number | null): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "vote",
    round: null,
    visibility: "private",
    type: "vote_cast",
    seat,
    target,
    private_reasoning: "Secret thoughts.",
    reasoning_truncated: false,
  };
}

/** The ADK event that carries an engine event. */
export function adkGameEvent(event: GameEvent) {
  return {
    author: "game_runner",
    invocationId: "e-1",
    nodeInfo: { path: `game_runner@1/${event.phase}@1` },
    content: { role: "model", parts: [{ text: JSON.stringify(event) }] },
    customMetadata: { game_event: event },
  };
}

/** A partial ADK event with the next chunk of a seat's answer. */
export function adkPartial({
  seat,
  phase = "clue",
  attempt = 1,
  text,
  thought = false,
}: {
  seat: number;
  phase?: string;
  attempt?: number;
  text: string;
  thought?: boolean;
}) {
  const author = `player_${seat}_${phase}`;

  return {
    author,
    invocationId: "e-1",
    partial: true,
    nodeInfo: {
      path: `game_runner@1/${phase}@1/player_${seat}_turn@1/${author}@${attempt}`,
    },
    content: { role: "model", parts: [{ text, thought }] },
  };
}
