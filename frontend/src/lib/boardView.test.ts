import { describe, expect, it } from "vitest";

import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent } from "@/api/types";
import {
  type BoardMode,
  buildBoardView,
  maskWord,
  type ModelPrices,
  WORD_MASK,
} from "@/lib/boardView";
import {
  clueGiven,
  gameStarted,
  phaseStarted,
  turnStarted,
  voteCast,
  wholeGame,
} from "@/test/fixtures";

const BASE_REFLECTION = {
  game_id: "game-1",
  seq: 0,
  phase: "debrief",
  round: null,
  timestamp: "2026-10-31T09:00:00Z",
  visibility: "public",
  type: "reflection",
  seat: 0,
  reflection: "I played well.",
} as const satisfies GameEvent;

const PRICES: ModelPrices = { "claude-haiku": { input: 0.1, output: 0.5 } };

/** Every private value of the fixtures, none of which the audience may see early. */
const SECRETS = ["lighthouse", "objects", "Secret thoughts", "Deep thinking"];

function answer(seat: number, phase: string, text: string, thought = ""): PartialAnswer {
  return { seat, phase, path: `p${seat}@1`, text, thought };
}

function view({
  events,
  mode = "audience",
  answers = {},
  running = true,
  cursor,
}: {
  events: GameEvent[];
  mode?: BoardMode;
  answers?: Partial<Record<number, PartialAnswer>>;
  running?: boolean;
  cursor?: number;
}) {
  return buildBoardView({ events, cursor, answers, mode, running, prices: PRICES });
}

describe("buildBoardView in audience mode", () => {
  it("shows nothing private before the reveal, at any cursor", () => {
    const events = wholeGame();
    const outcomeAt = events.findIndex((event) => event.type === "outcome");

    for (let cursor = 0; cursor <= outcomeAt; cursor += 1) {
      const live = cursor === events.length ? {} : liveAnswers(events.slice(0, cursor));
      const board = view({ events: events.slice(0, cursor), answers: live });
      const text = JSON.stringify(board);

      for (const secret of SECRETS) {
        expect(text, `cursor ${cursor}`).not.toContain(secret);
      }

      expect(board.showPrivate).toBe(false);
      expect(board.word).toBeNull();
      expect(board.seats.every((seat) => seat.role === null)).toBe(true);
      expect(board.seats.every((seat) => !seat.live?.voteFor)).toBe(true);
    }
  });

  it("hides the votes until they are revealed", () => {
    const events = wholeGame();
    const beforeReveal = view({ events: events.slice(0, 15) });

    expect(beforeReveal.votes).toBeNull();
    expect(beforeReveal.seats.map((seat) => seat.hasVoted)).toEqual([true, true, true]);
    expect(beforeReveal.transcript.some((entry) => entry.kind === "vote")).toBe(false);

    const afterReveal = view({ events: events.slice(0, 16) });

    expect(afterReveal.votes).toEqual({
      revealed: true,
      votes: [
        { voter: 0, target: 1 },
        { voter: 1, target: 2 },
        { voter: 2, target: 1 },
      ],
      caught: [1],
    });
    expect(afterReveal.seats.map((seat) => seat.votesReceived)).toEqual([0, 2, 1]);
    expect(afterReveal.seats.map((seat) => seat.caught)).toEqual([false, true, false]);
  });

  it("hides the secret word in live clues and statements, also a start of it", () => {
    const events = [gameStarted(0), phaseStarted(1, "clue", 1), turnStarted(2, 0)];
    const whole = view({
      events,
      answers: { 0: answer(0, "clue", '{"clue": "Lighthouse') },
    });
    const start = view({
      events,
      answers: { 0: answer(0, "clue", '{"clue": "the light') },
    });

    expect(whole.seats[0]?.live?.text).toBe(WORD_MASK);
    expect(start.seats[0]?.live?.text).toBe(`the ${WORD_MASK}`);
  });

  it("reveals everything after the outcome", () => {
    const board = view({ events: wholeGame() });

    expect(board.revealed).toBe(true);
    expect(board.word).toBe("lighthouse");
    expect(board.category).toBe("objects");
    expect(board.seats.map((seat) => seat.role)).toEqual([
      "civilian",
      "imposter",
      "civilian",
    ]);
    expect(board.transcript.filter((entry) => entry.kind === "vote")).toHaveLength(3);
    expect(board.outcome).toMatchObject({
      winner: "civilians",
      title: "The civilians win",
      detail: "Bob was caught and guessed wrong.",
    });
  });
});

describe("buildBoardView in god mode", () => {
  it("shows the word, the roles, the secret votes and the reasoning", () => {
    const board = view({ events: wholeGame().slice(0, 14), mode: "god" });

    expect(board.word).toBe("lighthouse");
    expect(board.seats.map((seat) => seat.role)).toEqual([
      "civilian",
      "imposter",
      "civilian",
    ]);
    expect(board.votes).toEqual({
      revealed: false,
      votes: [
        { voter: 0, target: 1 },
        { voter: 1, target: 2 },
      ],
      caught: [],
    });
    expect(board.transcript.find((entry) => entry.kind === "clue")).toMatchObject({
      reasoning: "Secret thoughts.",
    });
  });

  it("shows the live answer with its reasoning, vote and thinking", () => {
    const events = [gameStarted(0), phaseStarted(1, "vote"), turnStarted(2, 0)];
    const text = '{"vote_for": "Bob", "private_reasoning": "Bob hesit';
    const board = view({
      events,
      mode: "god",
      answers: { 0: answer(0, "vote", text, "Deep thinking") },
    });

    expect(board.seats[0]?.live).toEqual({
      phase: "vote",
      text: null,
      voteFor: "Bob",
      reasoning: "Bob hesit",
      thought: "Deep thinking",
    });
  });
});

