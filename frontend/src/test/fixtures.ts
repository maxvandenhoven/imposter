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

/** A `phase_started` event. */
export function phaseStarted(
  seq: number,
  phase: GameEvent["phase"],
  round: number | null = null,
): GameEvent {
  return { ...BASE, seq, phase, round, type: "phase_started" };
}

/** A `statement_made` event of a seat. */
export function statementMade(seq: number, seat: number, statement: string): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "discussion",
    type: "statement_made",
    seat,
    statement,
    truncated: false,
    private_reasoning: "Secret thoughts.",
    reasoning_truncated: false,
  };
}

/** The `votes_revealed` event of votes, as `[voter, target]` pairs. */
export function votesRevealed(
  seq: number,
  votes: [number, number | null][],
  caught: number[],
): GameEvent {
  const counts = [0, 0, 0];

  for (const [, target] of votes) {
    if (target !== null) {
      counts[target] = (counts[target] ?? 0) + 1;
    }
  }

  return {
    ...BASE,
    seq,
    phase: "resolution",
    round: null,
    type: "votes_revealed",
    votes: votes.map(([voter, target]) => ({ voter, target })),
    counts,
    caught,
  };
}

/** A `guess_made` event of an imposter. */
export function guessMade(
  seq: number,
  seat: number,
  guess: string,
  correct: boolean,
): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "guess",
    round: null,
    type: "guess_made",
    seat,
    guess,
    correct,
    judged_by: "exact",
    private_reasoning: "Secret thoughts.",
    reasoning_truncated: false,
  };
}

/** The `outcome` event of a game in which Bob, the imposter, was caught. */
export function outcome(
  seq: number,
  result: "civilians_win" | "imposter_wins" | "imposter_steals" = "civilians_win",
): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "outcome",
    round: null,
    type: "outcome",
    outcome: result,
    word: "lighthouse",
    imposters: [1],
    caught: [1],
    word_said_by: null,
  };
}

/** A `reflection` event of a seat. */
export function reflection(seq: number, seat: number, text: string): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "debrief",
    round: null,
    type: "reflection",
    seat,
    reflection: text,
  };
}

/** The `game_finished` event of a game in which the civilians won. */
export function gameFinished(seq: number): GameEvent {
  return {
    ...BASE,
    seq,
    phase: "done",
    round: null,
    type: "game_finished",
    outcome: "civilians_win",
  };
}

/** A `usage` event of a seat. */
export function usage(
  seq: number,
  seat: number,
  modelId: string,
  total: number,
): GameEvent {
  return {
    ...BASE,
    seq,
    visibility: "system",
    type: "usage",
    seat,
    model_id: modelId,
    input_tokens: 1_000_000,
    output_tokens: 100_000,
    thinking_tokens: 0,
    total_tokens: total,
  };
}

/** A `player_error` event of a seat. */
export function playerError(seq: number, seat: number, message: string): GameEvent {
  return { ...BASE, seq, visibility: "system", type: "player_error", seat, message };
}

/** A whole game: two clues, a statement, the vote, a wrong guess and the outcome. */
export function wholeGame(): GameEvent[] {
  return [
    gameStarted(0),
    phaseStarted(1, "clue", 1),
    turnStarted(2, 0),
    clueGiven(3, 0, "beacon"),
    turnStarted(4, 1),
    playerError(5, 1, "The model did not answer."),
    clueGiven(6, 1, "coast"),
    usage(7, 1, "claude-haiku", 1_100_000),
    phaseStarted(8, "discussion", 1),
    turnStarted(9, 2),
    statementMade(10, 2, "Bob seems unsure."),
    phaseStarted(11, "vote"),
    voteCast(12, 0, 1),
    voteCast(13, 1, 2),
    voteCast(14, 2, 1),
    votesRevealed(
      15,
      [
        [0, 1],
        [1, 2],
        [2, 1],
      ],
      [1],
    ),
    phaseStarted(16, "guess"),
    guessMade(17, 1, "harbour", false),
    outcome(18),
  ];
}