describe("buildBoardView", () => {
  it("marks the speaking seats and shows their live answer only at the live end", () => {
    const events = [gameStarted(0), phaseStarted(1, "clue", 1), turnStarted(2, 0)];
    const answers = { 0: answer(0, "clue", '{"clue": "bea') };

    expect(view({ events, answers }).seats[0]).toMatchObject({
      speaking: true,
      live: { text: "bea" },
    });
    expect(view({ events, answers, cursor: 2 }).seats[0]?.speaking).toBe(false);
    expect(view({ events, answers, running: false }).seats[0]?.live).toBeNull();
  });

  it("collects the clues of each seat by round", () => {
    const events = [gameStarted(0), clueGiven(1, 0, "beacon"), clueGiven(2, 1, null)];

    expect(view({ events }).seats.map((seat) => seat.clues)).toEqual([
      [{ round: 1, clue: "beacon" }],
      [{ round: 1, clue: null }],
      [],
    ]);
  });

  it("puts player errors on the entry of their turn", () => {
    const board = view({ events: wholeGame() });
    const bobClue = board.transcript.find(
      (entry) => entry.kind === "clue" && entry.seat === 1,
    );

    expect(bobClue).toMatchObject({
      clue: "coast",
      errors: ["The model did not answer."],
    });
  });

  it("keeps an error of a hidden turn as its own entry", () => {
    const events: GameEvent[] = [
      gameStarted(0),
      { ...voteCast(1, 0, 1), seq: 1 },
      {
        ...voteCast(2, 0, 1),
        seq: 2,
        type: "player_error",
        visibility: "system",
        message: "Invalid vote.",
      } as unknown as GameEvent,
    ];
    const board = view({ events });

    expect(board.transcript).toEqual([
      { key: "e2", kind: "error", seat: 0, message: "Invalid vote." },
    ]);
  });

  it("adds up the tokens and the estimated cost", () => {
    const board = view({ events: wholeGame() });

    expect(board.usage.tokens).toBe(1_100_000);
    expect(board.usage.costUsd).toBeCloseTo(0.1 + 0.05);
  });

  it("follows the phase and round of the latest event", () => {
    expect(view({ events: wholeGame().slice(0, 11) })).toMatchObject({
      phase: "discussion",
      round: 1,
    });
  });
});

describe("maskWord", () => {
  it.each([
    ["A LIGHTHOUSE and a lighthouse", `A ${WORD_MASK} and a ${WORD_MASK}`],
    ["ships need a ligh", `ships need a ${WORD_MASK}`],
    ["light", WORD_MASK],
    ["li", "li"],
    ["beacon", "beacon"],
  ])("masks %j", (text, expected) => {
    expect(maskWord(text, "lighthouse")).toBe(expected);
  });
});

/** Live answers full of secrets for the seats that are speaking at the end of events. */
function liveAnswers(events: GameEvent[]): Partial<Record<number, PartialAnswer>> {
  const answers: Partial<Record<number, PartialAnswer>> = {};
  const phase =
    events.findLast((event) => event.type === "phase_started")?.phase ?? "clue";
  const text = JSON.stringify({
    clue: "lighthouse",
    statement: "The word is lighthouse.",
    vote_for: "Charlie",
    private_reasoning: "Secret thoughts about lighthouse in objects.",
  });

  for (const seat of [0, 1, 2]) {
    answers[seat] = answer(seat, phase, text, "Deep thinking about lighthouse.");
  }

  return answers;
}

describe("buildBoardView bubbles", () => {
  it("keeps what a seat said while its phase and round last", () => {
    const events = wholeGame();
    const discussing = view({ events: events.slice(0, 11), mode: "god" });
    const voting = view({ events: events.slice(0, 12), mode: "god" });

    expect(discussing.seats[2]?.said).toEqual({
      phase: "discussion",
      round: 1,
      text: "Bob seems unsure.",
      reasoning: "Secret thoughts.",
    });
    expect(voting.seats[2]?.said).toBeNull();
  });

  it("keeps the reflections when the game is done", () => {
    const events: GameEvent[] = [
      gameStarted(0),
      { ...BASE_REFLECTION, seq: 1 },
      { ...phaseStarted(2, "done"), round: null },
    ];

    expect(view({ events }).seats[0]?.said?.text).toBe("I played well.");
  });

  it("leaves the reasoning out of the bubble in audience mode", () => {
    const board = view({ events: wholeGame().slice(0, 11) });

    expect(board.seats[2]?.said?.reasoning).toBeNull();
  });
});
